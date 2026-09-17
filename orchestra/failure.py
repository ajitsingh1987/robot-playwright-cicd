"""Evidence-driven failure classification (SIX canonical categories).

A failing test is classified ONLY from observable evidence, never from a verbal claim
or guesswork. The trusted evidence sources are repeated full-run outcomes, isolated
(solo) re-execution outcomes and explicit run markers (auth/validate hang, page never
renders, network timeout, ...).

The SIX canonical categories and their decision rules:

    1. ENVIRONMENT_FAILURE   - the execution environment prevented valid execution:
                               page does not render, /auth/validate hangs, navigation
                               never completes, network timeout, browser/infra failure,
                               public-demo server unresponsive. Also replaces legacy
                               EXTERNAL_SERVICE_DEFECT. Requires `environment_issue`
                               together with at least one concrete environment marker,
                               a public-demo target, or isolation-failure evidence.
                               NEVER heal, NEVER convert to PASS.
    2. APPLICATION_DEFECT    - the application itself behaves incorrectly. Requires
                               `application_behavior_issue` and a repeated isolation
                               failure (consistent misbehaviour, not a one-off).
    3. TEST_DATA_DEFECT      - the test's business data / data config is invalid.
                               Requires `data_issue` and a repeated isolation failure.
    4. FLAKY                 - a full-run FAIL that then PASSES in isolation, i.e.
                               repeated execution shows INCONSISTENT results. A single
                               timeout is NEVER sufficient evidence of flakiness.
    5. AUTOMATION_DEFECT     - fails in isolation with automation/locator/timing
                               evidence (and no environment markers).
    6. UNKNOWN               - insufficient evidence. Never guess; never auto-heal.

Priority is fixed: environment markers (hard infrastructure evidence) dominate, then
application, then data, then flaky (requires the isolation-pass proof), then
automation, then UNKNOWN.

Guarantees (HARD contract) for every non-healable category:

    1. The failure is NEVER converted into PASS. `converted_to_pass` is always False
       and classification never mutates the recorded regression `failed` count.
    2. It NEVER triggers healing. `healable` is False and the kernel gate refuses the
       FAILURE_ANALYSIS -> HEALING transition for any non-healable classification.
       THIS INCLUDES environment failures: the framework must NEVER modify working
       automation merely because an external/public application is temporarily
       unavailable.
    3. It keeps FINAL_QUALITY_GATE blocked while the regression remains non-clean
       (regression.failed > 0), because the clean gate is the sole source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

# Canonical, non-healable categories (never auto-heal, never auto-convert to PASS).
NON_HEALABLE = {
    "ENVIRONMENT_FAILURE",
    "APPLICATION_DEFECT",
    "FLAKY",
    "UNKNOWN",
}

# Healable categories (may route to HEALING, capped at 3, only for AUTOMATION modes).
HEALABLE = {"AUTOMATION_DEFECT", "TEST_DATA_DEFECT"}

VALID_CATEGORIES = NON_HEALABLE | HEALABLE

# Concrete, observable markers that prove the ENVIRONMENT prevented valid execution.
# A marker is strong evidence by itself: it never depends on a human claim.
ENVIRONMENT_MARKERS = (
    "auth_validate_hang",
    "navigation_incomplete",
    "network_timeout",
    "server_unresponsive",
    "page_not_rendered",
    "server_request_incomplete",
    "browser_unavailable",
    "browser_unresponsive",
    "docker_unavailable",
)


@dataclass
class FailureEvidence:
    """Observed evidence for a single failing test across runs."""

    test_id: str
    full_run_failed: bool = True
    isolated_rerun_passed: bool = False
    repeated_full_run_failures: int = 1
    repeated_isolated_failures: int = 0
    environment_issue: bool = False
    automation_evidence: bool = False
    application_behavior_issue: bool = False
    data_issue: bool = False
    public_demo: bool = False
    environment_markers: List[str] = field(default_factory=list)
    extra: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "test_id": self.test_id,
            "full_run_failed": self.full_run_failed,
            "isolated_rerun_passed": self.isolated_rerun_passed,
            "repeated_full_run_failures": self.repeated_full_run_failures,
            "repeated_isolated_failures": self.repeated_isolated_failures,
            "environment_issue": self.environment_issue,
            "automation_evidence": self.automation_evidence,
            "application_behavior_issue": self.application_behavior_issue,
            "data_issue": self.data_issue,
            "public_demo": self.public_demo,
            "environment_markers": list(self.environment_markers),
            "extra": self.extra,
        }


@dataclass
class FailureClassification:
    category: str
    healable: bool
    converted_to_pass: bool
    blocking: bool
    reason: str
    evidence: FailureEvidence

    def to_dict(self) -> Dict[str, object]:
        ev = self.evidence.to_dict() if hasattr(self.evidence, "to_dict") else {}
        return {
            "test_id": self.evidence.test_id,
            "category": self.category,
            "healable": self.healable,
            "converted_to_pass": self.converted_to_pass,
            "blocking": self.blocking,
            "reason": self.reason,
            "evidence": ev,
        }


class FailureClassifier:
    """Deterministically classify a failing test from repeated/isolated evidence."""

    @staticmethod
    def heard_markers(evidence: FailureEvidence) -> List[str]:
        """Return the environment markers present in the evidence (observed, not claimed)."""
        known = set(ENVIRONMENT_MARKERS)
        seen = []
        for m in evidence.environment_markers or []:
            if m in known:
                seen.append(m)
        return seen

    def classify(self, evidence: FailureEvidence) -> FailureClassification:
        test_id = evidence.test_id
        # A failure is never PASS, period.
        converted_to_pass = False
        markers = self.heard_markers(evidence)

        # ENVIRONMENT_FAILURE: environment prevented valid execution. A concrete
        # marker (auth/validate hang, page never renders, network timeout, ...) is
        # decisive even on first occurrence; a public-demo target equally so, because
        # a temporarily-unavailable shared demo is never an automation defect.
        if evidence.environment_issue and (
            markers or evidence.public_demo or evidence.repeated_isolated_failures > 0
        ):
            return FailureClassification(
                category="ENVIRONMENT_FAILURE",
                healable=False,
                converted_to_pass=converted_to_pass,
                blocking=True,
                reason=(
                    "environment prevented valid execution"
                    + (f"; markers={markers}" if markers else "")
                    + ("; public demo target" if evidence.public_demo else "")
                ),
                evidence=evidence,
            )

        # APPLICATION_DEFECT: the application misbehaves consistently.
        if evidence.application_behavior_issue and evidence.repeated_isolated_failures > 0:
            return FailureClassification(
                category="APPLICATION_DEFECT",
                healable=False,
                converted_to_pass=converted_to_pass,
                blocking=True,
                reason="application behaves incorrectly in isolation; report to product",
                evidence=evidence,
            )

        # TEST_DATA_DEFECT: invalid/missing/stale test data, consistent in isolation.
        if evidence.data_issue and evidence.repeated_isolated_failures > 0:
            return FailureClassification(
                category="TEST_DATA_DEFECT",
                healable=True,
                converted_to_pass=converted_to_pass,
                blocking=True,
                reason="invalid/missing/stale test data reproduced in isolation",
                evidence=evidence,
            )

        # FLAKY: full-run FAIL but PASSES in isolation -> repeated execution shows
        # INCONSISTENT results. A single timeout alone is never flaky.
        if evidence.isolated_rerun_passed and evidence.repeated_isolated_failures == 0:
            return FailureClassification(
                category="FLAKY",
                healable=False,
                converted_to_pass=converted_to_pass,
                blocking=True,
                reason=(
                    "failed in full run but passed when re-run in isolation; "
                    "inconsistent results across repeated executions"
                ),
                evidence=evidence,
            )

        # AUTOMATION_DEFECT: fails in isolation with automation/locator/timing evidence.
        if evidence.automation_evidence and evidence.repeated_isolated_failures > 0:
            return FailureClassification(
                category="AUTOMATION_DEFECT",
                healable=True,
                converted_to_pass=converted_to_pass,
                blocking=True,
                reason="fails in isolation with automation/locator/timing evidence",
                evidence=evidence,
            )

        # UNKNOWN: insufficient evidence (never guess, never auto-invoke the Healer).
        return FailureClassification(
            category="UNKNOWN",
            healable=False,
            converted_to_pass=converted_to_pass,
            blocking=True,
            reason="insufficient evidence to classify root cause",
            evidence=evidence,
        )

    @staticmethod
    def is_non_healable(category: str) -> bool:
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid failure category: {category}")
        return category in NON_HEALABLE
