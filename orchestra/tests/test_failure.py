"""Unit tests for evidence-driven SIX-category failure classification.

Covers the HARD guarantees of the contract:
    1. A failing test is NEVER converted into PASS for any category.
    2. ENVIRONMENT_FAILURE / FLAKY / APPLICATION_DEFECT / UNKNOWN NEVER trigger healing.
    3. FINAL_QUALITY_GATE stays BLOCKED while the regression remains non-clean.
"""
from __future__ import annotations

import pytest

from orchestra.evidence import EvidenceBus
from orchestra.failure import (
    FailureClassifier,
    FailureEvidence,
    HEALABLE,
    NON_HEALABLE,
    VALID_CATEGORIES,
)
from orchestra.gates import GateEngine
from orchestra.healing import HealingCounter
from orchestra.kernel import Kernel
from orchestra.machine import StageRegistry
from orchestra.scope import ImpactDecision
from orchestra.state import StateStore


def make_kernel() -> Kernel:
    store = StateStore("test-fail-0001")
    registry = StageRegistry()
    gates = GateEngine()
    evidence = EvidenceBus(store)
    return Kernel(store=store, registry=registry, gates=gates, evidence=evidence)


def walk_to_failure_analysis(k: Kernel, mode: str = "NEW_AUTOMATION",
                             branch: str = "feature/qa-auto-x") -> None:
    """Walk the AUTOMATION prefix into FAILURE_ANALYSIS (no agent subprocess)."""
    k.classify(mode)
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"],
                            scope_evidence=["e"]))
    k.coverage("PARTIAL")
    k.branch(branch)
    for stage, src in [
        ("PLANNING", "BRANCH_DECISION"),
        ("EXPLORATION", "PLANNING"),
        ("GENERATION", "EXPLORATION"),
        ("LOCAL_EXECUTION", "GENERATION"),
        ("FAILURE_ANALYSIS", "LOCAL_EXECUTION"),
    ]:
        k.store.transition(stage, allowed=k.registry.allowed(src, stage))


def record_failing_regression(k: Kernel, failed: int = 1) -> None:
    """Record a non-clean regression directly (record_regression asserts the clean gate)."""
    k.store.record("regression", {
        "total": 32, "failed": failed, "skipped": 0,
        "unresolved": 0, "exit_code": 1,
    })


# -- classifier unit logic -------------------------------------------------

def test_classifier_flaky_when_passes_in_isolation():
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=True)
    res = cls.classify(ev)
    assert res.category == "FLAKY"
    assert res.healable is False
    assert res.converted_to_pass is False
    assert res.blocking is True


def test_classifier_environment_when_persistent_infrastructure():
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=False,
                         repeated_isolated_failures=1, environment_issue=True)
    res = cls.classify(ev)
    assert res.category == "ENVIRONMENT_FAILURE"
    assert res.healable is False


def test_classifier_environment_on_first_failure_when_marker_or_public_demo():
    cls = FailureClassifier()
    # a concrete marker (auth/validate hang) is decisive even without isolated reruns
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=False,
                         environment_issue=True, environment_markers=["auth_validate_hang"])
    res = cls.classify(ev)
    assert res.category == "ENVIRONMENT_FAILURE"
    assert res.healable is False
    # a public-demo target is decisive even without markers
    ev2 = FailureEvidence(test_id="t2", environment_issue=True, public_demo=True)
    res2 = cls.classify(ev2)
    assert res2.category == "ENVIRONMENT_FAILURE"
    assert res2.healable is False


def test_classifier_application_defect_consistent_misbehaviour():
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=False,
                         repeated_isolated_failures=2, application_behavior_issue=True)
    res = cls.classify(ev)
    assert res.category == "APPLICATION_DEFECT"
    assert res.healable is False


def test_classifier_test_data_defect_consistent_repro():
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=False,
                         repeated_isolated_failures=1, data_issue=True)
    res = cls.classify(ev)
    assert res.category == "TEST_DATA_DEFECT"
    assert res.healable is True


def test_single_timeout_is_not_flaky():
    # one timeout with no isolation evidence is NOT flaky and NOT healable
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=False,
                         repeated_isolated_failures=0)
    res = cls.classify(ev)
    assert res.category == "UNKNOWN"
    assert res.healable is False


