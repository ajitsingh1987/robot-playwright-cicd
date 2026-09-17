"""Remediation tests: final-gate independence, reviewer integrity, scope triggers,
branch decision-vs-existence, Docker evidence, and legal transitions."""
from __future__ import annotations

import pytest

from orchestra.adapters.agent_cli import AgentResult
from orchestra.adapters.allure import AllureRunner
from orchestra.adapters.docker import DockerEvidence, DockerRunner
from orchestra.evidence import EvidenceBus
from orchestra.gates import GateEngine
from orchestra.kernel import Kernel
from orchestra.machine import StageRegistry
from orchestra.review import parse_review_verdict
from orchestra.scope import ImpactDecision, ScopeEngine
from orchestra.state import StateError, StateStore


def make_kernel() -> Kernel:
    return Kernel(store=StateStore("test-remed-0001"), registry=StageRegistry(),
                  gates=GateEngine(), evidence=EvidenceBus(StateStore("test-remed-ev")))


def walk_clean_to_final(k: Kernel):
    """Walk a fully clean NEW_AUTOMATION run to ALLURE_VALIDATION (no agents)."""
    k.classify("NEW_AUTOMATION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("MISSING")
    k.branch("feature/qa-auto-x")
    for stage, src in [("PLANNING", "BRANCH_DECISION"),
                       ("EXPLORATION", "PLANNING"),
                       ("GENERATION", "EXPLORATION")]:
        k.store.transition(stage, allowed=k.registry.allowed(src, stage))
    k.record_local_execution(total=1, failed=0, skipped=0)
    k.record_regression(total=35, failed=0, skipped=0, full_run_completed=True)
    k.review("APPROVED")
    k.docker(build_exit_code=0, run_exit_code=0, robot_failed=0, robot_skipped=0,
             output_xml_exists=True, output_xml="results/output.xml")
    k.store.record("allure", {"results_present": True, "status_parity": True,
                              "credential_leak": False, "report_index_exists": True})
    k.store.transition("ALLURE_VALIDATION",
                       allowed=k.registry.allowed("DOCKER_VALIDATION", "ALLURE_VALIDATION"))


# 1. FINAL QUALITY GATE independence ---------------------------------------
def test_final_gate_passes_without_commit_or_push():
    k = make_kernel()
    walk_clean_to_final(k)
    final = k.final_gate()
    # Mandatory condition: clean run can PASS the final quality gate with NO commit/push.
    assert final["all_satisfied"] is True
    assert final["results"]["gate_final"] is True
    assert k.store.get("commit") is None
    assert k.store.get("push") is None
    assert k.store.get("branch", {}).get("exists") is False  # exists must not be faked


def test_final_evaluation_excludes_authorization_gates():
    k = make_kernel()
    walk_clean_to_final(k)
    results = k.gates.evaluate_final(k.store.snapshot())["results"]
    assert "gate_commit_auth" not in results
    assert "gate_push_branch" not in results
    assert results["gate_final"] is True


def test_final_gate_blocked_when_regression_non_clean():
    k = make_kernel()
    walk_clean_to_final(k)
    k.store.record("regression", {"total": 35, "failed": 1, "skipped": 0,
                                  "unresolved": 0, "exit_code": 1,
                                  "full_run_completed": True})
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_regression_clean", snap) is False
    final = k.gates.evaluate_final(snap)
    assert final["all_satisfied"] is False
    assert final["results"]["gate_final"] is False


# 2/3. REVIEWER INTEGRITY --------------------------------------------------
def test_review_verdict_parsed_reject():
    text = (
        "I reviewed the run. **Verdict: REJECT**.\n"
        "The branch does not exist and the work is not committed."
    )
    assert parse_review_verdict(text) == "REJECT"


def test_review_verdict_parsed_approved():
    text = (
        "All checks passed and evidence is complete.\n"
        "Verdict: APPROVED\n"
    )
    assert parse_review_verdict(text) == "APPROVED"


def test_review_verdict_unknown_when_ambiguous():
    assert parse_review_verdict("no clear verdict present") == "UNKNOWN"
    assert parse_review_verdict("") == "UNKNOWN"


def test_review_reject_propagates_to_gate_and_blocks_final():
    k = make_kernel()
    walk_clean_to_final(k)  # moves state to ALLURE_VALIDATION
    # emulate a real reviewer that REJECTED (state stays at ALLURE_VALIDATION)
    rev = k.record_review_from_agent(AgentResult(
        agent="reviewer", exit_code=0,
        session_id="ses-reject-1",
        text="**Verdict: REJECT** branch not created, no commit."))
    assert rev == "REJECT"
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_reviewer", snap) is False
    final = k.gates.evaluate_final(snap)
    assert final["all_satisfied"] is False


def test_review_approved_not_hardcoded_but_parsed():
    k = make_kernel()
    walk_clean_to_final(k)
    rev = k.record_review_from_agent(AgentResult(
        agent="reviewer", exit_code=0,
        session_id="ses-approve-1",
        text="Everything is consistent. **Verdict: APPROVED**"))
    assert rev == "APPROVED"
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_reviewer", snap) is True
    assert k.store.get("review")["session_id"] == "ses-approve-1"
    assert "session_id" in k.store.get("review")["evidence"]


# 4. SCOPE ENGINE safety triggers ------------------------------------------
@pytest.mark.parametrize("trigger", [
    ("shared_core_component_changed", True),
    ("shared_application_area_risk", True),
    ("insufficient_evidence_to_exclude", True),
    ("narrower_scope_failed", True),
])
def test_scope_safety_triggers_force_full(trigger):
    eng = ScopeEngine()
    field, value = trigger
    d = ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                       scope_evidence=["e"], **{field: value})
    res = eng.decide(d)
    assert res.execution_scope == "FULL_REGRESSION"
    assert res.full_regression_needed is True


