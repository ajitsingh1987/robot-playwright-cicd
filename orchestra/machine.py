"""Stage registry + transition table (the deterministic state machine)."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from .state import StateError


class StageRegistry:
    """Loads stages.yaml and validates transitions against a hard-coded edge table.

    The LLM (or any caller) can NEVER set state directly; every transition must be an
    allowed edge declared here or in the composed lifecycle edge table.
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        config_dir = config_dir or Path(__file__).parent / "config"
        raw = yaml.safe_load((config_dir / "stages.yaml").read_text(encoding="utf-8"))
        self.stages: List[Dict] = raw["stages"]
        self.terminal_states: Set[str] = set(raw["terminal_states"])
        self._ids = [s["id"] for s in self.stages]

        # Happy-path linear transition table (documented lifecycle). Additional edges
        # to terminal/blocking states are appended in _build_edges().
        self._linear_edges: List[tuple] = [
            ("REQUIREMENT_RECEIVED", "REQUIREMENT_CLASSIFICATION"),
            ("REQUIREMENT_CLASSIFICATION", "IMPACT_ANALYSIS"),
            ("IMPACT_ANALYSIS", "COVERAGE_DECISION"),
            ("COVERAGE_DECISION", "BRANCH_DECISION"),
            ("BRANCH_DECISION", "PLANNING"),
            ("BRANCH_DECISION", "REGRESSION_EXECUTION"),  # REGRESSION shortcut: no plan/gen
            ("BRANCH_DECISION", "COMPLETED"),  # REGRESSION + SUFFICIENT coverage -> terminal
            ("PLANNING", "EXPLORATION"),
            ("EXPLORATION", "GENERATION"),
            ("GENERATION", "LOCAL_EXECUTION"),
            ("LOCAL_EXECUTION", "REGRESSION_EXECUTION"),
            ("LOCAL_EXECUTION", "FAILURE_ANALYSIS"),
            ("FAILURE_ANALYSIS", "HEALING"),
            ("FAILURE_ANALYSIS", "REGRESSION_EXECUTION"),
            ("FAILURE_ANALYSIS", "REVIEW"),
            ("HEALING", "RE_EXECUTION"),
            ("RE_EXECUTION", "REGRESSION_EXECUTION"),
            ("RE_EXECUTION", "FAILURE_ANALYSIS"),
            ("REGRESSION_EXECUTION", "REVIEW"),
            ("REGRESSION_EXECUTION", "FAILURE_ANALYSIS"),
            ("REVIEW", "DOCKER_VALIDATION"),
            ("DOCKER_VALIDATION", "ALLURE_VALIDATION"),
            ("ALLURE_VALIDATION", "FINAL_QUALITY_GATE"),
            ("FINAL_QUALITY_GATE", "COMMIT"),
            ("FINAL_QUALITY_GATE", "COMPLETED"),
            ("FINAL_QUALITY_GATE", "PR_READY"),  # terminal after a passed quality gate (no commit/push)
            ("COMMIT", "PUSH"),
            ("PUSH", "CI_VALIDATION"),
            ("CI_VALIDATION", "CI_HEALING"),
            ("CI_VALIDATION", "PR_READY"),
            ("CI_HEALING", "CI_VALIDATION"),
            ("CI_HEALING", "CICD_LOCKED"),
            ("HEALING", "HEALING_EXHAUSTED"),
            ("REGRESSION_EXECUTION", "REGRESSION_FAILURE"),
        ]
        self._edges: Set[tuple] = set(self._linear_edges)
        # Any stage may become BLOCKED or CICD_LOCKED (control flow halts).
        for s in self._ids + list(self.terminal_states):
            self._edges.add((s, "BLOCKED"))
            self._edges.add((s, "CICD_LOCKED"))

    def has_stage(self, stage: str) -> bool:
        return stage in self._ids or stage in self.terminal_states

    def allowed(self, state: str, target: str) -> bool:
        if not self.has_stage(target):
            raise StateError(f"Unknown target stage: {target}")
        if state in self.terminal_states:
            return False
        if (state, target) in self._edges:
            return True
        return False

    def owner_of(self, stage: str) -> Optional[str]:
        for s in self.stages:
            if s["id"] == stage:
                return s.get("owner", "KERNEL")
        return None


def build_registry(config_dir: Optional[Path] = None) -> StageRegistry:
    return StageRegistry(config_dir)
