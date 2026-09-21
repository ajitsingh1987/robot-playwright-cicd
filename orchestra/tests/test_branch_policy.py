"""Unit tests for the autonomous QA branch naming policy + checkout verification.

Contract (governance): every autonomous automation branch is
feature/qa-auto-<feature-name> (NEW_AUTOMATION / AUTOMATION_ENHANCEMENT) or
fix/qa-auto-<feature-name> (AUTOMATION_FIX). main/master and malformed names are
rejected, and checkout verification must NEVER silently substitute another
branch (main or a different QA branch).
"""
from __future__ import annotations

import pytest

from orchestra.branch_policy import (
    is_valid_qa_branch,
    normalize_jenkins_branch,
    verify_checkout,
)


# ── is_valid_qa_branch ────────────────────────────────────────────────────
@pytest.mark.parametrize("branch", [
    "feature/qa-auto-admin",
    "feature/qa-auto-leave",
    "feature/qa-auto-leave-application-approval",
    "feature/qa-auto-user-management",
    "feature/qa-auto-orangehrm-automation",
    "fix/qa-auto-login",
    "fix/qa-auto-employee-login-required-assertion",
])
def test_valid_qa_branches(branch):
    assert is_valid_qa_branch(branch) is True


@pytest.mark.parametrize("branch", [
    "main",
    "master",
    "develop",
    "feature/random",
    "qa-auto-admin",
    "fix/random",
    "feature/qa-auto-",
    "fix/qa-auto-",
    "feature/qa-auto-Admin",            # uppercase
    "feature/qa-auto-admin--panel",     # double hyphen
    "feature/qa-auto-admin-",           # trailing hyphen
    "feature/qa-auto-admin/panel",      # slash
    "feature/qa-auto-admin panel",      # space
    "*/feature/qa-auto-admin",          # must be normalized first
    "origin/feature/qa-auto-admin",     # must be normalized first
    "",
    None,
])
def test_invalid_qa_branches(branch):
    assert is_valid_qa_branch(branch) is False


# ── normalize_jenkins_branch ──────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("origin/feature/qa-auto-admin", "feature/qa-auto-admin"),
    ("*/feature/qa-auto-admin", "feature/qa-auto-admin"),
    ("remotes/origin/fix/qa-auto-login", "fix/qa-auto-login"),
    ("refs/heads/feature/qa-auto-admin", "feature/qa-auto-admin"),
    ("feature/qa-auto-admin", "feature/qa-auto-admin"),
    ("  feature/qa-auto-admin  ", "feature/qa-auto-admin"),
])
def test_normalize_jenkins_branch(raw, expected):
    assert normalize_jenkins_branch(raw) == expected


def test_normalize_unknown_value_is_unchanged_so_it_can_be_rejected():
    assert normalize_jenkins_branch("main") == "main"
    assert is_valid_qa_branch(normalize_jenkins_branch("main")) is False


def test_normalize_empty_is_none():
    assert normalize_jenkins_branch("") is None
    assert normalize_jenkins_branch(None) is None


# ── verify_checkout (no silent substitution) ──────────────────────────────
def test_verify_checkout_pass():
    ok, reason = verify_checkout(
        "feature/qa-auto-admin", "a" * 40, "origin/feature/qa-auto-admin", "a" * 40
    )
    assert ok is True
    assert reason == ""


def test_verify_checkout_rejects_branch_substitution_to_main():
    ok, reason = verify_checkout(
        "feature/qa-auto-admin", "a" * 40, "main", "a" * 40
    )
    assert ok is False
    assert "branch_substitution" in reason


def test_verify_checkout_rejects_substitution_to_another_qa_branch():
    ok, reason = verify_checkout(
        "feature/qa-auto-admin", "a" * 40, "feature/qa-auto-leave", "a" * 40
    )
    assert ok is False
    assert "branch_substitution" in reason


def test_verify_checkout_rejects_commit_mismatch():
    ok, reason = verify_checkout(
        "feature/qa-auto-admin", "a" * 40, "feature/qa-auto-admin", "b" * 40
    )
    assert ok is False
    assert "commit_mismatch" in reason


def test_verify_checkout_rejects_non_qa_expected_branch():
    ok, reason = verify_checkout("main", "a" * 40, "main", "a" * 40)
    assert ok is False
    assert "expected_branch_not_qa" in reason


def test_verify_checkout_rejects_missing_evidence():
    ok, reason = verify_checkout("feature/qa-auto-admin", "", "feature/qa-auto-admin", "")
    assert ok is False
    assert "commit_evidence_missing" in reason
    ok, reason = verify_checkout("feature/qa-auto-admin", "a" * 40, "", "a" * 40)
    assert ok is False
    assert "actual_branch_missing" in reason


def test_verify_checkout_never_passes_on_any_branch_mismatch():
    """Exhaustive guard: PASS implies expected == actual (no substitution)."""
    expected = "feature/qa-auto-admin"
    for actual in ["main", "master", "feature/qa-auto-leave", "fix/qa-auto-admin"]:
        ok, _ = verify_checkout(expected, "a" * 40, actual, "a" * 40)
        assert ok is False, actual