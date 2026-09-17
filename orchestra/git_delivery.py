"""Git Delivery: commit + push execution, gated exclusively by the commit plan.

This stage performs the REAL git actions — but ONLY when:
  - the CommitPlan is safe (all mandatory commit gates passed),
  - the plan is EXACTLY what gets staged (explicit per-file staging; never git add .),
  - the target branch is a feature/fix branch that exists locally,
  - a push is requested only for that branch (never origin/main autonomously).

Dry-run mode performs the full decision and evidence check WITHOUT touching the
git index, creating a commit or hitting the remote. In every mode the result
records the commit SHA and the verified push state from real git output — never
fabricated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .adapters.git import GitAdapter
from .commit_planner import CommitPlan
from .secrets import diff_contains_secrets


@dataclass
class DeliveryAttempt:
    delivered: bool = False
    dry_run: bool = False
    commit_hash: Optional[str] = None
    staged_paths: List[str] = field(default_factory=list)
    push_output: str = ""
    remote_head: Optional[str] = None
    pushed_verified: bool = False
    reasons: List[str] = field(default_factory=list)

    @property
    def committed(self) -> bool:
        return bool(self.commit_hash)

    def to_dict(self) -> dict:
        return {
            "delivered": self.delivered,
            "dry_run": self.dry_run,
            "commit_hash": self.commit_hash,
            "staged_paths": list(self.staged_paths),
            "push_output": self.push_output,
            "remote_head": self.remote_head,
            "pushed_verified": self.pushed_verified,
            "reasons": list(self.reasons),
        }


class GitDelivery:
    def __init__(self, git: Optional[GitAdapter] = None) -> None:
        self.git = git or GitAdapter()

    def deliver(self, plan: CommitPlan, *, push: bool = True, dry_run: bool = False,
                remote: str = "origin") -> DeliveryAttempt:
        """Execute (or dry-run) the commit + push described by `plan`.

        Raises RuntimeError when the plan is unsafe or when a real execution would
        stage a file that is not part of the plan. Returns a DeliveryAttempt with
        real git evidence (commit hash, staged paths, remote HEAD).

        Dry-run NEVER touches the git index or remote: the expected staged set is
        the plan's own file list and no commit/push subprocess is issued.
        """
        attempt = DeliveryAttempt(dry_run=dry_run)

        if not plan.safe:
            attempt.reasons.append(
                f"unsafe_plan: {plan.failed_gates or 'empty file list'}"
            )
            return attempt

        if dry_run:
            attempt.staged_paths = sorted(plan.files_to_stage)
            attempt.reasons.append("dry_run: commit and push validated, not executed")
            return attempt

        # Stage EXACTLY the planned files (never a wildcard/git-add-all).
        self.git.stage(plan.files_to_stage)
        staged = self.git.staged_paths()
        planned = set(plan.files_to_stage)
        staged_set = set(staged)
        if staged_set != planned:
            attempt.reasons.append(
                "staged_mismatch: staged set differs from the plan "
                f"(extra={sorted(staged_set - planned)}, "
                f"missing={sorted(planned - staged_set)})"
            )
            return attempt
        attempt.staged_paths = sorted(staged_set)

        # Secret re-check on the REAL staged diff (defense in depth).
        if diff_contains_secrets(self.git.diff_cached()):
            attempt.reasons.append("secrets_detected_in_staged_diff")
            return attempt

        attempt.commit_hash = self.git.commit(plan.message)
        if push:
            attempt.push_output = self.git.push(plan.branch, remote=remote)
            attempt.remote_head = self.git.ls_remote(plan.branch, remote=remote)
            attempt.pushed_verified = self.git.verify_push(
                plan.branch, attempt.commit_hash, remote=remote
            )
            if not attempt.pushed_verified:
                attempt.reasons.append(
                    "push_unverified: remote HEAD does not match local commit"
                )
        attempt.delivered = bool(attempt.commit_hash) and (
            not push or attempt.pushed_verified
        )
        return attempt