"""Executable LOCAL QUALITY GATE: GREEN/RED verdict bound to the working tree.

The COMMIT/PUSH authorizer is NOT documentation: this module runs the local
quality gate as real processes and produces a machine-readable verdict
(local-quality-gate.json) whose evidence is bound to the CURRENT working-tree
state via a deterministic fingerprint.

Fingerprint = sha256 over, for every `git status --porcelain` entry (sorted):
    - the status code,
    - the relative file path,
    - a sha256 hash of the file CONTENT on disk,
  plus the active branch and the current HEAD.

Because the content hash is part of the fingerprint, a content-only edit of an
already-dirty file invalidates a previously recorded GREEN. A GREEN recorded in
one run NEVER authorizes a different change set: the Commit Planner's
`local_gate_fresh` gate re-computes the fingerprint at commit time and refuses if
the working tree content / entry set / branch / HEAD have changed since the
verdict. Volatile paths (results/, .git/, .venv/, __pycache__/, logs) never
appear in `git status` and are therefore never part of the fingerprint.

Mandatory checks (all must be True for GREEN):
    - pytest       : python -m pytest orchestra/tests -q
    - arch         : python -m orchestra arch
    - dry_run      : python -m orchestra dry-run --mode NEW_AUTOMATION --scope FULL_REGRESSION
    - branch_policy: active branch is a feature/qa-auto-* / fix/qa-auto-* branch

Robot execution check (robot_ci):
    - True  : executed Robot+Allure artifacts exist and the CI gate verdict is GREEN.
    - False : the change touches the Robot automation surface (tests/, pages/,
              resources/, variables/, data/, *.robot, *.resource) and either no
              executed artifacts exist (no local Robot execution) or the CI gate
              verdict is not GREEN. A Robot-affecting change is NEVER GREEN without
              Robot evidence.
    - None  : a framework-only change (no Robot surface touched) with no executed
              artifacts; Robot validation is genuinely irrelevant locally and is
              deferred to Jenkins (recorded, never claimed as verified).

Status is GREEN only when every mandatory check passed and robot_ci is not
False. Any RED check keeps the run RED so it can never authorize a commit.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .adapters.git import GitAdapter
from .branch_policy import is_valid_qa_branch
from .config import settings

# The evidence artifact consumed by the Commit Planner / deliverable flow. It is
# NEVER a fake GREEN marker: status is only GREEN when every check above passed.
LOCAL_GATE_ARTIFACT = "results/run/local-quality-gate.json"

# The Robot automation execution surface. A change touching any of these paths
# makes local Robot execution MANDATORY before a GREEN verdict can be issued.
ROBOT_SURFACE_PREFIXES = ("tests/", "pages/", "resources/", "variables/", "data/")
ROBOT_SURFACE_SUFFIXES = (".robot", ".resource")


def affects_robot_automation(paths: List[str]) -> bool:
    """True when any changed path belongs to the Robot automation surface.

    The surface is `tests/`, `pages/`, `resources/`, `variables/`, `data/` and any
    `*.robot` / `*.resource` file. A change here can only be validated by actually
    executing the affected Robot suite, so the local gate must not issue a GREEN
    without Robot execution evidence.
    """
    for raw in paths or []:
        path = (raw or "").replace("\\", "/")
        if not path:
            continue
        if path.startswith(ROBOT_SURFACE_PREFIXES):
            return True
        if path.lower().endswith(ROBOT_SURFACE_SUFFIXES):
            return True
    return False


def _content_hash(root: Path, path: str) -> str:
    """Stable sha256 of a worktree file's CONTENT (ABSENT when unreadable)."""
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        if p.is_file():
            return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        pass
    return "ABSENT"


