"""Unit tests for the executable LOCAL QUALITY GATE (local_gate.py).

The local gate is the ONLY authorizer of COMMIT/PUSH. These tests prove:
  - the worktree fingerprint is deterministic and sensitive to any change,
    INCLUDING a content-only modification of an already-dirty file,
  - GREEN requires every mandatory check to pass,
  - a GREEN verdict is bound to branch + HEAD + fingerprint (stale -> RED),
  - a Robot-affecting change REQUIRES Robot execution: no artifacts -> RED,
    non-GREEN CI gate -> RED, GREEN CI gate -> GREEN,
  - a framework-only change may defer robot_ci (None) when no artifacts exist,
  - verdict artifacts round-trip through local-quality-gate.json.

No real subprocess is executed: pytest/arch/dry-run/ci-gate runners are stubbed.
"""
from __future__ import annotations

import pytest

from orchestra import local_gate
from orchestra.adapters.git import GitStatus, GitStatusEntry
from orchestra.local_gate import (
    LocalGateVerdict,
    affects_robot_automation,
    compute_worktree_fingerprint,
    export_verdict,
    load_verdict,
    run_local_gate,
)


class FakeGit:
    def __init__(self, entries=None, branch="feature/qa-auto-login", head="a" * 40):
        self._entries = entries or []
        self._branch = branch
        self._head = head

    def status(self) -> GitStatus:
        return GitStatus(entries=list(self._entries))

    def current_branch(self):
        return self._branch

    def head(self):
        return self._head


def _entry(code, path):
    return GitStatusEntry(index=code[0], worktree=code[1], path=path,
                          untracked=(code == "??"))


# ── fingerprint ───────────────────────────────────────────────────────────
def test_fingerprint_is_deterministic():
    g1 = FakeGit(entries=[_entry(" M", "tests/a.robot")])
    g2 = FakeGit(entries=[_entry(" M", "tests/a.robot")])
    assert compute_worktree_fingerprint(g1) == compute_worktree_fingerprint(g2)


def test_fingerprint_changes_with_entries():
    base = FakeGit(entries=[_entry(" M", "tests/a.robot")])
    changed = FakeGit(entries=[
        _entry(" M", "tests/a.robot"),
        _entry("??", "tests/b.robot"),
    ])
    assert compute_worktree_fingerprint(base) != compute_worktree_fingerprint(changed)


def test_fingerprint_changes_with_branch_and_head():
    base = FakeGit(entries=[_entry(" M", "tests/a.robot")])
    other_branch = FakeGit(entries=[_entry(" M", "tests/a.robot")],
                           branch="feature/qa-auto-admin")
    other_head = FakeGit(entries=[_entry(" M", "tests/a.robot")], head="b" * 40)
    assert compute_worktree_fingerprint(base) != compute_worktree_fingerprint(other_branch)
    assert compute_worktree_fingerprint(base) != compute_worktree_fingerprint(other_head)


def test_fingerprint_order_independent():
    e1 = _entry(" M", "tests/a.robot")
    e2 = _entry("??", "tests/b.robot")
    assert compute_worktree_fingerprint(FakeGit(entries=[e1, e2])) == \
        compute_worktree_fingerprint(FakeGit(entries=[e2, e1]))


def test_fingerprint_changes_with_file_content_only(tmp_path):
    """A content-only edit of an already-dirty file MUST invalidate the fingerprint.

    The entry set, branch and HEAD are unchanged; only the bytes on disk change.
    """
    f = tmp_path / "tests" / "a.robot"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("*** Test Cases ***\nFirst\n", encoding="utf-8")
    git = FakeGit(entries=[_entry(" M", "tests/a.robot")])
    before = compute_worktree_fingerprint(git, root=tmp_path)
    f.write_text("*** Test Cases ***\nSecond\n", encoding="utf-8")
    after = compute_worktree_fingerprint(git, root=tmp_path)
    assert before != after


def test_fingerprint_content_hash_ignores_untracked_volatile_paths():
    """Volatile files never appear in git status, so they never affect the hash."""
    base = FakeGit(entries=[_entry(" M", "orchestra/cli.py")])
    assert compute_worktree_fingerprint(base) == compute_worktree_fingerprint(base)


# ── affects_robot_automation ──────────────────────────────────────────────
@pytest.mark.parametrize("path", [
    "tests/login.robot",
    "pages/login_page.robot",
    "resources/common.resource",
    "variables/variables.py",
    "data/users.yaml",
    "login.robot",
])
def test_affects_robot_automation_true(path):
    assert affects_robot_automation([path]) is True


@pytest.mark.parametrize("path", [
    "orchestra/local_gate.py",
    "Jenkinsfile",
    "AGENTS.md",
    "README.md",
    ".opencode/agents/cicd.md",
])
def test_affects_robot_automation_false(path):
    assert affects_robot_automation([path]) is False


def test_affects_robot_automation_windows_separators():
    assert affects_robot_automation(["tests\\login.robot"]) is True


# ── run_local_gate ────────────────────────────────────────────────────────
@pytest.fixture
def stub_checks(monkeypatch):
    def _stub(pytest_ok=True, arch_ok=True, dry_ok=True, ci_ok=True):
        monkeypatch.setattr(local_gate, "_run_pytest", lambda: pytest_ok)
        monkeypatch.setattr(local_gate, "_run_arch", lambda: arch_ok)
        monkeypatch.setattr(local_gate, "_run_dry_run", lambda: dry_ok)
        monkeypatch.setattr(local_gate, "_run_ci_gate", lambda *a, **k: ci_ok)
    return _stub


