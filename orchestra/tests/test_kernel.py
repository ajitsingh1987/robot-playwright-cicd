"""Unit tests for the orchestration kernel (state machine, gates, scope, healing)."""
from __future__ import annotations

import pytest

from orchestra.evidence import EvidenceBus
from orchestra.gates import GateEngine
from orchestra.healing import HealingCounter
from orchestra.kernel import Kernel
from orchestra.machine import StageRegistry
from orchestra.scope import ImpactDecision, ScopeEngine
from orchestra.state import StateError, StateStore


def make_kernel() -> Kernel:
    store = StateStore("test-run-0001")
    registry = StageRegistry()
    gates = GateEngine()
    evidence = EvidenceBus(store)
    return Kernel(store=store, registry=registry, gates=gates, evidence=evidence)


def test_disallowed_transition_raises():
    store = StateStore("test-run-0002")
    with pytest.raises(StateError):
        store.transition("FINAL_QUALITY_GATE", allowed=False)


def classify_impact_coverage_branch(k: Kernel, mode: str, branch_name=None):
    """Walk the shared prefix: classify -> impact -> coverage -> branch."""
    k.classify(mode)
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("PARTIAL")
    k.branch(branch_name)


def walk_to_generation(k: Kernel, branch_name="feature/qa-auto-x"):
    """Walk AUTOMATION prefix: classify .. branch -> planning -> exploration -> generation."""
    classify_impact_coverage_branch(k, "NEW_AUTOMATION", branch_name)
    for stage, src in [
        ("PLANNING", "BRANCH_DECISION"),
        ("EXPLORATION", "PLANNING"),
        ("GENERATION", "EXPLORATION"),
    ]:
        k.store.transition(stage, allowed=k.registry.allowed(src, stage))


def test_stage_registry_linear_edges():
    reg = StageRegistry()
    assert reg.allowed("REQUIREMENT_RECEIVED", "REQUIREMENT_CLASSIFICATION")
    assert reg.allowed("REVIEW", "DOCKER_VALIDATION")
    assert reg.allowed("DOCKER_VALIDATION", "ALLURE_VALIDATION")
    assert reg.allowed("REQUIREMENT_RECEIVED", "DOCKER_VALIDATION") is False
    with pytest.raises(StateError):
        reg.allowed("REQUIREMENT_RECEIVED", "NOT_A_REAL_STAGE")  # unknown target


def test_gate_classification_and_branch_gates():
    k = make_kernel()
    k.classify("NEW_AUTOMATION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"]))
    k.coverage("MISSING")
    k.branch("feature/qa-auto-x")
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_classified", snap) is True
    assert k.gates.evaluate_gate("gate_branch_derived", snap) is True


def test_regression_mode_never_branches():
    k = make_kernel()
    k.classify("REGRESSION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("SUFFICIENT")
    k.branch(None)
    assert k.store.get("branch")["decision"] is None
    assert k.store.get("branch")["exists"] is False
    # REGRESSION + SUFFICIENT must terminate at COMPLETED (no commit/push)
    assert k.registry.allowed("BRANCH_DECISION", "COMPLETED") is True


def test_regression_mode_branch_forbidden():
    k = make_kernel()
    k.classify("REGRESSION")
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("SUFFICIENT")
    with pytest.raises(ValueError):
        k.branch("feature/qa-auto-x")


def test_automation_mode_requires_feature_branch():
    k = make_kernel()
    k.classify("NEW_AUTOMATION")
    with pytest.raises(ValueError):
        k.branch(None)
    with pytest.raises(ValueError):
        k.branch("main")


def test_healing_cap_automation_only():
    k = make_kernel()
    k.classify("NEW_AUTOMATION")
    hc = HealingCounter(k.store)
    assert hc.can_heal("NEW_AUTOMATION") is True
    assert hc.can_heal("REGRESSION") is False
    for _ in range(3):
        hc.increment()
    assert hc.exhausted()
    with pytest.raises(RuntimeError):
        hc.increment()


def test_scope_engine_fallback_to_full():
    eng = ScopeEngine()
    # LOW confidence -> FULL_REGRESSION
    d = ImpactDecision(confidence="LOW", scope_evidence=["x"])
    assert eng.decide(d).execution_scope == "FULL_REGRESSION"
    # empty evidence -> FULL_REGRESSION
    d2 = ImpactDecision(confidence="HIGH")
    assert eng.decide(d2).execution_scope == "FULL_REGRESSION"


def test_scope_engine_targeted_vs_impacted():
    eng = ScopeEngine()
    d = ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                       scope_evidence=["e"])
    assert eng.decide(d).execution_scope == "TARGETED"
    d2 = ImpactDecision(confidence="MEDIUM",
                        impacted_tests=["tests/a.robot", "tests/b.robot"],
                        scope_evidence=["e"])
    assert eng.decide(d2).execution_scope == "IMPACTED_REGRESSION"


