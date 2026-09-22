"""CI Quality Gate: deterministic verdict over executed Robot + Allure artifacts.

The CI quality gate is the Jenkins-side counterpart of FINAL_QUALITY_GATE. It
converts executed artifacts (output.xml, allure-results/, branch evidence) into a
GREEN / RED / UNVERIFIED verdict that is NEVER inferred from file existence alone
or from an agent's verbal claim. A PASS requires:

  - a real Robot test run (total > 0) parsed from output.xml,
  - zero failed / zero skipped / zero unresolved tests,
  - Allure results present, status-parity matching the Robot total, and no
    credential leakage in the generated artifacts,
  - (when branch/commit are supplied) the checked-out branch matching the
    feature/qa-auto-* or fix/qa-auto-* wildcard contract and a real commit SHA.

The verdict is exported as a machine-readable JSON artifact (ci-quality-gate.json)
that Jenkins archives and the orchestrator's CI_VALIDATION can consume.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .adapters.allure import AllureRunner
from .adapters.robot import RobotRunner
from .branch_policy import normalize_jenkins_branch

# The identical branch contract enforced by the Jenkins branch-selection guard:
# a CI-triggering build must originate from an autonomous feature or fix branch.
QA_BRANCH_PATTERNS = ("feature/qa-auto-", "fix/qa-auto-")

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


@dataclass
class CIQualityResult:
    status: str = "UNVERIFIED"  # GREEN | RED | UNVERIFIED
    robot: Dict[str, int] = field(default_factory=dict)
    allure: Dict[str, object] = field(default_factory=dict)
    branch: Optional[str] = None
    commit: Optional[str] = None
    reasons: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "GREEN"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "robot": dict(self.robot),
            "allure": dict(self.allure),
            "branch": self.branch,
            "commit": self.commit,
            "reasons": list(self.reasons),
        }


class CIQualityGate:
    """Evaluate executed artifacts and produce the reusable CI quality verdict."""

    def __init__(
        self,
        output_xml: Optional[Path] = None,
        allure_dir: Optional[Path] = None,
        allure_runner: Optional[AllureRunner] = None,
        robot_parser=None,
    ) -> None:
        self.output_xml = output_xml
        self.allure_dir = allure_dir
        self.allure = allure_runner or AllureRunner()
        self._robot_parse = robot_parser or RobotRunner._parse

    def evaluate(
        self,
        output_xml: Optional[Path] = None,
        allure_dir: Optional[Path] = None,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
    ) -> CIQualityResult:
        output_xml = Path(output_xml or self.output_xml or "results/run/output.xml")
        allure_dir = Path(allure_dir or self.allure_dir or "results/run/allure-results")
        result = CIQualityResult(branch=branch, commit=commit)
        reasons = result.reasons

        if not output_xml.exists():
            reasons.append(f"missing robot output.xml: {output_xml}")
            result.status = "UNVERIFIED"
            return result

        counts = self._robot_parse(output_xml)
        result.robot = counts
        if not counts.get("total", 0):
            reasons.append("robot output.xml parsed no executed tests")
            result.status = "RED"
            return result

        if counts.get("failed", 0) or counts.get("skipped", 0) or counts.get("unresolved", 0):
            reasons.append(
                "robot run not clean: "
                f"failed={counts.get('failed', 0)} "
                f"skipped={counts.get('skipped', 0)} "
                f"unresolved={counts.get('unresolved', 0)}"
            )
            result.status = "RED"
        elif not allure_dir.exists() or not list(allure_dir.glob("*-result.json")):
            reasons.append(f"allure-results missing or empty: {allure_dir}")
            result.status = "RED"
        else:
            result_files = list(allure_dir.glob("*-result.json"))
            total = counts.get("total", 0)
            result.allure = {
                "result_count": len(result_files),
                "results_present": total > 0 and len(result_files) > 0,
                "status_parity": total > 0 and len(result_files) == total,
                "credential_leak": self.allure.scan_for_credentials(allure_dir),
            }
            if not result.allure["status_parity"]:
                reasons.append(
                    f"allure parity mismatch: result files {len(result_files)} != robot total {total}"
                )
                result.status = "RED"
            elif result.allure["credential_leak"]:
                reasons.append("credential leak detected in allure artifacts")
                result.status = "RED"

        if branch is not None or commit is not None:
            self._validate_scm_evidence(result, branch, commit)

        if result.status == "UNVERIFIED":
            result.status = "GREEN" if (not reasons and counts.get("total", 0)) else "RED"

        if result.status == "RED":
            reasons.append("ci quality gate RED (non-clean run or unusable artifacts)")
        if result.status == "UNVERIFIED":
            reasons.append("missing robot output.xml: cannot determine verdict")
        return result

    def _validate_scm_evidence(
        self, result: CIQualityResult, branch: Optional[str], commit: Optional[str]
    ) -> None:
        """When provided, branch/commit must satisfy the autonomous-delivery contract."""
        if branch is not None:
            # Jenkins reports the checkout branch with a prefix (origin/,
            # refs/remotes/origin/, */, ...). The shared branch_policy
            # normalizer strips every known prefix deterministically.
            stripped = normalize_jenkins_branch(branch)
            if stripped and not stripped.startswith(QA_BRANCH_PATTERNS):
                result.reasons.append(f"branch {branch!r} not in {QA_BRANCH_PATTERNS}")
                result.status = "RED"
        if commit is not None:
            if commit and not _SHA_RE.fullmatch(commit.strip()):
                result.reasons.append(f"commit {commit!r} is not a valid SHA")
                result.status = "RED"

    def export(self, result: CIQualityResult, out_path: Optional[Path] = None) -> Path:
        """Persist the verdict as ci-quality-gate.json (evidence for CI_VALIDATION)."""
        out_path = Path(out_path or "results/run/ci-quality-gate.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
        return out_path