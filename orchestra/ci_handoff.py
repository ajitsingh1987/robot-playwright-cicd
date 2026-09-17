"""CI Handoff + Delivery Verifier for the Jenkins-maintained Robot-Playwright job.

The GitHub webhook is the ONLY mechanism that starts Jenkins's
Robot-Playwright-Sanity job. This module:

  - verifies a pushed SHA is actually present on the remote feature/fix branch
    (DeliveryVerifier, real `git ls-remote` / adapter evidence),
  - verifies whether the Jenkins job is reachable/visible (build/console evidence)
    and produces a strict CI_VALIDATION verdict,
  - tracks CI healing attempts (max 3) — a failed CI run may heal only up to the cap.

Anti-fabrication contract: a verdict is PASS only when real evidence exists
(remote HEAD matches the commit and a Jenkins build with SUCCESS result + 0
failed tests is observable). Otherwise the verdict is UNVERIFIED / FAIL and is
NEVER reported as PASS. A CI verdict of UNVERIFIED keeps the ci gate blocked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .adapters.git import GitAdapter
from .config import settings

JENKINS_JOB = getattr(settings, "JENKINS_JOB_NAME", "Robot-Playwright-Sanity")


@dataclass
class DeliveryVerification:
    verified: bool = False
    local_head: Optional[str] = None
    remote_head: Optional[str] = None
    branch_exists_remote: bool = False
    uncommitted_after_commit: bool = False
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verified": self.verified,
            "local_head": self.local_head,
            "remote_head": self.remote_head,
            "branch_exists_remote": self.branch_exists_remote,
            "uncommitted_after_commit": self.uncommitted_after_commit,
            "reasons": list(self.reasons),
        }


@dataclass
class CIVerification:
    # CI states: PASS (real evidence), UNVERIFIED (no reachable evidence), FAIL.
    status: str = "UNVERIFIED"
    job: str = JENKINS_JOB
    build_url: Optional[str] = None
    build_result: Optional[str] = None
    test_counts: Dict[str, int] = field(default_factory=dict)
    checkout_sha: Optional[str] = None
    reasons: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "job": self.job,
            "build_url": self.build_url,
            "build_result": self.build_result,
            "test_counts": dict(self.test_counts),
            "checkout_sha": self.checkout_sha,
            "reasons": list(self.reasons),
        }


class DeliveryVerifier:
    """Post-push verification: the delivered SHA is real and reachable remotely."""

    def __init__(self, git: Optional[GitAdapter] = None) -> None:
        self.git = git or GitAdapter()

    def verify_push(self, branch: str, commit_hash: str) -> DeliveryVerification:
        ver = DeliveryVerification()
        if not commit_hash:
            ver.reasons.append("missing_commit_hash")
            return ver
        ver.local_head = commit_hash
        ver.remote_head = self.git.ls_remote(branch)
        ver.branch_exists_remote = bool(ver.remote_head)
        ver.verified = bool(ver.remote_head) and ver.remote_head == commit_hash
        ver.uncommitted_after_commit = not self._staged_untracked_delta(branch)
        if ver.remote_head and ver.remote_head != commit_hash:
            ver.reasons.append("remote_head_mismatch")
        if not ver.branch_exists_remote:
            ver.reasons.append("branch_not_on_remote")
        return ver

    def _staged_untracked_delta(self, branch: str) -> bool:
        """True when the worktree still has staged/untracked entries that should
        have been consumed by the commit (indicates the commit was incomplete)."""
        try:
            status = self.git.status()
        except Exception:
            return True  # unverifiable -> treat as delta present
        return any(not e.is_untracked for e in status.entries)


class CIHandoff:
    """Records and verifies the GitHub webhook -> Jenkins Robot-Playwright-Sanity
    handoff. The webhook is the ONLY trigger; we never push to force a run and we
    never fabricate a PASS when the build is unreachable."""

    MAX_CI_HEALING = 3

    def __init__(self, git: Optional[GitAdapter] = None) -> None:
        self.git = git or GitAdapter()

    def track(self, branch: str, commit_hash: str) -> CIVerification:
        """Verify reachability of the pushed branch + Jenkins job.

        A remote head that matches the commit is necessary but not sufficient for
        PASS: PASS also requires an observable Jenkins build with SUCCESS and 0
        failed tests (via a callback supplied by CI integration). When the build
        is not observable, the verdict is UNVERIFIED and the ci gate stays blocked.
        """
        ver = DeliveryVerifier(self.git).verify_push(branch, commit_hash)
        if not ver.verified:
            return CIVerification(
                status="FAIL",
                checkout_sha=commit_hash,
                reasons=ver.reasons,
            )
        # The handoff contract: webhook fires once per new commit. Whether Jenkins
        # actually executed it is only knowable with real CI evidence; without it we
        # report UNVERIFIED (never PASS).
        return CIVerification(
            status="UNVERIFIED",
            checkout_sha=commit_hash,
            reasons=["jenkins_build_not_observable_from_this_environment"],
        )

    @staticmethod
    def verify_external(ver: CIVerification, *, build_url: str, build_result: str,
                        failed_tests: int, total_tests: int, checkout_sha: Optional[str] = None,
                        reason: str = "") -> CIVerification:
        """Promote a CI verification to PASS ONLY with real external build evidence.

        PASS requires: build_result == 'SUCCESS', failed_tests == 0, total_tests > 0.
        Anything else (missing url, non-success, or failed>0) is FAIL/UNVERIFIED.
        """
        ver.build_url = build_url or None
        ver.build_result = build_result or None
        ver.checkout_sha = checkout_sha or ver.checkout_sha
        ver.test_counts = {"total": total_tests, "failed": failed_tests}
        if reason:
            ver.reasons.append(reason)
        if not build_url:
            ver.status = "UNVERIFIED"
            return ver
        if build_result != "SUCCESS":
            ver.status = "FAIL"
            ver.reasons.append(f"build_result={build_result}")
            return ver
        if failed_tests > 0:
            ver.status = "FAIL"
            ver.reasons.append(f"failed_tests={failed_tests}")
            return ver
        if total_tests <= 0:
            ver.status = "UNVERIFIED"
            ver.reasons.append("no_executed_tests")
            return ver
        ver.status = "PASS"
        ver.reasons.append("jenkins_build_success_with_real_evidence")
        return ver


class CIHealingTracker:
    """Jenkins-side healing counter, capped at 3 attempts (never a 4th auto-push)."""

    def __init__(self) -> None:
        self._attempts = 0

    def attempts(self) -> int:
        return self._attempts

    def can_heal(self) -> bool:
        return self._attempts < CIHandoff.MAX_CI_HEALING

    def start_attempt(self) -> int:
        if not self.can_heal():
            raise RuntimeError(
                f"CI healing cap exceeded ({self._attempts}/{CIHandoff.MAX_CI_HEALING}); "
                "no 4th autonomous Jenkins repair attempt."
            )
        self._attempts += 1
        return self._attempts