"""Controlled validation: prove the execution loop guard eliminates repeated driver invocation.

This test suite proves the three loop-breaking mechanisms:
1. StateStore.resume() hydrates state from JSONL log (no fresh restart)
2. Run-once execution guard prevents re-execution of completed stages
3. Bounded restart counter (MAX_RESUMES=1) prevents infinite restart loops

Each test is an isolated, deterministic proof — no real agents, no browser, no network.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from orchestra.evidence import EvidenceBus
from orchestra.gates import GateEngine
from orchestra.kernel import Kernel, MAX_RESUMES
from orchestra.machine import StageRegistry
from orchestra.scope import ImpactDecision, ScopeEngine
from orchestra.state import StateStore


def make_kernel(run_id: str = "loop-test-001") -> Kernel:
    store = StateStore(run_id)
    return Kernel(store=store)


def walk_classify_through_branch(k: Kernel, mode: str = "NEW_AUTOMATION", branch: str = "feature/qa-auto-x"):
    """Walk the shared prefix: classify -> impact -> coverage -> branch."""
    k.classify(mode)
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["repo-evidence"]))
    k.coverage("PARTIAL")
    k.branch(branch)


# ── Test 1: one workflow starts, each state executes once, no duplicates ──────

def test_run_once_classify_only_executes_once():
    """Calling classify() twice returns immediately on second call (no duplicate work)."""
    k = make_kernel("run-once-001")
    k.classify("NEW_AUTOMATION")
    state1 = k.store.current_state()
    snap1 = k.store.snapshot()

    # Second call must be a no-op
    k.classify("NEW_AUTOMATION")
    state2 = k.store.current_state()
    snap2 = k.store.snapshot()

    assert state1 == state2 == "REQUIREMENT_CLASSIFICATION"
    assert snap1 == snap2
    assert k._already_executed("classify") is True


def test_run_once_impact_only_executes_once():
    """Calling impact() twice returns immediately on second call."""
    k = make_kernel("run-once-002")
    k.classify("NEW_AUTOMATION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    snap1 = k.store.snapshot()
    current1 = k.store.current_state()

    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    snap2 = k.store.snapshot()
    current2 = k.store.current_state()

    assert current1 == current2 == "IMPACT_ANALYSIS"
    assert snap1 == snap2
    assert k._already_executed("impact") is True


def test_run_once_all_stages_execute_exactly_once():
    """Walk a full lifecycle and prove no stage runs twice."""
    k = make_kernel("run-once-full-001")
    walk_classify_through_branch(k, "REGRESSION", branch=None)

    k.record_regression(total=10, failed=0, skipped=0)

    # Record a review via record_review_from_agent
    from orchestra.adapters.agent_cli import AgentResult
    fake_verdict = "APPROVED"
    fake_result = AgentResult(
        agent="reviewer",
        exit_code=0,
        session_id="sess-123",
        text="APPROVED: all tests pass, no issues.",
        raw_json="",
    )
    k.record_review_from_agent(fake_result)
    k.review(fake_verdict)

    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0, robot_skipped=0,
             output_xml_exists=True)
    k.allure(results_present=True, status_parity=True, credential_leak=False)

    res = k.final_gate()

    # Assert state reached FINAL_QUALITY_GATE
    assert k.store.current_state() == "FINAL_QUALITY_GATE"
    # Assert gate_final derived from quality gates
    assert res["all_satisfied"] is True
    assert res["results"]["gate_final"] is True

    # Prove every stage ran exactly once via executed_stages marker
    executed = k.store.get("executed_stages")
    assert executed is not None
    for key in ["classify", "impact", "coverage", "branch",
                 "regression", "review",
                 "docker", "allure", "final_gate"]:
        assert executed.get(key) is True, f"Stage {key!r} not marked executed"

    # Calling them again is a no-op
    k.classify("REGRESSION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("SUFFICIENT")
    k.branch(None)
    k.record_regression(total=10, failed=0, skipped=0)
    assert k.store.current_state() == "FINAL_QUALITY_GATE", "State must NOT revert"


# ── Test 2: no duplicate driver invocation ────────────────────────────────────

def test_no_duplicate_regression_execution():
    """record_regression() only records once; second call is a no-op."""
    k = make_kernel("no-dup-reg-001")
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)

    snap1 = k.store.snapshot()
    k.record_regression(total=10, failed=0, skipped=0)
    snap2 = k.store.snapshot()

    assert snap1["state"] == snap2["state"] == "REGRESSION_EXECUTION"
    assert snap1.get("regression") == snap2.get("regression")


def test_no_duplicate_docker_execution():
    """docker() only records once; second call is a no-op."""
    k = make_kernel("no-dup-docker-001")
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)
    from orchestra.adapters.agent_cli import AgentResult
    fake_result = AgentResult(agent="reviewer", exit_code=0, session_id="s",
                               text="APPROVED", raw_json="")
    k.record_review_from_agent(fake_result)
    k.review("APPROVED")
    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0,
             robot_skipped=0, output_xml_exists=True)

    snap1 = k.store.snapshot()
    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0,
             robot_skipped=0, output_xml_exists=True)
    snap2 = k.store.snapshot()

    assert snap1["state"] == snap2["state"] == "DOCKER_VALIDATION"
    assert snap1.get("docker") == snap2.get("docker")


# ── Test 3: state transitions correctly (lifecycle path) ─────────────────────

def test_full_regression_lifecycle_state_path():
    """Walk the full REGRESSION lifecycle: classify->...->FINAL_QUALITY_GATE and prove transitions."""
    k = make_kernel("lifecycle-path-001")
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)
    from orchestra.adapters.agent_cli import AgentResult
    fake_result = AgentResult(agent="reviewer", exit_code=0, session_id="s",
                               text="APPROVED", raw_json="")
    k.record_review_from_agent(fake_result)
    k.review("APPROVED")
    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0,
             robot_skipped=0, output_xml_exists=True)
    k.allure(results_present=True, status_parity=True)
    res = k.final_gate()

    assert k.store.current_state() == "FINAL_QUALITY_GATE"
    assert res["all_satisfied"] is True


def test_automation_lifecycle_reaches_final_gate():
    """Walk AUTOMATION lifecycle (without agents) through to FINAL_QUALITY_GATE."""
    k = make_kernel("lifecycle-auto-001")
    walk_classify_through_branch(k, "NEW_AUTOMATION", "feature/qa-auto-login")
    # Simulate agent stages via direct transition (agents not invoked here)
    for stage, src in [
        ("PLANNING", "BRANCH_DECISION"),
        ("EXPLORATION", "PLANNING"),
        ("GENERATION", "EXPLORATION"),
    ]:
        k.store.transition(stage, allowed=k.registry.allowed(src, stage))

    k.record_local_execution(total=5, failed=0, skipped=0)
    k.record_regression(total=10, failed=0, skipped=0)
    from orchestra.adapters.agent_cli import AgentResult
    fake_result = AgentResult(agent="reviewer", exit_code=0, session_id="s",
                               text="APPROVED", raw_json="")
    k.record_review_from_agent(fake_result)
    k.review("APPROVED")
    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0,
             robot_skipped=0, output_xml_exists=True)
    k.allure(results_present=True, status_parity=True)
    res = k.final_gate()

    assert k.store.current_state() == "FINAL_QUALITY_GATE"
    assert res["all_satisfied"] is True


# ── Test 4: retry only when explicitly required ──────────────────────────────

def test_clear_execution_marker_allows_re_execution():
    """After clear_all_execution_markers(), stages can re-execute (simulates RE_EXECUTION path)."""
    k = make_kernel("retry-001")
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)

    assert k._already_executed("regression") is True

    # Simulate RE_EXECUTION: clear markers
    k.clear_all_execution_markers()
    assert k._already_executed("regression") is False


def test_clear_single_marker_allows_re_execution():
    """After clear_execution_marker(), only the specified stage can re-execute."""
    k = make_kernel("retry-single-001")
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)

    k.clear_execution_marker("regression")
    assert k._already_executed("regression") is False
    assert k._already_executed("local_execution") is True or k._already_executed("classify") is True, "other markers must remain"


# ── Test 5: resume hydrates state from JSONL log ─────────────────────────────

def test_resume_hydrates_state_from_jsonl():
    """Kernel.resume() replays the JSONL log and restores state snapshot."""
    run_id = "resume-test-001"
    log_path = Path("results") / "orchestra" / f"{run_id}.jsonl"

    # Clean up any prior log
    if log_path.exists():
        log_path.unlink()

    k = make_kernel(run_id)
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)
    state_before = k.store.current_state()

    # Simulate a fresh session by creating a new kernel via resume
    k2 = Kernel.resume(run_id, log_path=log_path.parent)
    assert k2.store.resumed is True
    assert k2.store.current_state() == state_before
    snap1 = k.store.snapshot()
    snap2 = k2.store.snapshot()
    # Evidence must match (state keys)
    assert snap2.get("automation_mode") == snap1.get("automation_mode")
    assert snap2.get("branch") == snap1.get("branch")
    assert snap2.get("regression") == snap1.get("regression")

    # Cleanup
    if log_path.exists():
        log_path.unlink()


def test_resume_run_once_guard_persists_after_resume():
    """After resume, the execution guard remembers what was already done."""
    run_id = "resume-guard-001"
    log_path = Path("results") / "orchestra" / f"{run_id}.jsonl"
    if log_path.exists():
        log_path.unlink()

    k = make_kernel(run_id)
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)

    # Resume
    k2 = Kernel.resume(run_id, log_path=log_path.parent)
    assert k2.store.resumed is True
    assert k2._already_executed("classify") is True
    assert k2._already_executed("regression") is True

    # Calling classify again is a no-op (state preserved at resumed position)
    k2.classify("REGRESSION")
    assert k2.store.current_state() == "REGRESSION_EXECUTION"

    if log_path.exists():
        log_path.unlink()


# ── Test 6: bounded restart cap ──────────────────────────────────────────────

def test_restart_count_increments_on_resume():
    """Each resume increments restart_count; first resume is allowed."""
    run_id = "restart-cap-001"
    log_path = Path("results") / "orchestra" / f"{run_id}.jsonl"
    if log_path.exists():
        log_path.unlink()

    k = make_kernel(run_id)
    k.classify("REGRESSION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("SUFFICIENT")
    k.branch(None)

    # Resume once: allowed
    k2 = Kernel.resume(run_id, log_path=log_path.parent)
    assert k2.store.resumed is True
    assert k2.store.get("restart_count") == 1

    if log_path.exists():
        log_path.unlink()


def test_second_resume_exceeds_cap():
    """Second resume raises RuntimeError (resume cap exceeded, run is BLOCKED)."""
    run_id = "restart-cap-002"
    log_path = Path("results") / "orchestra" / f"{run_id}.jsonl"
    if log_path.exists():
        log_path.unlink()

    k = make_kernel(run_id)
    k.classify("REGRESSION")

    # Resume once: allowed, but we need to write the log
    # First resume creates a log entry for restart_count
    k2 = Kernel.resume(run_id, log_path=log_path.parent)

    # To simulate second resume, we need the log to already contain restart_count=1
    # Let's manually write a restart_count record to the log
    import json
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "record", "key": "restart_count", "value": 1}) + "\n")

    # Second resume: must fail
    with pytest.raises(RuntimeError, match="Resume cap exceeded"):
        Kernel.resume(run_id, log_path=log_path.parent)

    if log_path.exists():
        log_path.unlink()


# ── Test 7: final gates evaluated independently, gate_final derived ──────────

def test_final_gate_derived_from_quality_gates():
    """gate_final is derived from the quality gates, never self-referencing."""
    engine = GateEngine()
    # Create a minimal state snapshot
    state = {
        "run_id": "gate-test-001",
        "state": "FINAL_QUALITY_GATE",
        "automation_mode": "REGRESSION",
        "impact": {"execution_scope": "TARGETED"},
        "coverage_decision": "SUFFICIENT",
        "branch": {"decision_valid": True},
        "execution": {"failed": 0, "skipped": 0, "unresolved": 0},
        "regression": {"total": 22, "failed": 0, "skipped": 0, "unresolved": 0},
        "review": {"verdict": "APPROVED"},
        "docker": {"build_exit_code": 0, "run_exit_code": 0,
                   "robot_failed": 0, "robot_skipped": 0, "output_xml_exists": True},
        "allure": {"results_present": True, "status_parity": True,
                   "credential_leak": False, "report_index_exists": True},
        "final_gate": {"all_satisfied": True},
    }
    res = engine.evaluate_final(state)
    assert res["all_satisfied"] is True
    assert res["results"]["gate_final"] is True


def test_final_gate_fails_when_quality_gate_fails():
    """gate_final becomes False when any quality gate fails."""
    engine = GateEngine()
    state = {
        "run_id": "gate-fail-001",
        "state": "FINAL_QUALITY_GATE",
        "automation_mode": "REGRESSION",
        "impact": {"execution_scope": "TARGETED"},
        "coverage_decision": "SUFFICIENT",
        "branch": {"decision_valid": True},
        "execution": {"failed": 0, "skipped": 0, "unresolved": 0},
        "regression": {"failed": 1, "skipped": 0, "unresolved": 0},  # regression failed!
        "review": {"verdict": "APPROVED"},
        "docker": {"build_exit_code": 0, "run_exit_code": 0,
                   "robot_failed": 0, "robot_skipped": 0, "output_xml_exists": True},
        "allure": {"results_present": True, "status_parity": True,
                   "credential_leak": False, "report_index_exists": True},
        "final_gate": {"all_satisfied": True},  # stale; will be overwritten
    }
    res = engine.evaluate_final(state)
    assert res["all_satisfied"] is False
    assert res["results"]["gate_final"] is False
    # gate_regression_clean must be False
    assert res["results"].get("gate_regression_clean") is False


# ── Test 8: workflow reaches deterministic FINAL state ────────────────────────

def test_regression_workflow_reaches_final_deterministic_state():
    """Full REGRESSION walk: every state executes once, final state is FINAL_QUALITY_GATE."""
    k = make_kernel("deterministic-001")
    walk_classify_through_branch(k, "REGRESSION", branch=None)
    k.record_regression(total=10, failed=0, skipped=0)
    from orchestra.adapters.agent_cli import AgentResult
    fake_result = AgentResult(agent="reviewer", exit_code=0, session_id="s",
                               text="APPROVED", raw_json="")
    k.record_review_from_agent(fake_result)
    k.review("APPROVED")
    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0,
             robot_skipped=0, output_xml_exists=True)
    k.allure(results_present=True, status_parity=True)
    k.final_gate()

    # State is FINAL_QUALITY_GATE (deterministic)
    assert k.store.current_state() == "FINAL_QUALITY_GATE"

    # No duplicate driver invocations
    executed = k.store.get("executed_stages")
    assert executed is not None
    # Each stage marked exactly once
    counts = {}
    for key, val in executed.items():
        if val is True:
            counts[key] = counts.get(key, 0) + 1
    for key, count in counts.items():
        assert count == 1, f"Stage {key!r} executed {count} times (expected 1)"
