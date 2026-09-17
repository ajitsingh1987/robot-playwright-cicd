"""Unit tests for the Phase 2 autonomous Git delivery flow.

Covers Change Intelligence classification, Commit Planner safety gates,
Git Delivery (dry-run + unsafe refusal), CI Handoff / Delivery Verifier and the
kernel commit/push/ci wiring. No real git mutation is performed: git subprocesses
are mocked and the adapter logic is exercised against canned output.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.adapters.git import GitAdapter, GitStatus, GitStatusEntry
from orchestra.ci_handoff import CIHandoff, CIHealingTracker, DeliveryVerifier
from orchestra.change_intel import ChangeClassifier, classify_excluded
from orchestra.commit_planner import (
    CommitPlanner,
    compose_commit_message,
    validate_commit_message,
)
from orchestra.evidence import EvidenceBus
from orchestra.gates import GateEngine
from orchestra.git_delivery import GitDelivery
from orchestra.kernel import Kernel
from orchestra.machine import StageRegistry
from orchestra.scope import ImpactDecision
from orchestra.state import StateStore


# ── GitStatus porcelain -z parsing ────────────────────────────────────────
def test_git_status_parse_basic_entries():
    out = " M pages/a_page.robot\x00?? tests/orangehrm_login.robot\x00"
    status = GitStatus.parse(out)
    assert len(status.entries) == 2
    modified = status.entries[0]
    assert modified.path == "pages/a_page.robot"
    assert modified.is_modified
    assert not modified.is_untracked
    untracked = status.entries[1]
    assert untracked.is_untracked


def test_git_status_parse_rename():
    out = "R  new.robot\x00old.robot\x00"
    status = GitStatus.parse(out)
    assert len(status.entries) == 1
    assert status.entries[0].is_renamed
    assert status.entries[0].path == "new.robot"
    assert status.entries[0].original_path == "old.robot"


def test_git_status_empty_is_clean():
    assert GitStatus.parse("").dirty is False


def test_git_status_deleted_detected():
    status = GitStatus.parse(" D tests/gone.robot\x00")
    assert status.entries[0].is_deleted


# ── Change Intelligence classification ────────────────────────────────────
def test_classify_excluded_generated_artifacts():
    for p in ("results/output.xml", "results/run/allure-results/1-result.json",
              "allure-report/index.html", ".venv/lib/x.py", "node_modules/x.js",
              "__pycache__/x.pyc", "evidence/run.log"):
        assert classify_excluded(p), p


def test_classify_owned_vs_unrelated():
    classifier = ChangeClassifier()
    status = GitStatus(entries=[
        GitStatusEntry(index="M", worktree=" ", path="tests/orangehrm_login.robot"),
        GitStatusEntry(index="M", worktree=" ", path="requirements.txt"),
    ])
    report = classifier.classify(
        status.entries,
        changeset=["tests/orangehrm_login.robot"],
        requirement="login",
    )
    assert report.owned == ["tests/orangehrm_login.robot"]
    assert report.unrelated == ["requirements.txt"]
    assert report.clean is False


def test_classify_excluded_never_in_owned():
    classifier = ChangeClassifier()
    status = GitStatus(entries=[
        GitStatusEntry(index="?", worktree="?", path="results/run/output.xml"),
    ])
    report = classifier.classify(
        status.entries, changeset=["results/run/output.xml"], requirement="x"
    )
    assert report.excluded == ["results/run/output.xml"]
    assert report.owned == []


def test_classify_shared_support_imported_by_owned():
    classifier = ChangeClassifier()
    entries = [
        GitStatusEntry(index="M", worktree=" ", path="tests/orangehrm_login.robot"),
        GitStatusEntry(index="M", worktree=" ", path="pages/orangehrm_login_page.robot"),
    ]
    # orangehrm_login.robot imports the login page object -> SHARED_SUPPORT.
    report = classifier.classify(
        entries, changeset=["tests/orangehrm_login.robot"], requirement="login"
    )
    assert report.owned == ["tests/orangehrm_login.robot"]
    assert report.shared_support == ["pages/orangehrm_login_page.robot"]
    assert report.clean is True


# ── Commit Planner ────────────────────────────────────────────────────────
class FakeGit:
    """In-memory fake of the GitAdapter surface the planner needs."""

    def __init__(self, entries=None):
        self._entries = entries or []
        self._branch_exists = True
        self._config = {"user.name": "Tester", "user.email": "t@example.com"}

    def status(self) -> GitStatus:
        return GitStatus(entries=list(self._entries))

    def config_set(self, key: str) -> bool:
        return self._config.get(key, False)

    def branch_exists(self, branch: str) -> bool:
        return self._branch_exists

    def ls_remote(self, branch: str, remote: str = "origin"):
        return "0" * 40


def clean_snapshot() -> dict:
    return {
        "automation_mode": "NEW_AUTOMATION",
        "final_gate": {"all_satisfied": True},
        "branch": {"decision": "feature/qa-auto-login", "exists": True},
        "review": {"verdict": "APPROVED"},
        "regression": {"total": 12, "failed": 0, "skipped": 0, "unresolved": 0},
        "docker": {"build_exit_code": 0, "run_exit_code": 0,
                   "robot_failed": 0, "robot_skipped": 0, "output_xml_exists": True},
        "healing_attempts": 0,
        "commit_authorized": True,
    }


def planner_entries() -> list:
    return [
        GitStatusEntry(index="M", worktree=" ", path="tests/orangehrm_login.robot"),
    ]


def test_validate_commit_message():
    assert validate_commit_message("feat(qa): add orangehrm login automation")
    assert validate_commit_message("fix(qa): correct admin page selector")
    assert validate_commit_message("refactor(qa): split login suite per requirement")
    assert not validate_commit_message("")
    assert not validate_commit_message("kick")
    assert not validate_commit_message("wip")
    assert not validate_commit_message("update")


def test_compose_commit_message_never_empty():
    assert compose_commit_message("login", "NEW_AUTOMATION").startswith("feat(qa):")
    assert compose_commit_message("login", "AUTOMATION_FIX").startswith("fix(qa):")
    assert compose_commit_message("login", "AUTOMATION_ENHANCEMENT", "logout").startswith("feat(qa):")


def test_planner_safe_when_all_gates_pass(tmp_path):
    planner = CommitPlanner(root=tmp_path)
    git = FakeGit(entries=planner_entries())
    plan = planner.plan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        state=clean_snapshot(),
        git=git,
        test_file="tests/orangehrm_login.robot",
    )
    assert plan.safe is True
    assert plan.files_to_stage == ["tests/orangehrm_login.robot"]
    assert plan.failed_gates == []
    # deletion must be staged honestly
    assert plan.deleted_files == []


def test_planner_blocks_unrelated_changes(tmp_path):
    planner = CommitPlanner(root=tmp_path)
    git = FakeGit(entries=[
        GitStatusEntry(index="M", worktree=" ", path="tests/orangehrm_login.robot"),
        GitStatusEntry(index="M", worktree=" ", path="Jenkinsfile"),
    ])
    plan = planner.plan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        state=clean_snapshot(),
        git=git,
        test_file="tests/orangehrm_login.robot",
    )
    assert plan.safe is False
    assert "no_unrelated_in_commit" in plan.failed_gates


def test_planner_blocks_when_final_gate_not_passed(tmp_path):
    planner = CommitPlanner(root=tmp_path)
    state = clean_snapshot()
    state["final_gate"] = {"all_satisfied": False}
    git = FakeGit(entries=planner_entries())
    plan = planner.plan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        state=state,
        git=git,
        test_file="tests/orangehrm_login.robot",
    )
    assert plan.safe is False
    assert "final_quality_gate_pass" in plan.failed_gates


def test_planner_blocks_secret_content(tmp_path):
    planner = CommitPlanner(root=tmp_path)
    secret_file = tmp_path / "tests" / "orangehrm_login.robot"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret_file.write_text(
        'password = "SuperSecret123"\n', encoding="utf-8"
    )
    git = FakeGit(entries=[
        GitStatusEntry(index="M", worktree=" ", path="tests/orangehrm_login.robot"),
    ])
    plan = planner.plan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        state=clean_snapshot(),
        git=git,
        test_file="tests/orangehrm_login.robot",
    )
    assert plan.safe is False
    assert plan.secrets_detected is True
    assert "no_secrets" in plan.failed_gates


def test_planner_blocks_deleted_unknown_branch_msg(tmp_path):
    planner = CommitPlanner(root=tmp_path)
    git = FakeGit(entries=[])
    git._branch_exists = False
    plan = planner.plan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        state=clean_snapshot(),
        git=git,
        test_file="tests/orangehrm_login.robot",
    )
    # listed deleted? none. With no status entry the file is still owned but the
    # branch doesn't exist -> gate fails.
    assert plan.safe is False
    assert any("branch" in g for g in plan.failed_gates)


# ── Git Delivery (dry-run + unsafe refusal) ───────────────────────────────
def test_delivery_dry_run_never_stages_or_commits(tmp_path):
    planner = CommitPlanner(root=tmp_path)
    git = FakeGit(entries=planner_entries())
    plan = planner.plan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        state=clean_snapshot(),
        git=git,
        test_file="tests/orangehrm_login.robot",
    )
    delivery = GitDelivery(git=git)
    attempt = delivery.deliver(plan, dry_run=True)
    assert attempt.dry_run is True
    assert attempt.committed is False
    assert attempt.commit_hash is None
    assert attempt.staged_paths == ["tests/orangehrm_login.robot"]
    assert any("dry_run" in r for r in attempt.reasons)


def test_delivery_refuses_unsafe_plan():
    from orchestra.commit_planner import CommitPlan

    plan = CommitPlan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        message="feat(qa): login",
        files_to_stage=[],
        failed_gates=["no_unrelated_in_commit"],
    )
    delivery = GitDelivery(git=FakeGit(entries=[]))
    attempt = delivery.deliver(plan)
    assert attempt.delivered is False
    assert any("unsafe_plan" in r for r in attempt.reasons)


def test_delivery_requires_exact_plan_staging(tmp_path):
    class GreedyGit(FakeGit):
        def stage(self, paths):
            return paths

        def staged_paths(self):
            return ["tests/orangehrm_login.robot", "unrelated/extra.py"]  # extra file

    gg = GreedyGit(entries=planner_entries())
    planner = CommitPlanner(root=tmp_path)
    plan = planner.plan(
        requirement="login",
        automation_mode="NEW_AUTOMATION",
        branch="feature/qa-auto-login",
        state=clean_snapshot(),
        git=gg,
        test_file="tests/orangehrm_login.robot",
    )
    assert plan.safe is True  # plan itself is clean
    delivery = GitDelivery(git=gg)
    attempt = delivery.deliver(plan)
    assert attempt.committed is False
    assert any("staged_mismatch" in r for r in attempt.reasons)


# ── CI Handoff / Delivery Verifier ────────────────────────────────────────
def test_ci_handoff_unverified_when_not_observable(tmp_path):
    git = FakeGit(entries=[])
    handoff = CIHandoff(git=git)
    ver = handoff.track("feature/qa-auto-login", "0" * 40)
    assert ver.status == "UNVERIFIED"
    assert ver.passed is False  # UNVERIFIED never PASS


def test_ci_verified_only_with_real_build_evidence():
    from orchestra.ci_handoff import CIVerification

    ver = CIVerification(status="UNVERIFIED")
    out = CIHandoff.verify_external(
        ver,
        build_url="https://jenkins/job/Robot-Playwright-Sanity/12",
        build_result="SUCCESS",
        failed_tests=0,
        total_tests=32,
        checkout_sha="abcd1234",
    )
    assert out.status == "PASS"
    assert out.passed is True

    ver2 = CIVerification(status="UNVERIFIED")
    out2 = CIHandoff.verify_external(
        ver2,
        build_url="https://jenkins/job/Robot-Playwright-Sanity/13",
        build_result="SUCCESS",
        failed_tests=2,
        total_tests=32,
    )
    assert out2.status == "FAIL"
    assert out2.passed is False


def test_ci_verified_without_build_url_is_unverified():
    from orchestra.ci_handoff import CIVerification

    ver = CIVerification(status="UNVERIFIED")
    out = CIHandoff.verify_external(
        ver, build_url="", build_result="SUCCESS", failed_tests=0, total_tests=32
    )
    assert out.status == "UNVERIFIED"
    assert out.passed is False


def test_delivery_verifier_remote_head_mismatch():
    class MismatchGit(FakeGit):
        def ls_remote(self, branch: str, remote: str = "origin"):
            return "f" * 40  # remote differs from local commit

    verifier = DeliveryVerifier(git=MismatchGit(entries=[]))
    ver = verifier.verify_push("feature/qa-auto-login", "0" * 40)
    assert ver.verified is False
    assert any("remote_head_mismatch" in r for r in ver.reasons)


def test_ci_healing_tracker_cap():
    tracker = CIHealingTracker()
    assert tracker.can_heal() is True
    for _ in range(3):
        tracker.start_attempt()
    assert tracker.attempts() == 3
    assert tracker.can_heal() is False
    with pytest.raises(RuntimeError, match="cap exceeded"):
        tracker.start_attempt()


# ── Kernel commit / push / ci wiring ──────────────────────────────────────
def _walk_to_final_gate(k: Kernel) -> None:
    k.classify("NEW_AUTOMATION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("PARTIAL")
    k.branch("feature/qa-auto-login")
    k.confirm_branch_exists("feature/qa-auto-login", git_exists=True)
    for stage, src in [
        ("PLANNING", "BRANCH_DECISION"),
        ("EXPLORATION", "PLANNING"),
        ("GENERATION", "EXPLORATION"),
    ]:
        k.store.transition(stage, allowed=k.registry.allowed(src, stage))
    k.record_local_execution(total=3, failed=0, skipped=0)
    k.record_regression(total=12, failed=0, skipped=0)
    k.record_review_from_agent(_approved_result())
    k.review("APPROVED")
    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0, robot_skipped=0,
             output_xml_exists=True)
    k.allure(results_present=True, status_parity=True, credential_leak=False)
    k.final_gate()


def _approved_result():
    from orchestra.adapters.agent_cli import AgentResult

    return AgentResult(agent="reviewer", exit_code=0, session_id="sess-1",
                       text="APPROVED: quality gates satisfied", raw_json="")


def _safe_plan_record() -> dict:
    return {
        "requirement": "login",
        "automation_mode": "NEW_AUTOMATION",
        "branch": "feature/qa-auto-login",
        "message": "feat(qa): login automation",
        "files_to_stage": ["tests/orangehrm_login.robot"],
        "safe": True,
        "secrets_detected": False,
        "failed_gates": [],
    }


def test_kernel_commit_requires_authorization_and_plan():
    store = StateStore("delivery-kernel-0001")
    k = Kernel(store=store)
    _walk_to_final_gate(k)
    assert store.current_state() == "FINAL_QUALITY_GATE"

    k.record_commit_plan(_safe_plan_record())
    # without commit_authorized -> gate_commit_auth fails
    with pytest.raises(RuntimeError, match="Gate FAILED: gate_commit_auth"):
        k.commit("a" * 40, staged_files=["tests/orangehrm_login.robot"])


def test_kernel_commit_push_ci_full_chain():
    store = StateStore("delivery-kernel-0002")
    k = Kernel(store=store)
    _walk_to_final_gate(k)
    k.record_commit_plan(_safe_plan_record())
    k.authorize_commit(True)
    k.commit("a" * 40, staged_files=["tests/orangehrm_login.robot"])
    assert store.current_state() == "COMMIT"
    assert store.get("commit")["hash"] == "a" * 40
    assert store.get("commit_authorized") is True

    k.push(verified=True, remote_head="a" * 40, branch="feature/qa-auto-login")
    assert store.current_state() == "PUSH"
    assert store.get("push")["verified"] is True

    k.ci_validation(
        status="PASS",
        build_result="SUCCESS",
        build_url="https://jenkins/job/Robot-Playwright-Sanity/1",
        test_counts={"total": 32, "failed": 0},
        checkout_sha="a" * 40,
    )
    assert store.current_state() == "CI_VALIDATION"
    assert store.get("ci_validation")["status"] == "PASS"


def test_kernel_ci_unverified_blocks_validation_gate():
    store = StateStore("delivery-kernel-0003")
    k = Kernel(store=store)
    _walk_to_final_gate(k)
    k.record_commit_plan(_safe_plan_record())
    k.authorize_commit(True)
    k.commit("b" * 40, staged_files=["tests/orangehrm_login.robot"])
    k.push(verified=True, remote_head="b" * 40, branch="feature/qa-auto-login")
    with pytest.raises(RuntimeError, match="Gate FAILED: gate_ci_verified"):
        k.ci_validation(
            status="UNVERIFIED", build_result=None, build_url=None,
            test_counts={}, checkout_sha="b" * 40,
        )


def test_kernel_ci_healing_cap_blocks_on_three():
    store = StateStore("delivery-kernel-0004")
    k = Kernel(store=store)
    _walk_to_final_gate(k)
    k.record_commit_plan(_safe_plan_record())
    k.authorize_commit(True)
    k.commit("c" * 40, staged_files=["tests/orangehrm_login.robot"])
    k.push(verified=True, remote_head="c" * 40, branch="feature/qa-auto-login")
    # three failed CI runs each heal (attempts 1..3 allowed)
    for i in range(1, 4):
        k.clear_execution_marker("ci_healing")
        assert k.ci_validation(
            status="FAIL", build_result="FAILURE",
            build_url="https://jenkins/job/Robot-Playwright-Sanity/1",
            test_counts={"total": 32, "failed": 1}, checkout_sha="c" * 40,
        ) == "FAIL"
        assert store.current_state() == "CI_VALIDATION"
        k.ci_healing(i)
        assert store.current_state() == "CI_HEALING"
    # a 4th failed validation has no healing budget left -> STOP (CICD_LOCKED)
    k.clear_execution_marker("ci_healing")
    with pytest.raises(RuntimeError, match="Gate FAILED: gate_ci_healing_cap"):
        k.ci_validation(
            status="FAIL", build_result="FAILURE",
            build_url="https://jenkins/job/Robot-Playwright-Sanity/1",
            test_counts={"total": 32, "failed": 1}, checkout_sha="c" * 40,
        )
    assert store.get("ci_healing_attempts") == 3


def test_stage_registry_has_delivery_edges():
    reg = StageRegistry()
    assert reg.allowed("FINAL_QUALITY_GATE", "COMMIT")
    assert reg.allowed("COMMIT", "PUSH")
    assert reg.allowed("PUSH", "CI_VALIDATION")
    assert reg.allowed("CI_VALIDATION", "CI_HEALING")
    assert reg.allowed("CI_HEALING", "CI_VALIDATION")
    assert reg.allowed("FINAL_QUALITY_GATE", "COMPLETED")  # REGRESSION terminator
    assert reg.allowed("CI_VALIDATION", "PR_READY")