def test_scope_engine_shared_core_forces_full():
    eng = ScopeEngine()
    d = ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                       scope_evidence=["e"], shared_core_component_changed=True)
    assert eng.decide(d).execution_scope == "FULL_REGRESSION"


def test_local_execution_gates():
    k = make_kernel()
    walk_to_generation(k)
    k.record_local_execution(total=1, failed=0, skipped=0)
    assert k.store.get("execution")["failed"] == 0

    k2 = make_kernel()
    walk_to_generation(k2)
    with pytest.raises(RuntimeError):
        k2.record_local_execution(total=1, failed=1, skipped=0)  # gate fails


def test_taxonomy_legacy_mapping_consistent():
    import yaml
    from pathlib import Path
    tax = yaml.safe_load((Path(__file__).parent.parent / "config" /
                          "taxonomy.yaml").read_text(encoding="utf-8"))
    canonical = {c["id"] for c in tax["categories"]}
    assert len(canonical) == 6
    assert canonical == {
        "AUTOMATION_DEFECT", "TEST_DATA_DEFECT", "APPLICATION_DEFECT",
        "ENVIRONMENT_FAILURE", "FLAKY", "UNKNOWN",
    }
    assert "FLAKY" in canonical
    assert "ENVIRONMENT_FAILURE" in canonical
    legacy = set(tax["legacy_mapping"].values())
    assert legacy.issubset(canonical)


def test_final_outcome_green_when_no_failures():
    from orchestra.gates import final_outcome
    k = make_kernel()
    k.store.record("final_gate", {"all_satisfied": True, "results": {}})
    outcome, _ = final_outcome(k.store.snapshot())
    assert outcome == "GREEN"


def test_final_outcome_red_environment_dominates_others():
    from orchestra.gates import final_outcome
    k = make_kernel()
    k.store.record("failure_classifications", {
        "A": {"category": "ENVIRONMENT_FAILURE", "healable": False},
        "B": {"category": "AUTOMATION_DEFECT", "healable": True},
    })
    outcome, _ = final_outcome(k.store.snapshot())
    assert outcome == "RED_ENVIRONMENT"


def test_final_outcome_red_labels_for_each_category():
    from orchestra.gates import final_outcome
    expected = {
        "APPLICATION_DEFECT": "RED_APPLICATION",
        "ENVIRONMENT_FAILURE": "RED_ENVIRONMENT",
        "AUTOMATION_DEFECT": "RED_AUTOMATION",
        "TEST_DATA_DEFECT": "RED_DATA",
        "FLAKY": "RED_FLAKY",
        "UNKNOWN": "RED_UNKNOWN",
    }
    for cat, label in expected.items():
        k = make_kernel()
        k.store.record("failure_classifications", {
            "t": {"category": cat, "healable": cat in ("AUTOMATION_DEFECT", "TEST_DATA_DEFECT")},
        })
        outcome, _ = final_outcome(k.store.snapshot())
        assert outcome == label
        # a RED_* outcome is never GREEN
        assert outcome != "GREEN"


def test_gate_final_outcome_never_fabricates_green():
    k = make_kernel()
    k.store.record("failure_classifications", {
        "t": {"category": "ENVIRONMENT_FAILURE", "healable": False},
    })
    snap = k.store.snapshot()
    # gate_final_outcome: GREEN only when no failures -> RED must not be GREEN
    assert k.gates.evaluate_gate("gate_final_outcome", snap) is True
    assert k.gates.evaluate_gate("gate_regression_clean", snap) is False
    final = k.gates.evaluate_final(snap)
    assert final["all_satisfied"] is False
    assert final["outcome"] == "RED_ENVIRONMENT"