def test_scope_low_confidence_and_missing_evidence_force_full():
    eng = ScopeEngine()
    assert eng.decide(ImpactDecision(confidence="LOW", scope_evidence=["e"])).execution_scope == "FULL_REGRESSION"
    assert eng.decide(ImpactDecision(confidence="HIGH")).execution_scope == "FULL_REGRESSION"


def test_scope_shared_application_area_full():
    eng = ScopeEngine()
    # login/logout is a shared authentication area -> FULL_REGRESSION
    d = ImpactDecision(confidence="HIGH", impacted_tests=["tests/orangehrm_qa_e2e_login_logout.robot"],
                       scope_evidence=["shared auth area"], shared_application_area_risk=True)
    assert eng.decide(d).execution_scope == "FULL_REGRESSION"


def test_scope_targeted_only_when_no_trigger():
    eng = ScopeEngine()
    d = ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                       scope_evidence=["e"])
    assert eng.decide(d).execution_scope == "TARGETED"


def test_scope_impacted_when_multiple_suites():
    eng = ScopeEngine()
    d = ImpactDecision(confidence="MEDIUM",
                       impacted_tests=["tests/a.robot", "tests/b.robot"],
                       scope_evidence=["e"])
    assert eng.decide(d).execution_scope == "IMPACTED_REGRESSION"