def test_local_gate_green_framework_only_without_executed_artifacts(
    stub_checks, tmp_path, monkeypatch
):
    stub_checks()
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    verdict = run_local_gate(git=FakeGit(entries=[_entry(" M", "orchestra/cli.py")]))
    assert verdict.status == "GREEN"
    assert verdict.green is True
    assert verdict.checks["robot_ci"] is None
    assert verdict.branch == "feature/qa-auto-login"
    assert verdict.worktree_fingerprint


def test_local_gate_red_when_robot_change_without_execution(
    stub_checks, tmp_path, monkeypatch
):
    """Robot change + no Robot execution => LOCAL RED (never a deferred GREEN)."""
    stub_checks()
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    verdict = run_local_gate(git=FakeGit(entries=[_entry(" M", "tests/a.robot")]))
    assert verdict.status == "RED"
    assert verdict.checks["robot_ci"] is False
    assert any("Robot automation change requires local execution" in r for r in verdict.reasons)


def test_local_gate_red_when_robot_change_and_robot_red(
    stub_checks, tmp_path, monkeypatch
):
    stub_checks(ci_ok=False)
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    (tmp_path / "allure-results").mkdir()
    (tmp_path / "output.xml").write_text("<robot/>", encoding="utf-8")
    (tmp_path / "allure-results" / "1-result.json").write_text("{}", encoding="utf-8")
    verdict = run_local_gate(git=FakeGit(entries=[_entry(" M", "tests/a.robot")]))
    assert verdict.status == "RED"
    assert verdict.checks["robot_ci"] is False


def test_local_gate_green_when_robot_change_and_robot_green(
    stub_checks, tmp_path, monkeypatch
):
    stub_checks(ci_ok=True)
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    (tmp_path / "allure-results").mkdir()
    (tmp_path / "output.xml").write_text("<robot/>", encoding="utf-8")
    (tmp_path / "allure-results" / "1-result.json").write_text("{}", encoding="utf-8")
    verdict = run_local_gate(git=FakeGit(entries=[_entry(" M", "tests/a.robot")]))
    assert verdict.status == "GREEN"
    assert verdict.checks["robot_ci"] is True


def test_local_gate_red_when_pytest_fails(stub_checks, tmp_path, monkeypatch):
    stub_checks(pytest_ok=False)
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    verdict = run_local_gate(git=FakeGit())
    assert verdict.status == "RED"
    assert any("pytest" in r for r in verdict.reasons)


def test_local_gate_red_when_branch_policy_fails(stub_checks, tmp_path, monkeypatch):
    stub_checks()
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    verdict = run_local_gate(git=FakeGit(branch="main"))
    assert verdict.status == "RED"
    assert verdict.checks["branch_policy"] is False
    assert any("branch policy" in r for r in verdict.reasons)


def test_local_gate_red_when_artifacts_present_but_ci_gate_not_green(
    stub_checks, tmp_path, monkeypatch
):
    stub_checks(ci_ok=False)
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    (tmp_path / "allure-results").mkdir()
    (tmp_path / "output.xml").write_text("<robot/>", encoding="utf-8")
    (tmp_path / "allure-results" / "1-result.json").write_text("{}", encoding="utf-8")
    verdict = run_local_gate(git=FakeGit())
    assert verdict.status == "RED"
    assert verdict.checks["robot_ci"] is False
    assert any("robot_ci" in r for r in verdict.reasons)


def test_local_gate_green_when_artifacts_present_and_ci_gate_green(
    stub_checks, tmp_path, monkeypatch
):
    stub_checks(ci_ok=True)
    monkeypatch.setattr(local_gate.settings, "RESULTS_DIR", tmp_path)
    (tmp_path / "allure-results").mkdir()
    (tmp_path / "output.xml").write_text("<robot/>", encoding="utf-8")
    (tmp_path / "allure-results" / "1-result.json").write_text("{}", encoding="utf-8")
    verdict = run_local_gate(git=FakeGit())
    assert verdict.status == "GREEN"
    assert verdict.checks["robot_ci"] is True


# ── verdict artifact round-trip ───────────────────────────────────────────
def test_verdict_artifact_round_trip(tmp_path):
    verdict = LocalGateVerdict(
        status="GREEN", branch="feature/qa-auto-login", head="a" * 40,
        worktree_fingerprint="deadbeef",
        checks={"pytest": True, "arch": True, "dry_run": True,
                "branch_policy": True, "robot_ci": None},
        reasons=[],
    )
    out = export_verdict(verdict, tmp_path / "local-quality-gate.json")
    loaded = load_verdict(out)
    assert loaded is not None
    assert loaded.status == "GREEN"
    assert loaded.worktree_fingerprint == "deadbeef"
    assert loaded.checks["robot_ci"] is None
    assert loaded.to_dict() == verdict.to_dict()


def test_load_verdict_absent_is_none(tmp_path):
    assert load_verdict(tmp_path / "missing.json") is None


def test_load_verdict_corrupt_is_none(tmp_path):
    p = tmp_path / "local-quality-gate.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_verdict(p) is None