"""Autonomous QA branch naming policy and checkout verification.

The governance model REQUIRES an automation feature/fix branch to be named:

    feature/qa-auto-<feature-name>      (NEW_AUTOMATION / AUTOMATION_ENHANCEMENT)
    fix/qa-auto-<feature-name>          (AUTOMATION_FIX)

This module is the single source of truth for that contract. It:

  - decides whether a branch name is a valid autonomous QA branch,
  - normalizes the Jenkins-reported branch (origin/ or */ prefix stripping),
  - verifies that the branch/commit Jenkins actually checked out is EXACTLY the
    expected branch/commit (no silent substitution of main or another branch).

The same policy is enforced at every boundary:

  - locally in Kernel.branch() (before any modification),
  - in the Commit Planner (gate branch_is_feature_fix / local_gate_fresh),
  - by the CI quality gate (ci_quality.py SCM evidence), and
  - by the Jenkins Branch Verification stage (deterministic batch mirror).

A branch may never silently fall back to main/master or to another automation
branch; the checker must return (False, reason) for any mismatch.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# The QA branch family prefixes (contract). Never hard-code a single feature
# branch name anywhere in CI/CD: the wildcard pattern consumes every suffix.
QA_BRANCH_PREFIXES = ("feature/qa-auto-", "fix/qa-auto-")

# Lowercase feature-name; components separated by single hyphens (no double
# hyphens, no trailing/leading hyphen, no unsafe characters, no secrets).
_BRANCH_RE = re.compile(r"^(feature|fix)/qa-auto-[a-z0-9]+(?:-[a-z0-9]+)*$")

# Prefixes Jenkins may report on a checkout; stripped before comparison. Longest
# prefixes are listed first so the match is unambiguous (refs/remotes/origin/ is
# stripped before remotes/origin/).
_JENKINS_PREFIXES = (
    "refs/remotes/origin/",
    "remotes/origin/",
    "refs/heads/",
    "origin/",
    "*/",
)


def is_valid_qa_branch(branch: Optional[str]) -> bool:
    """True ONLY for a well-formed autonomous feature/fix QA branch.

    Rejects main/master, bare qa-auto-admin, feature/random, empty suffixes,
    uppercase, double hyphens, trailing/leading hyphens and anything that is
    not exactly feature/qa-auto-<name> or fix/qa-auto-<name>.
    """
    if not branch:
        return False
    return _BRANCH_RE.fullmatch(branch.strip()) is not None


def normalize_jenkins_branch(branch: Optional[str]) -> Optional[str]:
    """Strip the Jenkins checkout prefix so `origin/feature/qa-auto-x` and
    `*/feature/qa-auto-x` compare equal to `feature/qa-auto-x`.

    Returns None for an empty/whitespace value; unknown values are returned
    unchanged so the caller can still reject them.
    """
    if not branch:
        return None
    name = branch.strip()
    for prefix in _JENKINS_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name


def verify_checkout(
    expected_branch: Optional[str],
    expected_commit: Optional[str],
    actual_branch: Optional[str],
    actual_head: Optional[str],
) -> Tuple[bool, str]:
    """Verify that the checked-out branch/commit match the expected evidence.

    PASS requires:
      - expected branch present and a valid autonomous QA branch,
      - actual branch (Jenkins-normalized) is not empty,
      - actual branch == expected branch (no silent substitution),
      - expected commit and actual HEAD both present,
      - actual HEAD == expected commit (exact commit evidence).

    Returns (True, "") on PASS, otherwise (False, reason) with a deterministic,
    machine-readable reason string.
    """
    expected = normalize_jenkins_branch(expected_branch)
    if not expected:
        return False, "expected_branch_missing"
    if not is_valid_qa_branch(expected):
        return False, f"expected_branch_not_qa: {expected!r}"

    actual = normalize_jenkins_branch(actual_branch)
    if not actual:
        return False, "actual_branch_missing"
    if actual != expected:
        return (
            False,
            f"branch_substitution: expected {expected!r}, checked out {actual!r}",
        )
    if not (expected_commit and actual_head):
        return False, "commit_evidence_missing"
    if str(actual_head).strip() != str(expected_commit).strip():
        return (
            False,
            f"commit_mismatch: expected {expected_commit!r}, checked out {actual_head!r}",
        )
    return True, ""