# 5. BRANCH decision vs existence ------------------------------------------
def test_branch_decision_never_implies_existence():
    k = make_kernel()
    k.classify("NEW_AUTOMATION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("MISSING")
    k.branch("feature/qa-auto-x")
    assert k.store.get("branch")["decision"] == "feature/qa-auto-x"
    assert k.store.get("branch")["exists"] is False  # decision alone is not existence


def test_branch_exists_only_after_git_confirmation():
    k = make_kernel()
    k.classify("NEW_AUTOMATION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("MISSING")
    k.branch("feature/qa-auto-x")
    k.confirm_branch_exists("feature/qa-auto-x", git_exists=False)
    assert k.store.get("branch")["exists"] is False
    k.confirm_branch_exists("feature/qa-auto-x", git_exists=True)
    assert k.store.get("branch")["exists"] is True


def test_branch_exists_requires_decided_name():
    k = make_kernel()
    k.classify("REGRESSION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("SUFFICIENT")
    k.branch(None)
    with pytest.raises(ValueError):
        k.confirm_branch_exists(None, git_exists=True)


# 6. DOCKER evidence validation --------------------------------------------
def test_docker_gate_requires_real_build_and_run():
    k = make_kernel()
    walk_clean_to_final(k)
    # only docker CLI availability recorded but no real build/run evidence
    k.store.record("docker", {"exit_code": 0, "failed": 0, "total": 0})
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_docker_clean", snap) is False


def test_docker_gate_passes_with_real_evidence():
    k = make_kernel()
    walk_clean_to_final(k)
    # gate only inspects the recorded state dict; record the full real-evidence keys
    k.store.record("docker", {"build_exit_code": 0, "run_exit_code": 0,
                              "robot_failed": 0, "robot_skipped": 0,
                              "unresolved": 0, "output_xml_exists": True,
                              "output_xml": "results/output.xml"})
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_docker_clean", snap) is True


def test_docker_evidence_clean_flag():
    ev = DockerEvidence(built=True, ran=True, build_exit_code=0, run_exit_code=0,
                        failed=0, skipped=0, output_xml="results/output.xml")
    assert ev.clean is True
    ev2 = DockerEvidence(built=True, ran=True, build_exit_code=0, run_exit_code=1,
                         failed=1, skipped=0, output_xml="results/output.xml")
    assert ev2.clean is False


# 7/8. transitions ---------------------------------------------------------
def test_final_gate_self_transition_disallowed():
    k = make_kernel()
    with pytest.raises(StateError):
        k.store.transition("FINAL_QUALITY_GATE", allowed=k.registry.allowed("FINAL_QUALITY_GATE", "FINAL_QUALITY_GATE"))


# 9. GATE/REPORTING NEVER TRIGGERS EXECUTION (loop-elimination guarantee) ---
def test_gate_evaluation_never_executes_subprocess(monkeypatch):
    """evaluate_gate/evaluate_stage/evaluate_final are pure predicates."""
    import subprocess

    k = make_kernel()
    walk_clean_to_final(k)
    snap = k.store.snapshot()

    calls = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError("gate evaluation must never shell out")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    for g in ("gate_regression_clean", "gate_docker_clean", "gate_allure", "gate_reviewer"):
        k.gates.evaluate_gate(g, snap)
    k.gates.evaluate_stage("ALLURE_VALIDATION", snap)
    k.gates.evaluate_final(snap)
    assert calls == []


def test_report_validation_never_executes_subprocess(monkeypatch, tmp_path):
    """Allure validate()/scan_for_credentials() never launch a process."""
    import subprocess

    from orchestra.adapters.allure import AllureResult

    calls = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError("reporting must never shell out")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)

    runner = AllureRunner(results_dir=tmp_path)
    res = AllureResult(
        exit_code=0, results_present=True,
        results_dir=str(tmp_path / "allure-results"),
        report_dir=str(tmp_path / "allure-report"),
    )
    (tmp_path / "allure-report").mkdir(parents=True, exist_ok=True)
    (tmp_path / "allure-report" / "index.html").write_text("<html></html>", encoding="utf-8")
    validated = runner.validate(res)
    assert validated.report_dir is not None
    runner.scan_for_credentials(tmp_path)
    assert calls == []


def test_kernel_invoke_agent_requires_evidence_to_advance():
    """invoke_agent must NOT advance state on a fabricated/empty agent result."""
    from orchestra.adapters.agent_cli import AgentCLI

    class FakeCLI(AgentCLI):
        def run_agent(self, agent, message, *, timeout=None, depth=1, output_file=None):
            return AgentResult(agent=agent, exit_code=0, session_id=None, text="")

    k = make_kernel()
    k.agent_cli = FakeCLI()
    k.classify("NEW_AUTOMATION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("MISSING")
    k.branch("feature/qa-auto-x")
    k.store.transition("PLANNING", allowed=k.registry.allowed("BRANCH_DECISION", "PLANNING"))
    with pytest.raises(RuntimeError):
        k.invoke_agent("planner", "PLANNING", "plan this")
    assert k.store.current_state() == "PLANNING"  # never advanced