def test_environment_marker_dominates_flaky_pass():
    # hard infrastructure evidence dominates an isolation pass
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=True,
                         environment_issue=True, environment_markers=["network_timeout"])
    res = cls.classify(ev)
    assert res.category == "ENVIRONMENT_FAILURE"
    assert res.healable is False


def test_application_defect_dominates_unknown_but_not_environment():
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=False,
                         repeated_isolated_failures=1, application_behavior_issue=True,
                         environment_issue=True, environment_markers=["server_unresponsive"])
    res = cls.classify(ev)
    assert res.category == "ENVIRONMENT_FAILURE"
    assert res.healable is False


def test_classifier_automation_defect_when_persistent_with_automation_evidence():
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1", isolated_rerun_passed=False,
                         repeated_isolated_failures=1, automation_evidence=True)
    res = cls.classify(ev)
    assert res.category == "AUTOMATION_DEFECT"
    assert res.healable is True


def test_classifier_unknown_when_insufficient_evidence():
    cls = FailureClassifier()
    ev = FailureEvidence(test_id="t1")
    res = cls.classify(ev)
    assert res.category == "UNKNOWN"
    assert res.healable is False


def test_never_converted_to_pass_for_any_category():
    cls = FailureClassifier()
    for ev, expected in [
        (FailureEvidence(test_id="t", isolated_rerun_passed=True), "FLAKY"),
        (FailureEvidence(test_id="t", repeated_isolated_failures=1,
                         environment_issue=True), "ENVIRONMENT_FAILURE"),
        (FailureEvidence(test_id="t", repeated_isolated_failures=1,
                         automation_evidence=True), "AUTOMATION_DEFECT"),
        (FailureEvidence(test_id="t", repeated_isolated_failures=1,
                         application_behavior_issue=True), "APPLICATION_DEFECT"),
        (FailureEvidence(test_id="t", repeated_isolated_failures=1,
                         data_issue=True), "TEST_DATA_DEFECT"),
        (FailureEvidence(test_id="t"), "UNKNOWN"),
    ]:
        res = cls.classify(ev)
        assert res.category == expected
        assert res.converted_to_pass is False


def test_healable_categories_are_exactly_automation_set():
    assert HEALABLE == {"AUTOMATION_DEFECT", "TEST_DATA_DEFECT"}
    assert len(VALID_CATEGORIES) == 6
    assert NON_HEALABLE == {
        "FLAKY", "ENVIRONMENT_FAILURE", "APPLICATION_DEFECT", "UNKNOWN",
    }
    assert HEALABLE | NON_HEALABLE == VALID_CATEGORIES


def test_healing_counter_never_heals_flake_or_environment():
    k = make_kernel()
    k.classify("NEW_AUTOMATION")
    hc = HealingCounter(k.store)
    assert hc.can_heal("NEW_AUTOMATION") is True
    assert hc.healable("AUTOMATION_DEFECT") is True
    assert hc.can_heal_failure("NEW_AUTOMATION", "AUTOMATION_DEFECT") is True
    for non in ("FLAKY", "ENVIRONMENT_FAILURE", "APPLICATION_DEFECT", "UNKNOWN"):
        assert hc.healable(non) is False
        assert hc.can_heal_failure("NEW_AUTOMATION", non) is False


# -- kernel integration / hard guarantees ----------------------------------

def test_classify_failure_does_not_convert_to_pass_or_mutate_regression():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)

    cls = k.classify_failure("Employee X", FailureEvidence(
        test_id="Employee X", isolated_rerun_passed=True))

    assert cls.category == "FLAKY"
    assert cls.converted_to_pass is False
    # regression failed count is untouched by classification
    assert k.store.get("regression")["failed"] == 1
    recorded = k.store.get("failure_classifications")["Employee X"]
    assert recorded["converted_to_pass"] is False
    # gate_regression_clean still fails -> regression is NOT clean
    assert k.gates.evaluate_gate("gate_regression_clean", k.store.snapshot()) is False


def test_flake_routes_to_review_not_healing():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    k.classify_failure("FlakeTest", FailureEvidence(
        test_id="FlakeTest", isolated_rerun_passed=True))

    nxt = k.route_after_failure()
    assert nxt == "REVIEW"
    assert nxt != "HEALING"