def compute_worktree_fingerprint(git, root: Optional[Path] = None) -> str:
    """Deterministic sha256 of the current git worktree evidence.

    `git` is any object exposing status() / current_branch() / head() (the real
    GitAdapter or a hermetic fake). `root` is the worktree root used to read file
    CONTENT (defaults to the project root). The fingerprint covers, for every
    status entry: the status code, the relative path and a content hash, plus the
    branch and HEAD. Any change to the entry set, a file's content, the branch or
    the HEAD produces a different fingerprint, so a recorded GREEN can never be
    re-used for unrelated, newer or content-modified work.
    """
    root = Path(root) if root is not None else settings.PROJECT_ROOT
    status = git.status()
    lines = sorted(
        f"{e.code}\t{e.path}\t{_content_hash(root, e.path)}" for e in status.entries
    )
    branch = git.current_branch() or ""
    head = git.head()
    payload = "\n".join([*lines, branch, head]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class LocalGateVerdict:
    status: str = "RED"  # GREEN | RED (never UNVERIFIED; ROBOT_CI=None is recorded)
    branch: Optional[str] = None
    head: Optional[str] = None
    worktree_fingerprint: str = ""
    checks: Dict[str, object] = field(default_factory=dict)  # bool | None
    reasons: List[str] = field(default_factory=list)

    @property
    def green(self) -> bool:
        return self.status == "GREEN"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "branch": self.branch,
            "head": self.head,
            "worktree_fingerprint": self.worktree_fingerprint,
            "checks": dict(self.checks),
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LocalGateVerdict":
        return cls(
            status=str(data.get("status") or "RED"),
            branch=data.get("branch"),
            head=data.get("head"),
            worktree_fingerprint=str(data.get("worktree_fingerprint") or ""),
            checks=dict(data.get("checks") or {}),
            reasons=list(data.get("reasons") or []),
        )


def _run(version_args: List[str], timeout: int = 1200) -> "subprocess.CompletedProcess":
    return subprocess.run(
        [sys.executable, "-m"] + version_args,
        cwd=str(settings.PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _run_pytest() -> bool:
    try:
        return _run(["pytest", "orchestra/tests", "-q"], timeout=1800).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _run_arch() -> bool:
    try:
        return _run(["orchestra", "arch"]).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _run_dry_run() -> bool:
    try:
        return (
            _run(
                [
                    "orchestra",
                    "dry-run",
                    "--mode",
                    "NEW_AUTOMATION",
                    "--scope",
                    "FULL_REGRESSION",
                ]
            ).returncode
            == 0
        )
    except subprocess.TimeoutExpired:
        return False


def _run_ci_gate(output_xml: Path, allure_dir: Path) -> bool:
    try:
        proc = _run(
            [
                "orchestra",
                "ci-gate",
                "--output-xml",
                str(output_xml),
                "--allure-dir",
                str(allure_dir),
            ]
        )
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def run_local_gate(
    git: Optional[GitAdapter] = None,
    output_xml: Optional[Path] = None,
    allure_dir: Optional[Path] = None,
    root: Optional[Path] = None,
) -> LocalGateVerdict:
    """Execute the deterministic local quality gate and return the verdict.

    NEVER mutates git (read-only: status/branch/HEAD). Runs only deterministic
    local processes (pytest, arch, dry-run, ci-gate) — no browser, no push,
    no network execution.

    Robot execution is MANDATORY when the changed paths touch the Robot
    automation surface: in that case a missing or non-GREEN CI-gate verdict makes
    the whole gate RED. Framework-only changes may defer robot_ci to Jenkins.
    """
    git = git or GitAdapter()
    branch = git.current_branch()
    head = git.head()
    fingerprint = compute_worktree_fingerprint(git, root=root)
    reasons: List[str] = []

    status = git.status()
    changed_paths = [e.path for e in status.entries]
    robot_required = affects_robot_automation(changed_paths)

    checks: Dict[str, object] = {
        "pytest": _run_pytest(),
        "arch": _run_arch(),
        "dry_run": _run_dry_run(),
        "branch_policy": bool(branch) and is_valid_qa_branch(branch),
    }

    if not checks["pytest"]:
        reasons.append("pytest: orchestra test suite RED")
    if not checks["arch"]:
        reasons.append("architecture validation RED")
    if not checks["dry_run"]:
        reasons.append("deterministic machine dry-run RED")
    if not checks["branch_policy"]:
        reasons.append(f"branch policy RED: active branch {branch!r} is not "
                       f"feature/qa-auto-* / fix/qa-auto-*")

    output_xml = Path(output_xml or settings.RESULTS_DIR / "output.xml")
    allure_dir = Path(allure_dir or settings.RESULTS_DIR / "allure-results")
    artifacts_present = output_xml.exists() and any(
        allure_dir.glob("*-result.json")
    )
    if artifacts_present:
        robot_ci = _run_ci_gate(output_xml, allure_dir)
        checks["robot_ci"] = robot_ci
        if not robot_ci:
            reasons.append(
                "robot_ci: executed artifacts are present but the CI gate verdict "
                "is not GREEN"
            )
    elif robot_required:
        # A Robot-affecting change MUST be executed locally before GREEN. No
        # artifacts means no execution happened -> RED (never deferred here).
        checks["robot_ci"] = False
        reasons.append(
            "robot_ci: Robot automation change requires local execution but no "
            "executed Robot/Allure artifacts were found (LOCAL RED)"
        )
    else:
        checks["robot_ci"] = None
        reasons.append(
            "robot_ci: framework-only change; no Robot execution required locally "
            "(CI gate deferred to Jenkins)"
        )

    green = all(v is True for v in checks.values() if v is not None)
    return LocalGateVerdict(
        status="GREEN" if green else "RED",
        branch=branch,
        head=head,
        worktree_fingerprint=fingerprint,
        checks=checks,
        reasons=reasons,
    )


def export_verdict(verdict: LocalGateVerdict, out: Optional[Path] = None) -> Path:
    out = Path(out or LOCAL_GATE_ARTIFACT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(verdict.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    return out


def load_verdict(path: Optional[Path] = None) -> Optional[LocalGateVerdict]:
    """Read a recorded verdict artifact; None when absent/unreadable."""
    path = Path(path or LOCAL_GATE_ARTIFACT)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return LocalGateVerdict.from_dict(data)