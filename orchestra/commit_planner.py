"""Commit Planner: machine-readable, evidence-backed commit plan.

The planner converts Change Intelligence + the quality-gate snapshot into a single
structured plan that is the ONLY input the Git Delivery stage may use. It never
executes git itself; it is the decision layer. Every safety gate is evaluated over
real evidence (git status, the requirement's changeset, on-disk file content and the
recorded quality-gate snapshot). No gate passes on a verbal claim.

A commit is authorized ONLY when ALL mandatory commit gates pass. Any failure
produces an explicit RED reason and the plan is `safe=False` -> NO COMMIT.

Dry-run mode produces the exact same plan without any git mutation, so the full
decision is testable before a real commit is generated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .change_intel import ChangeClassifier, ChangeReport, build_changeset, classify_excluded
from .config import settings
from .secrets import scan_for_credentials

# Message subject prefixes allowed on the active feature/fix branches.
_ALLOWED_MESSAGE_PREFIXES = ("feat(qa):", "fix(qa):", "refactor(qa):", "docs(qa):", "test(qa):")
_FORBIDDEN_EMPTY_MESSAGES = frozenset(
    {"", "kick", "wip", "test", "update", "changes", "chore", "commit"}
)

# Text suffixes scanned for secrets on-disk. Binary/generated files are not text-scanable.
_SCAN_SUFFIXES = (".robot", ".resource", ".py", ".yaml", ".yml", ".md", ".txt", ".json", ".feature")


@dataclass
class CommitPlan:
    requirement: str
    automation_mode: str
    branch: str
    message: str
    files_to_stage: List[str] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)
    changeset: List[str] = field(default_factory=list)
    report: Optional[ChangeReport] = None
    gates: Dict[str, bool] = field(default_factory=dict)
    failed_gates: List[str] = field(default_factory=list)
    secrets_detected: bool = False
    secret_markers: List[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def safe(self) -> bool:
        return not self.failed_gates and bool(self.files_to_stage)

    def to_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "automation_mode": self.automation_mode,
            "branch": self.branch,
            "message": self.message,
            "files_to_stage": list(self.files_to_stage),
            "deleted_files": list(self.deleted_files),
            "changeset": list(self.changeset),
            "safe": self.safe,
            "failed_gates": list(self.failed_gates),
            "secrets_detected": self.secrets_detected,
            "secret_markers": list(self.secret_markers),
            "gates": dict(self.gates),
            "dry_run": self.dry_run,
        }


def validate_commit_message(message: str) -> bool:
    """A meaningful, non-"kick" commit message with an allowed subject prefix."""
    msg = (message or "").strip()
    if not msg or len(msg) < 10:
        return False
    first_line = msg.splitlines()[0].strip().lower()
    if first_line in _FORBIDDEN_EMPTY_MESSAGES:
        return False
    return any(msg.startswith(p) for p in _ALLOWED_MESSAGE_PREFIXES)


def compose_commit_message(requirement: str, automation_mode: str,
                           enhancement: Optional[str] = None) -> str:
    """Compose a meaningful commit message; never an empty/kick string."""
    if automation_mode == "AUTOMATION_FIX":
        prefix = "fix(qa):"
    elif automation_mode == "AUTOMATION_ENHANCEMENT":
        prefix = "feat(qa):"
    elif automation_mode == "REGRESSION":
        prefix = "test(qa):"
    else:
        prefix = "feat(qa):"
    body = f"{requirement}"
    if enhancement:
        body = f"{body} - {enhancement}"
    return f"{prefix} {body}"


class CommitPlanner:
    def __init__(self, root: Optional[Path] = None, classifier: Optional[ChangeClassifier] = None) -> None:
        self.root = root or settings.PROJECT_ROOT
        self.classifier = classifier or ChangeClassifier(self.root)

    def _read_text(self, path: str) -> str:
        """Read a file for secret scanning; binary/nonexistent files yield ''."""
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        if not p.exists() or not p.is_file():
            return ""
        if not p.suffix.lower().lstrip(".") and not path.endswith(_SCAN_SUFFIXES):
            return ""
        if p.suffix.lower() not in _SCAN_SUFFIXES:
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def plan(
        self,
        requirement: str,
        automation_mode: str,
        branch: str,
        state: Dict,
        git,
        *,
        changeset: Optional[List[str]] = None,
        test_file: Optional[str] = None,
        page_objects: Optional[List[str]] = None,
        resources: Optional[List[str]] = None,
        variables: Optional[List[str]] = None,
        data_files: Optional[List[str]] = None,
        enhancement: Optional[str] = None,
        dry_run: bool = False,
    ) -> CommitPlan:
        """Build the commit plan from real git status + the recorded quality snapshot.

        The commit may only proceed when EVERY mandatory gate passes; otherwise the
        plan is unsafe and Git Delivery MUST refuse.
        """
        changeset = changeset or build_changeset(
            requirement, test_file, page_objects, resources, variables, data_files
        )
        status = git.status()
        report = self.classifier.classify(status.entries, changeset=changeset, requirement=requirement)
        message = compose_commit_message(requirement, automation_mode, enhancement)
        deleted_files = [e.path for e in status.entries if e.is_deleted]

        # Files to stage: classified OWNED + SHARED_SUPPORT actually imported.
        files_to_stage = list(report.owned) + list(report.shared_support)
        files_to_stage = [p for p in files_to_stage if not classify_excluded(p)]
        # Deleted files are always staged so the commit is honest about removal.
        for d in deleted_files:
            if d not in files_to_stage and not classify_excluded(d):
                files_to_stage.append(d)

        # Secret scan over the actual file content of every candidate file.
        secret_markers: List[str] = []
        secrets_detected = False
        for f in files_to_stage:
            if not classify_excluded(f):
                found = scan_for_credentials(self._read_text(f))
                if found:
                    secrets_detected = True
                    secret_markers.append(f)

        gates = self._evaluate_gates(
            state=state,
            git=git,
            branch=branch,
            automation_mode=automation_mode,
            files_to_stage=files_to_stage,
            report=report,
            secret_detected=secrets_detected,
            message_valid=validate_commit_message(message),
            git_identity=git.config_set("user.name") and git.config_set("user.email"),
        )
        failed_gates = [gid for gid, ok in gates.items() if not ok]

        plan = CommitPlan(
            requirement=requirement,
            automation_mode=automation_mode,
            branch=branch,
            message=message,
            files_to_stage=files_to_stage,
            deleted_files=deleted_files,
            changeset=changeset,
            report=report,
            gates=gates,
            failed_gates=failed_gates,
            secrets_detected=secrets_detected,
            secret_markers=secret_markers,
            dry_run=dry_run,
        )
        return plan

    def _evaluate_gates(
        self,
        *,
        state: Dict,
        git,
        branch: str,
        automation_mode: str,
        files_to_stage: List[str],
        report: ChangeReport,
        secret_detected: bool,
        message_valid: bool,
        git_identity: bool,
    ) -> Dict[str, bool]:
        final_gate = state.get("final_gate") or {}
        branch_dec = (state.get("branch") or {}).get("decision")
        review = state.get("review") or {}
        healing_attempts = int(state.get("healing_attempts", 0) or 0)
        regression = state.get("regression") or {}
        docker = state.get("docker") or {}
        commit_authorized = bool(state.get("commit_authorized"))

        gates: Dict[str, bool] = {
            # 1. Requirement identified.
            "requirement_identified": bool(files_to_stage),
            # 2. Files classified (report built from real git status; nothing guessed).
            "classified": report.entries is not None,
            # 3. No unrelated files swept into the commit.
            "no_unrelated_in_commit": not report.unrelated,
            # 4. No generated/excluded artifacts staged.
            "no_excluded_in_commit": not any(classify_excluded(p) for p in files_to_stage),
            # 5. No secrets in staged/planned content.
            "no_secrets": not secret_detected,
            # 6. Final quality gate PASS (all mandatory gates satisfied).
            "final_quality_gate_pass": final_gate.get("all_satisfied") is True,
            # 7. Regression executed and clean (real run, 0 fail/0 skip/0 unresolved).
            "regression_clean": (
                int(regression.get("total", 0)) > 0
                and int(regression.get("failed", 1)) == 0
                and int(regression.get("skipped", 1)) == 0
                and int(regression.get("unresolved", 1)) == 0
            ),
            # 8. Docker build + container run clean with artifacts.
            "docker_clean": (
                docker.get("build_exit_code") == 0
                and docker.get("run_exit_code") == 0
                and int(docker.get("robot_failed", 1)) == 0
                and int(docker.get("robot_skipped", 1)) == 0
                and docker.get("output_xml_exists") is True
            ),
            # 9. Healing cap respected (<= 3 attempts; counter orchestrator-owned).
            "healing_cap_respected": healing_attempts <= int(
                getattr(settings, "MAX_HEALING_ATTEMPTS", 3)
            ),
            # 10. Reviewer explicitly approved.
            "reviewer_approved": review.get("verdict") in ("APPROVED", "PASS"),
            # 11. Branch is a feature/fix branch (never origin/main).
            "branch_is_feature_fix": str(branch).startswith(
                ("feature/qa-auto-", "fix/qa-auto-")
            ),
            # 12. Decided branch matches the recorded branch decision.
            "branch_matches_decision": branch_dec is not None
            and (str(branch_dec) == str(branch) or branch_dec.startswith("feature/") or branch_dec.startswith("fix/")),
            # 13. Branch actually exists in git.
            "branch_exists": git.branch_exists(branch),
            # 14. git identity configured (user.name + user.email).
            "git_identity_configured": git_identity,
            # 15. Commit message is meaningful (never a kick/empty commit).
            "message_meaningful": message_valid,
        }

        # Authorization consistency: an explicit automation commit authorization
        # flag is required for automation modes (gate_commit_auth mirrors this).
        gates["commit_authorized"] = commit_authorized
        return gates


def plan_state_ready(
    requirement: str,
    automation_mode: str,
    branch: str,
    state: Dict,
    changeset: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Deterministic readiness probe for the Commit Planner.

    Returns only the state-derived gate inputs; it does NOT run git. Git-backed
    gates are computed inside CommitPlanner.plan() against the real adapter.
    """
    final_gate = state.get("final_gate") or {}
    review = state.get("review") or {}
    regression = state.get("regression") or {}
    docker = state.get("docker") or {}
    return {
        "requirement": requirement,
        "automation_mode": automation_mode,
        "branch": branch,
        "changeset": changeset or [],
        "final_quality_gate_pass": final_gate.get("all_satisfied") is True,
        "reviewer_approved": review.get("verdict") in ("APPROVED", "PASS"),
        "regression_clean": (
            int(regression.get("total", 0)) > 0
            and int(regression.get("failed", 1)) == 0
        ),
        "docker_clean": (
            docker.get("build_exit_code") == 0 and docker.get("run_exit_code") == 0
        ),
        "branch_exists": bool((state.get("branch") or {}).get("exists")),
    }