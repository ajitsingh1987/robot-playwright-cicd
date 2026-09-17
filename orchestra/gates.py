"""GateEngine: deterministic gate predicates over persisted run state."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Red outcome precedence: deterministic category -> final-outcome mapping for a
# non-clean run. The order is the REPORT label priority when several categories are
# present in one run (the most actionable / certification-relevant label wins):
#   1. APPLICATION_DEFECT  -> product bug, most critical to surface.
#   2. ENVIRONMENT_FAILURE -> certification is BLOCKED (external/public demo down).
#   3. AUTOMATION_DEFECT   -> our automation is broken (real, isolated-repro).
#   4. TEST_DATA_DEFECT    -> our test data is wrong.
#   5. FLAKY               -> intermittent; retries show inconsistency.
#   6. UNKNOWN             -> no evidence to act on.
_OUTCOME_PRECEDENCE = (
    ("APPLICATION_DEFECT", "RED_APPLICATION"),
    ("ENVIRONMENT_FAILURE", "RED_ENVIRONMENT"),
    ("AUTOMATION_DEFECT", "RED_AUTOMATION"),
    ("TEST_DATA_DEFECT", "RED_DATA"),
    ("FLAKY", "RED_FLAKY"),
    ("UNKNOWN", "RED_UNKNOWN"),
)


def final_outcome(state: Dict[str, Any]) -> tuple:  # (outcome, reason)
    """Deterministic final-gate outcome for the REPORT.

    GREEN is emitted ONLY when no failures were classified. Any recorded failure
    (of ANY category) produces a RED_* label; a RED_* outcome is NEVER a pass and
    the classification with the highest precedence dominates the report label.
    """
    classifications = state.get("failure_classifications") or {}
    if not classifications:
        final_gate = state.get("final_gate") or {}
        if final_gate.get("all_satisfied") is True:
            return "GREEN", "no failures classified and all quality gates satisfied"
        return "RED_UNKNOWN", "no failures classified but final quality gate not satisfied"
    present: Dict[str, int] = {}
    for c in classifications.values():
        cat = c.get("category")
        present[cat] = present.get(cat, 0) + 1
    for cat, outcome in _OUTCOME_PRECEDENCE:
        if cat in present:
            return outcome, f"classification dominated by {cat} ({present[cat]} failed test(s))"
    return "RED_UNKNOWN", "failures present with no matching category"


def public_demo_classification_guard(state: Dict[str, Any]) -> bool:
    """PUBLIC-DEMO PROTECTION: never treat an environment-flagged failure as healable.

    When the run target is a public demo environment and a failure carries concrete
    environment markers (auth/validate hang, page-not-rendered, network timeout, server
    unresponsive), its classification MUST be ENVIRONMENT_FAILURE. This guarantees the
    framework never modifies working automation merely because the public application
    is temporarily unavailable.
    """
    if state.get("public_demo_environment") is not True:
        return True
    for c in (state.get("failure_classifications") or {}).values():
        markers = ((c.get("evidence") or {}).get("environment_markers")) or []
        if markers and c.get("category") != "ENVIRONMENT_FAILURE":
            return False
    return True


# Safe builtins injected into gate expression evaluation. No arbitrary exec; each gate
# check string is evaluated only over these names plus the state snapshot.
_SAFE = {
    "len": len,
    "all": all,
    "any": any,
    "isinstance": isinstance,
    "final_outcome": final_outcome,
    "public_demo_classification_guard": public_demo_classification_guard,
}


class GateEngine:
    def __init__(self, gates_path: Optional[Path] = None) -> None:
        gates_path = gates_path or Path(__file__).parent / "config" / "gates.yaml"
        raw = yaml.safe_load(gates_path.read_text(encoding="utf-8"))
        self.gates: List[Dict] = raw["gates"]
        self._by_stage: Dict[str, List[Dict]] = {}
        for g in self.gates:
            self._by_stage.setdefault(g["stage"], []).append(g)

    def gate_ids_for_stage(self, stage: str) -> List[str]:
        return [g["id"] for g in self._by_stage.get(stage, [])]

    def evaluate_gate(self, gate_id: str, state: Dict[str, Any]) -> bool:
        gate = next((g for g in self.gates if g["id"] == gate_id), None)
        if gate is None:
            raise KeyError(f"Unknown gate: {gate_id}")
        code = compile(gate["check"], f"<gate:{gate_id}>", "eval")
        return bool(eval(code, {"__builtins__": {}}, {**_SAFE, "state": state}))

    def evaluate_stage(self, stage: str, state: Dict[str, Any]) -> List[str]:
        """Return list of FAILED gate ids for the stage (empty == all pass)."""
        failed = []
        for g in self._by_stage.get(stage, []):
            if not self.evaluate_gate(g["id"], state):
                failed.append(g["id"])
        return failed

    # Gate families considered mandatory for FINAL_QUALITY_GATE. Authorization
    # (commit/push) and CI gates are intentionally EXCLUDED: the final quality
    # decision is about quality only and must never depend on a commit hash or a
    # push that do not exist yet.
    _FINAL_QUALITY_CATEGORIES = ("quality", "final")

    def quality_gates(self) -> List[Dict]:
        """The gates that constitute FINAL_QUALITY_GATE (quality + derived final)."""
        return [g for g in self.gates if g.get("category") in self._FINAL_QUALITY_CATEGORIES]

    def evaluate_final(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate ONLY the quality gates; derive gate_final + outcome from the result.

        FINAL_QUALITY_GATE is passable even when `commit.hash` and `push.ref` are
        absent/None, because authorization gates are never part of this evaluation.
        The deterministic `outcome` (GREEN / RED_*) is derived for reporting and is
        NEVER used to fabricate a pass: outcome == GREEN only when no failures were
        classified AND every quality gate is satisfied.
        """
        results: Dict[str, bool] = {}
        all_ok = True
        for g in self.quality_gates():
            if g["id"] == "gate_final":
                # derived below from the other quality gates (no self-reference)
                continue
            ok = self.evaluate_gate(g["id"], state)
            results[g["id"]] = ok
            all_ok = all_ok and ok
        results["gate_final"] = all_ok
        derived = dict(state)
        derived["final_gate"] = {"all_satisfied": all_ok}
        outcome, reason = final_outcome(derived)
        return {
            "all_satisfied": all_ok,
            "results": results,
            "outcome": outcome,
            "outcome_reason": reason,
        }