def test_environment_routes_to_review_not_healing():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    k.classify_failure("EnvTest", FailureEvidence(
        test_id="EnvTest", repeated_isolated_failures=1, environment_issue=True))

    assert k.route_after_failure() == "REVIEW"


def test_public_demo_environment_marker_never_heals():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    # a public-demo /auth/validate hang with NO isolated evidence still blocks healing
    k.classify_failure("PublicDemoTest", FailureEvidence(
        test_id="PublicDemoTest",
        environment_issue=True, environment_markers=["auth_validate_hang"],
        public_demo=True))

    assert k.route_after_failure() == "REVIEW"
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_no_heal_on_flake_or_environment", snap) is False


def test_public_demo_guard_blocks_healable_misclassification():
    k = make_kernel()
    k.store.record("public_demo_environment", True)
    # a misclassification that labels an environment-marker failure as healable
    # (as if the public demo were an automation defect) MUST trip the guard
    k.store.record("failure_classifications", {
        "PublicDemoTest": {
            "test_id": "PublicDemoTest",
            "category": "AUTOMATION_DEFECT",
            "healable": True,
            "converted_to_pass": False,
            "evidence": {"environment_markers": ["auth_validate_hang"]},
        }
    })
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_public_demo_environment", snap) is False


def test_public_demo_guard_passes_for_real_environment_failure():
    k = make_kernel()
    k.store.record("public_demo_environment", True)
    k.store.record("failure_classifications", {
        "PublicDemoTest": {
            "test_id": "PublicDemoTest",
            "category": "ENVIRONMENT_FAILURE",
            "healable": False,
            "converted_to_pass": False,
            "evidence": {"environment_markers": ["auth_validate_hang"]},
        }
    })
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_public_demo_environment", snap) is True


def test_application_defect_routes_to_review_not_healing():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    k.classify_failure("AppTest", FailureEvidence(
        test_id="AppTest", repeated_isolated_failures=2, application_behavior_issue=True))
    assert k.route_after_failure() == "REVIEW"
    assert k.route_after_failure() != "HEALING"


def test_test_data_defect_routes_to_healing_in_automation_mode():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    k.classify_failure("DataTest", FailureEvidence(
        test_id="DataTest", repeated_isolated_failures=1, data_issue=True))
    assert k.route_after_failure() == "HEALING"


def test_mixed_healable_and_flake_routes_to_review():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k, failed=2)
    k.classify_failure("DefectTest", FailureEvidence(
        test_id="DefectTest", repeated_isolated_failures=1, automation_evidence=True))
    k.classify_failure("FlakeTest", FailureEvidence(
        test_id="FlakeTest", isolated_rerun_passed=True))

    assert k.route_after_failure() == "REVIEW"


def test_healable_defect_routes_to_healing_in_automation_mode():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    k.classify_failure("DefectTest", FailureEvidence(
        test_id="DefectTest", repeated_isolated_failures=1, automation_evidence=True))
    assert k.route_after_failure() == "HEALING"


def test_regression_mode_never_routes_to_healing_even_for_healable_defect():
    k = make_kernel()
    walk_to_failure_analysis(k, mode="REGRESSION", branch=None)
    record_failing_regression(k)
    k.classify_failure("DefectTest", FailureEvidence(
        test_id="DefectTest", repeated_isolated_failures=1, automation_evidence=True))
    assert k.route_after_failure() == "REVIEW"


def test_final_gate_blocked_while_regression_non_clean():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    k.classify_failure("FlakeTest", FailureEvidence(
        test_id="FlakeTest", isolated_rerun_passed=True))
    assert k.route_after_failure() == "REVIEW"

    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_regression_clean", snap) is False
    final = k.gates.evaluate_final(snap)
    assert final["all_satisfied"] is False
    assert final["results"]["gate_regression_clean"] is False


def test_no_heal_gate_blocks_healing_when_any_non_healable():
    k = make_kernel()
    walk_to_failure_analysis(k)
    record_failing_regression(k)
    k.classify_failure("FlakeTest", FailureEvidence(
        test_id="FlakeTest", isolated_rerun_passed=True))
    snap = k.store.snapshot()
    assert k.gates.evaluate_gate("gate_no_heal_on_flake_or_environment", snap) is False
