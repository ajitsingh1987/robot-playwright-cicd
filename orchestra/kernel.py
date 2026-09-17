"""Kernel driver: orchestrates the deterministic state machine lifecycle.

The kernel is the single authority for workflow truth. Agent subprocesses are delegated
for cognitive sub-stages; the kernel verifies their recorded evidence before allowing
state to advance via the GateEngine and StageRegistry.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Set

from .adapters.agent_cli import AgentCLI, AgentResult
from .config import settings
from .evidence import EvidenceBus
from .failure import FailureClassification, FailureClassifier, FailureEvidence
from .gates import GateEngine
from .healing import HealingCounter
from .machine import StageRegistry
from .review import parse_review_verdict
from .scope import ImpactDecision, ScopeEngine
from .state import StateStore

MAX_RESUMES = 1
_EXECUTED_KEY = "executed_stages"
_RESTART_COUNT_KEY = "restart_count"


class Kernel:
    def __init__(
        self,
        store: StateStore,
        registry: Optional[StageRegistry] = None,
        gates: Optional[GateEngine] = None,
        scope: Optional[ScopeEngine] = None,
        evidence: Optional[EvidenceBus] = None,
        agent_cli: Optional[AgentCLI] = None,
        failure_classifier: Optional[FailureClassifier] = None,
    ) -> None:
        self.store = store
        self.registry = registry or StageRegistry()
        self.gates = gates or GateEngine()
        self.scope_engine = scope or ScopeEngine()
        self.evidence = evidence or EvidenceBus(store)
        self.healing = HealingCounter(store)
        self.agent_cli = agent_cli or AgentCLI()
        self.failure_classifier = failure_classifier or FailureClassifier()

    # -- resume (classmethod) ------------------------------------------------
    @classmethod
    def resume(cls, run_id: str, log_path: Optional[Path] = None) -> "Kernel":
        """Hydrate a Kernel from a prior run's JSONL log instead of creating fresh.

        This is the ONLY safe way to restart an interrupted orchestration. It
        replays the log, reconstructs the full state snapshot, and enforces the
        bounded-restart rule (MAX_RESUMES=1). If the restart cap is exceeded,
        it raises RuntimeError and the caller must report BLOCKED — it must NOT
        create a fresh Kernel and restart.
        """
        store = StateStore.resume(run_id, log_path=log_path)
        snapshot = store.snapshot()
        restart_count = snapshot.get(_RESTART_COUNT_KEY, 0)
        if store.resumed:
            restart_count += 1
        if restart_count > MAX_RESUMES:
            raise RuntimeError(
                f"Resume cap exceeded: restart_count={restart_count} > MAX_RESUMES={MAX_RESUMES}. "
                f"Run {run_id} is BLOCKED — do NOT create a fresh kernel to retry."
            )
        store.record(_RESTART_COUNT_KEY, restart_count)
        k = cls(store=store)
        return k

    # -- run-once execution guard -------------------------------------------
    def _already_executed(self, action_key: str) -> bool:
        """True if `action_key` was already executed in this run.

        action_key is e.g. "agent:planner", "local_execution", "regression".
        The guard prevents re-execution of expensive actions on restart/resume
        unless an explicit retry transition (HEALING / RE_EXECUTION) clears the
        marker via `clear_execution_marker()`.
        """
        executed: Dict[str, Any] = self.store.get(_EXECUTED_KEY) or {}
        return bool(executed.get(action_key))

    def _mark_executed(self, action_key: str) -> None:
        """Record that `action_key` has been executed; calling code must persist."""
        executed: Dict[str, Any] = dict(self.store.get(_EXECUTED_KEY) or {})
        executed[action_key] = True
        self.store.record(_EXECUTED_KEY, executed)

    def clear_execution_marker(self, action_key: str) -> None:
        """Remove a single execution marker — used only by explicit retry transitions.

        HEALING transitions call this for the healed stage so the re-execution
        path actually re-runs. This is the ONLY permitted way to unblock a
        run-once guard; casual restarts never clear markers.
        """
        executed: Dict[str, Any] = dict(self.store.get(_EXECUTED_KEY) or {})
        executed.pop(action_key, None)
        self.store.record(_EXECUTED_KEY, executed)

    def clear_all_execution_markers(self) -> None:
        """Clear ALL execution markers (used after HEALING re-runs)."""
        self.store.record(_EXECUTED_KEY, {})

    # -- agent delegation -----------------------------------------------------
    def invoke_agent(
        self,
        agent: str,
        stage: str,
        message: str,
        *,
        timeout: int = 1800,
        evidence_dir: Optional[Path] = None,
    ) -> AgentResult:
        """Invoke a real opencode agent for a cognitive stage and record its evidence.

        Run-once guard: if this (agent, stage) pair has already been executed in
        this run and no retry marker was cleared, this method returns the cached
        result from state instead of re-shelling-out to the agent. This directly
        eliminates the "keep invoking the driver waiting for a result" loop.

        The kernel records the result in state, then advances the machine ONLY when the
        agent returned a session id + non-empty text (evidence of actual execution).
        A fabricated/empty agent result does NOT advance the stage.
        """
        action_key = f"agent:{stage}"
        cached = self.store.get(f"{stage}.agent")
        if self._already_executed(action_key) and cached:
            result_dict = cached if isinstance(cached, dict) else {}
            return AgentResult(
                agent=result_dict.get("agent", agent),
                exit_code=result_dict.get("exit_code", 0),
                session_id=result_dict.get("session_id"),
                text=result_dict.get("text", ""),
                raw_json="",
                artifacts=result_dict.get("artifacts", []),
            )

        evidence_dir = evidence_dir or Path("results") / "orchestra"
        out = evidence_dir / f"{self.store.run_id}-{agent}.jsonl"
        result = self.agent_cli.run_agent(agent, message, timeout=timeout, output_file=out)

        self.store.record(f"{stage}.agent", result.to_dict())
        self.evidence.add(f"{stage}.artifact", out.as_posix(), kind="agent-stream")

        if result.exit_code != 0:
            raise RuntimeError(
                f"Agent {agent} failed (exit {result.exit_code}); stage {stage} BLOCKED."
            )
        if not result.session_id or not result.text.strip():
            raise RuntimeError(
                f"Agent {agent} returned no evidence for {stage}; refusing to advance."
            )

        self._mark_executed(action_key)
        self._advance_from_current_to(stage)
        return result

    def _advance_from_current_to(self, stage: str) -> None:
        """Advance the machine from the current state into `stage` (if not already there)."""
        current = self.store.current_state()
        if current == stage:
            return
        if not self.registry.allowed(current, stage):
            raise RuntimeError(
                f"Cannot advance {current} -> {stage}: no such transition."
            )
        self.store.transition(stage, allowed=True)

    # -- helpers ----------------------------------------------------------
    def record_outcome(self, gate_results: Dict[str, bool]) -> None:
        self.store.record("gates", gate_results)

    # -- lifecycle steps ----------------------------------------------------
    def classify(self, automation_mode: str) -> None:
        if self._already_executed("classify"):
            return
        if automation_mode not in (
            "REGRESSION",
            "NEW_AUTOMATION",
            "AUTOMATION_ENHANCEMENT",
            "AUTOMATION_FIX",
        ):
            raise ValueError(f"Invalid automation mode: {automation_mode}")
        self.store.record("automation_mode", automation_mode)
        self.store.transition(
            "REQUIREMENT_CLASSIFICATION",
            allowed=self.registry.allowed(self.store.current_state(), "REQUIREMENT_CLASSIFICATION"),
        )
        self._assert_gate("gate_classified")
        self._mark_executed("classify")

    def impact(self, decision: ImpactDecision) -> None:
        if self._already_executed("impact"):
            return
        resolved = self.scope_engine.decide(decision)
        self.store.record("impact", resolved.to_dict())
        self.store.transition(
            "IMPACT_ANALYSIS",
            allowed=self.registry.allowed(self.store.current_state(), "IMPACT_ANALYSIS"),
        )
        self._assert_gate("gate_impact_after_classify")
        self._mark_executed("impact")

    def coverage(self, coverage_decision: str) -> None:
        if self._already_executed("coverage"):
            return
        if coverage_decision not in ("SUFFICIENT", "PARTIAL", "MISSING", "UNKNOWN"):
            raise ValueError(f"Invalid coverage decision: {coverage_decision}")
        self.store.record("coverage_decision", coverage_decision)
        self.store.transition(
            "COVERAGE_DECISION",
            allowed=self.registry.allowed(self.store.current_state(), "COVERAGE_DECISION"),
        )
        self._assert_gate("gate_coverage_after_impact")
        self._mark_executed("coverage")

    def branch(self, name: Optional[str]) -> None:
        if self._already_executed("branch"):
            return
        mode = self.store.get("automation_mode")
        if self.store.get("coverage_decision") == "UNKNOWN":
            raise RuntimeError(
                "Coverage is UNKNOWN; complete deeper impact analysis before branching."
            )
        if mode == "REGRESSION":
            if name is not None:
                raise ValueError("REGRESSION mode must not create a branch.")
            self.store.record(
                "branch",
                {
                    "decision": None,
                    "decision_valid": True,
                    "exists": False,
                    "created_before_modification": True,
                },
            )
        else:
            if not name or not name.startswith(
                ("feature/qa-auto-", "fix/qa-auto-")
            ):
                raise ValueError(
                    f"Invalid feature/fix branch name for {mode}: {name!r}"
                )
            self.store.record(
                "branch",
                {
                    "decision": name,
                    "decision_valid": True,
                    "exists": False,  # a decision never implies Git existence
                    "created_before_modification": True,
                },
            )
        self.store.transition(
            "BRANCH_DECISION",
            allowed=self.registry.allowed(self.store.current_state(), "BRANCH_DECISION"),
        )
        self._assert_gate("gate_branch_derived")
        self._mark_executed("branch")

    def confirm_branch_exists(self, decision: str, git_exists: bool) -> None:
        """Record whether the decided branch ACTUALLY exists in Git.

        This is the only way `branch.exists` becomes True: it requires a real,
        explicit Git confirmation. A decision alone never implies existence.
        """
        branch = dict(self.store.get("branch") or {})
        decision = decision if decision is not None else branch.get("decision")
        if git_exists and not decision:
            raise ValueError("Cannot mark a branch as existing without a decided name.")
        branch["decision"] = decision
        branch["exists"] = bool(git_exists)
        self.store.record("branch", branch)

    # -- execution ----------------------------------------------------------
    def record_local_execution(self, total: int, failed: int, skipped: int,
                               unresolved: int = 0, exit_code: int = 0) -> None:
        if self._already_executed("local_execution"):
            return
        if total <= 0 or exit_code != 0:
            raise ValueError("Local execution must run at least one test and exit 0.")
        self.store.record("local_execution_entered", True)
        self.store.record(
            "execution",
            {
                "total": total,
                "failed": failed,
                "skipped": skipped,
                "unresolved": unresolved,
                "exit_code": exit_code,
            },
        )
        self.store.transition(
            "LOCAL_EXECUTION",
            allowed=self.registry.allowed(self.store.current_state(), "LOCAL_EXECUTION"),
        )
        self._assert_gate("gate_local_clean")
        self._mark_executed("local_execution")

    def record_regression(self, total: int, failed: int, skipped: int,
                          unresolved: int = 0, exit_code: int = 0,
                          full_run_completed: Optional[bool] = None) -> None:
        if self._already_executed("regression"):
            return
        if total <= 0 or exit_code != 0:
            raise ValueError("Regression execution must run at least one test and exit 0.")
        data = {
            "total": total,
            "failed": failed,
            "skipped": skipped,
            "unresolved": unresolved,
            "exit_code": exit_code,
        }
        if full_run_completed is not None:
            data["full_run_completed"] = full_run_completed
        self.store.record("regression", data)
        self.store.transition(
            "REGRESSION_EXECUTION",
            allowed=self.registry.allowed(self.store.current_state(), "REGRESSION_EXECUTION"),
        )
        self._assert_gate("gate_regression_scope")
        self._assert_gate("gate_regression_clean")
        self._mark_executed("regression")

    # -- failure classification (six-category contract) --------------------------
    def classify_failure(
        self, test_id: str, evidence: FailureEvidence
    ) -> FailureClassification:
        """Classify a failing test from repeated/isolated execution evidence.

        Records the classification as state + evidence ONLY. It NEVER converts the
        failure into PASS, NEVER mutates the recorded regression `failed` count, and
        NEVER advances state (the run stays in FAILURE_ANALYSIS until routed).
        """
        cls = self.failure_classifier.classify(evidence)
        classifications = dict(self.store.get("failure_classifications", {}) or {})
        classifications[test_id] = cls.to_dict()
        self.store.record("failure_classifications", classifications)
        self.evidence.add(
            f"failure.{test_id}.classification", cls.to_dict(), kind="classification"
        )
        return cls

    def route_after_failure(self) -> str:
        """Decide the next stage after FAILURE_ANALYSIS (never soften a failure).

        HEALING is reached ONLY when every recorded failure is a healable
        AUTOMATION defect and the automation-mode healing cap allows it. A FLAKY,
        ENVIRONMENT_FAILURE, APPLICATION_DEFECT or UNKNOWN failure (or a mixed
        healable + non-healable set) never routes to HEALING: it routes to REVIEW,
        and the regression stays non-clean so FINAL_QUALITY_GATE remains blocked.
        """
        classifications = self.store.get("failure_classifications", {}) or {}
        if not classifications:
            raise RuntimeError(
                "No failure classifications recorded; cannot route after failure."
            )
        any_healable = any(c.get("healable") for c in classifications.values())
        all_healable = all(c.get("healable") for c in classifications.values())
        mode = self.store.get("automation_mode")

        if any_healable and not all_healable:
            # Mixed healable + non-healable: never heal the flake/environment part.
            return "REVIEW"
        if all_healable and self.healing.can_heal(mode or "REGRESSION"):
            self._assert_gate("gate_no_heal_on_flake_or_environment")
            return "HEALING"
        return "REVIEW"

    # -- review --------------------------------------------------------------
    def record_review_from_agent(self, result: AgentResult) -> str:
        """Record the reviewer verdict PARSED from the real agent result.

        The verdict is derived from the actual agent text via a deterministic parser;
        it is never hardcoded. The raw AgentResult, session id and full evidence are
        persisted alongside for audit. REJECT / UNKNOWN propagate to `gate_reviewer` =
        False (REJECT can never become APPROVED).
        """
        parsed = parse_review_verdict(result.text)
        self.store.record(
            "review",
            {
                "verdict": parsed,
                "session_id": result.session_id,
                "agent": result.agent,
                "exit_code": result.exit_code,
                "evidence": result.to_dict(),
            },
        )
        return parsed

    def review(self, verdict: str) -> None:
        if self._already_executed("review"):
            return
        existing = self.store.get("review") or {}
        if existing.get("evidence"):
            verdict = existing.get("verdict", "UNKNOWN")
        else:
            self.store.record("review", {"verdict": verdict})
        self.store.transition(
            "REVIEW",
            allowed=self.registry.allowed(self.store.current_state(), "REVIEW"),
        )
        self._assert_gate("gate_reviewer")
        self._mark_executed("review")

    # -- validation ------------------------------------------------------------
    def docker(
        self,
        build_exit_code: int,
        run_exit_code: int,
        robot_failed: int,
        robot_skipped: int,
        output_xml_exists: bool = False,
        image_id: Optional[str] = None,
        container_id: Optional[str] = None,
        output_xml: Optional[str] = None,
    ) -> None:
        """Record REAL Docker build + container run evidence.

        `output_xml_exists` must be backed by the artifact actually existing on disk
        after the container run; a bare exit code is never sufficient.
        """
        if self._already_executed("docker"):
            return
        self.store.record(
            "docker",
            {
                "build_exit_code": build_exit_code,
                "run_exit_code": run_exit_code,
                "robot_failed": robot_failed,
                "robot_skipped": robot_skipped,
                "unresolved": 0,
                "output_xml_exists": bool(output_xml_exists),
                "image_id": image_id,
                "container_id": container_id,
                "output_xml": output_xml,
            },
        )
        self.store.transition(
            "DOCKER_VALIDATION",
            allowed=self.registry.allowed(self.store.current_state(), "DOCKER_VALIDATION"),
        )
        self._assert_gate("gate_docker_clean")
        self._mark_executed("docker")

    def allure(self, results_present: bool, status_parity: bool,
               credential_leak: bool = False, report_index_exists: bool = True) -> None:
        if self._already_executed("allure"):
            return
        self.store.record(
            "allure",
            {
                "results_present": results_present,
                "status_parity": status_parity,
                "credential_leak": credential_leak,
                "report_index_exists": bool(report_index_exists),
            },
        )
        self.store.transition(
            "ALLURE_VALIDATION",
            allowed=self.registry.allowed(self.store.current_state(), "ALLURE_VALIDATION"),
        )
        self._assert_gate("gate_allure")
        self._mark_executed("allure")

    # -- final gate --------------------------------------------------------------
    def final_gate(self) -> Dict[str, Any]:
        if self._already_executed("final_gate"):
            cached = self.store.get("final_gate")
            return cached if isinstance(cached, dict) else {"all_satisfied": False, "results": {}}
        self.store.record("public_demo_environment", settings.PUBLIC_DEMO_ENVIRONMENT)
        res = self.gates.evaluate_final(self.store.snapshot())
        self.store.record("final_gate", res)
        self.store.transition(
            "FINAL_QUALITY_GATE",
            allowed=self.registry.allowed(self.store.current_state(), "FINAL_QUALITY_GATE"),
        )
        self.record_outcome(res["results"])
        self._mark_executed("final_gate")
        return res

    # -- Phase 2 git delivery (commit/push) -----------------------------------
    def record_commit_plan(self, plan: Any) -> None:
        """Record the machine-readable CommitPlan (dict) BEFORE any git mutation."""
        data = plan.to_dict() if hasattr(plan, "to_dict") else plan
        self.store.record("commit_plan", data)

    def authorize_commit(self, decision: bool = True) -> None:
        """Explicit, recorded human/orchestrator authorization to commit.

        `commit_authorized` is consumed by gate_commit_auth; a commit is refused
        without it. This never implies the plan is safe on its own.
        """
        self.store.record("commit_authorized", bool(decision))

    def commit(self, commit_hash: Optional[str],
               staged_files: Optional[List[str]] = None) -> None:
        if self._already_executed("commit"):
            return
        if not commit_hash:
            raise ValueError("commit() requires a real commit hash.")
        self.store.record(
            "commit",
            {
                "hash": commit_hash,
                "files": list(staged_files or []),
            },
        )
        self.store.transition(
            "COMMIT",
            allowed=self.registry.allowed(self.store.current_state(), "COMMIT"),
        )
        self._assert_gate("gate_commit_plan_clean")
        self._assert_gate("gate_commit_hash_recorded")
        self._assert_gate("gate_commit_auth")
        self._mark_executed("commit")

    def push(self, verified: bool, remote_head: Optional[str] = None,
             branch: Optional[str] = None) -> None:
        if self._already_executed("push"):
            return
        branch = branch or (self.store.get("branch") or {}).get("decision")
        self.store.record(
            "push",
            {
                "verified": bool(verified),
                "remote_head": remote_head,
                "branch": branch,
                "commit_hash": (self.store.get("commit") or {}).get("hash"),
            },
        )
        self.store.transition(
            "PUSH",
            allowed=self.registry.allowed(self.store.current_state(), "PUSH"),
        )
        self._assert_gate("gate_push_branch")
        self._assert_gate("gate_push_verified")
        self._mark_executed("push")

    # -- Phase 2 CI validation / healing ---------------------------------------
    def ci_validation(self, status: str, build_result: Optional[str] = None,
                      build_url: Optional[str] = None,
                      test_counts: Optional[Dict[str, int]] = None,
                      checkout_sha: Optional[str] = None) -> str:
        """Record a CI validation result and return its routing verdict.

        Routing is evidence-driven:
          - PASS          : the build was verified SUCCESS with 0 failed tests
                            -> gate_ci_verified asserted, the CI path continues.
          - FAIL          : a real build was observed but not clean -> healable up
                            to the cap (gate_ci_healing_cap), then CI_HEALING.
          - UNVERIFIED    : no observable build evidence -> NEVER a pass; the ci
                            gate stays blocked (DELIVERY_UNVERIFIED).
        """
        if self._already_executed("ci_validation"):
            prior = self.store.get("ci_validation") or {}
            return prior.get("status", "UNKNOWN")
        self.store.record(
            "ci_validation",
            {
                "status": status,
                "build_result": build_result,
                "build_url": build_url,
                "test_counts": dict(test_counts or {}),
                "checkout_sha": checkout_sha,
            },
        )
        self.store.transition(
            "CI_VALIDATION",
            allowed=self.registry.allowed(self.store.current_state(), "CI_VALIDATION"),
        )
        if status == "PASS":
            self._assert_gate("gate_ci_verified")
            self._mark_executed("ci_validation")
            return "PASS"
        if status == "FAIL":
            # A real failed build may heal only up to the cap; beyond that the run
            # must STOP (CICD_LOCKED) and never attempt a 4th auto-push.
            self._assert_gate("gate_ci_healing_cap")
            self._mark_executed("ci_validation")
            return "FAIL"
        self._assert_gate("gate_ci_verified")  # UNVERIFIED never satisfies it
        raise RuntimeError("CI validation UNVERIFIED: no real build evidence (never PASS).")

    def ci_healing(self, attempts: Optional[int] = None) -> None:
        """Enter CI_HEALING with an orchestrator-owned attempt counter (max 3).

        After the cap is reached the run must STOP (CICD_LOCKED); the gate refuses
        a 4th attempt. A CI healing transition clears the ci_validation marker so
        the re-validation path actually re-runs on the SAME pushed SHA.
        """
        if self._already_executed("ci_healing"):
            return
        attempts = attempts if attempts is not None else (int(self.store.get("ci_healing_attempts", 0) or 0) + 1)
        self.store.transition(
            "CI_HEALING",
            allowed=self.registry.allowed(self.store.current_state(), "CI_HEALING"),
        )
        # Cap is evaluated on the CURRENT attempt count: at most 3 entries.
        self._assert_gate("gate_ci_healing_cap")
        self.store.record("ci_healing_attempts", attempts)
        self.clear_execution_marker("ci_validation")
        self._mark_executed("ci_healing")

    # -- internal ---------------------------------------------------------------
    def _assert_gate(self, gate_id: str) -> None:
        snapshot = self.store.snapshot()
        if not self.gates.evaluate_gate(gate_id, snapshot):
            raise RuntimeError(f"Gate FAILED: {gate_id}")
