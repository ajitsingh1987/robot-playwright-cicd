"""ScopeEngine: deterministic EXECUTION_SCOPE resolution (AMD 11.4.11)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ImpactDecision:
    confidence: str = "LOW"
    affected_areas: List[str] = field(default_factory=list)
    changed_artifacts: List[str] = field(default_factory=list)
    impacted_tests: List[str] = field(default_factory=list)
    execution_scope: str = "FULL_REGRESSION"
    scope_reason: str = ""
    scope_evidence: List[str] = field(default_factory=list)
    full_regression_needed: bool = True
    fallback_reason: str = ""
    shared_core_component_changed: bool = False
    shared_application_area_risk: bool = False
    insufficient_evidence_to_exclude: bool = False
    narrower_scope_failed: bool = False

    def to_dict(self) -> Dict:
        return {
            "confidence": self.confidence,
            "affected_areas": self.affected_areas,
            "changed_artifacts": self.changed_artifacts,
            "impacted_tests": self.impacted_tests,
            "execution_scope": self.execution_scope,
            "scope_reason": self.scope_reason,
            "scope_evidence": self.scope_evidence,
            "full_regression_needed": self.full_regression_needed,
            "fallback_reason": self.fallback_reason,
        }


class ScopeEngine:
    """Resolves the execution scope from repository evidence.

    Safety rule (mandatory): when confidence is LOW or evidence is insufficient to
    exclude a suite, fall back to FULL_REGRESSION. Never risk excluding tests.
    """

    TRIGGERS_FULL = (
        "confidence_is_low",
        "missing_scope_evidence",
        "shared_core_component_changed",
        "shared_application_area_risk",
        "insufficient_evidence_to_exclude",
        "narrower_scope_failed",
    )

    def decide(self, decision: ImpactDecision) -> ImpactDecision:
        # 1. FULL_REGRESSION safety triggers. Every declared trigger is evaluated so a
        #    shared/core/authentication-area change or insufficient evidence can never
        #    silently down-scope to a narrower run.
        if decision.confidence == "LOW":
            decision.execution_scope = "FULL_REGRESSION"
            decision.full_regression_needed = True
            decision.fallback_reason = decision.fallback_reason or "confidence LOW"
            return decision
        if not decision.scope_evidence:
            decision.execution_scope = "FULL_REGRESSION"
            decision.full_regression_needed = True
            decision.fallback_reason = decision.fallback_reason or "no scope evidence"
            return decision
        if decision.shared_core_component_changed:
            decision.execution_scope = "FULL_REGRESSION"
            decision.full_regression_needed = True
            decision.fallback_reason = "shared/core component changed"
            return decision
        if decision.shared_application_area_risk:
            decision.execution_scope = "FULL_REGRESSION"
            decision.full_regression_needed = True
            decision.fallback_reason = decision.fallback_reason or (
                "shared application/authentication area at risk"
            )
            return decision
        if decision.insufficient_evidence_to_exclude:
            decision.execution_scope = "FULL_REGRESSION"
            decision.full_regression_needed = True
            decision.fallback_reason = decision.fallback_reason or (
                "insufficient evidence to exclude a suite"
            )
            return decision
        if decision.narrower_scope_failed:
            decision.execution_scope = "FULL_REGRESSION"
            decision.full_regression_needed = True
            decision.fallback_reason = "narrower scope failed"
            return decision

        # 2. Evidence-driven scopes ONLY when no safety trigger has fired.
        #    TARGETED: HIGH confidence + exactly ONE proven impacted requirement-owned
        #    suite, with scope evidence present.
        if decision.confidence == "HIGH" and len(decision.impacted_tests) == 1:
            decision.execution_scope = "TARGETED"
            decision.full_regression_needed = False
            return decision

        #    IMPACTED_REGRESSION: HIGH/MEDIUM confidence + a bounded proven set.
        if decision.confidence in ("HIGH", "MEDIUM") and len(decision.impacted_tests) >= 1:
            decision.execution_scope = "IMPACTED_REGRESSION"
            decision.full_regression_needed = False
            return decision

        # 3. Safety fallback.
        decision.execution_scope = "FULL_REGRESSION"
        decision.full_regression_needed = True
        decision.fallback_reason = decision.fallback_reason or "uncertain -> broader scope"
        return decision
