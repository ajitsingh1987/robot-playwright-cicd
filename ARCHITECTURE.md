# Phase 1 — Target Architecture: Executable Orchestration Kernel

> Status: DESIGN (Phase 1)
> Base baseline: branch `feature/qa-auto-orangehrm-automation` @ `7dfe64f`, 32/32 PASS sacred baseline.
> Scope: Convert the prose-based `qa-orchestrator.md` contract into an executable,
> state-machine-driven orchestration layer (Orchestration-as-Code). No test/POM/Docker/
> Jenkins modification. This is a design document, not implementation.

---

## 1. Objective

The current orchestration is **DOCUMENTED only** — the full state machine, gates, healing
loop and CI contract live as markdown instructions consumed by an LLM. There is no
runnable kernel that independently drives, verifies and records the stages with evidence.

This phase defines the target architecture for an **executable orchestration kernel**
that:

1. Reads a short requirement (e.g. `Test login end-to-end`).
2. Runs the deterministic lifecycle:
   `classify -> impact -> coverage -> branch -> plan -> explore -> generate ->
   local_execute -> failure_analysis -> heal(<=3) -> re_execute -> regression_scope ->
   review -> docker -> allure -> quality_gate`.
3. Enforces every gate with **repository evidence** (never fabrication).
4. Persists immutable, auditable state + evidence at each transition.
5. Keeps the LLM as the "cognitive executor" for its sub-stages but the **kernel** owns
   workflow truth, state transitions and the healing counter.

## 2. Design Principles

- **Kernel owns truth, agents own work.** The kernel is deterministic code; agents
  (LLM) produce artifacts and evidence that the kernel verifies before advancing.
- **Every stage = state + transition + gate + evidence.** No stage can claim PASS without
  recorded evidence.
- **Evidence over assumption.** All gate inputs derive from repo/disks/artifacts, never
  from an agent's assertion.
- **No Selenium, no arbitrary waits, no JS shortcuts.**
- **PowerShell-compatible** on the local Windows host.
- **Read-mostly.** During Phase 1 ONLY design; the kernel must not modify sacred tests,
  Dockerfile or Jenkinsfile implicitly.

## 3. Layered Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ L1  INTERFACE     CLI / prompt entry                          │
│                    -> "Testing" HARNESS (dry-run, arch check) │
├──────────────────────────────────────────────────────────────┤
│ L2  KERNEL        Deterministic state machine (Python)        │
│                    -> StateStore, StageRegistry, GateEngine,  │
│                       ScopeEngine, HealingCounter, EvidenceBus│
├──────────────────────────────────────────────────────────────┤
│ L3  ADAPTERS      Robot runner, allure collector, git adapter,│
│                    browser MCP client, file/content probes     │
├──────────────────────────────────────────────────────────────┤
│ L4  AGENTS        planner, playwright, generator, healer,     │
│  (LLM cognitive)  reviewer, reporter, failure-analysis, cicd  │
│                    delegated for non-deterministic sub-steps  │
├──────────────────────────────────────────────────────────────┤
│ L5  CONFIG        stages.yaml, gates.yaml, taxonomy.yaml,     │
│                    agents/*.md, opencode.json, AGENTS.md      │
└──────────────────────────────────────────────────────────────┘
```

## 4. Core Components

### 4.1 `orchestra/` package (the kernel)

```text
orchestra/
    __init__.py
    state.py          # StateStore: immutable per-run state + transitions
    machine.py        # StageRegistry + transition table (state machine)
    gates.py          # GateEngine: evaluable gate predicates
    scope.py          # ScopeEngine: TARGETED / IMPACTED_REGRESSION / FULL_REGRESSION
    healing.py        # HealingCounter (max 3, orchestrator-owned)
    evidence.py       # EvidenceBus: capture/validate/tag evidence artifacts
    runner.py         # Adapter orchestration (robot, allure, git)
    adapters/
        robot.py
        allure.py
        git.py
        mcp.py
        probe.py      # file/content/import dependency resolver
    config/
        stages.yaml
        gates.yaml
        taxonomy.yaml
    report.py         # produces the 26-section report
```

### 4.2 State Model

Each run is an immutable, append-only event log:

```json
{
  "run_id": "uuid",
  "state": "REQUIREMENT_RECEIVED",
  "requirement": "Test login end-to-end",
  "automation_mode": "NEW_AUTOMATION",
  "coverage_decision": "MISSING",
  "impact": {
    "confidence": "HIGH",
    "affected_areas": ["Authentication"],
    "execution_scope": "FULL_REGRESSION",
    "evidence": ["tests/orangehrm_login.robot imports pages/orangehrm_login_page.robot"]
  },
  "branch": {"created_before_modification": true, "name": "feature/qa-auto-login"},
  "healing_attempts": 0,
  "gates": [],
  "events": [{"at": "...", "stage": "...", "outcome": "...", "evidence": ["..."]}]
}
```

Transitions are hard-coded, single-source-of-truth edges. State can transition ONLY via
the machine table. The LLM never directly sets state — it submits artifacts/evidence and
the kernel advances if gates pass.

### 4.3 Stage Registry (from the orchestrator contract)

```text
REQUIREMENT_RECEIVED
  -> REQUIREMENT_CLASSIFICATION        (mode: REGRESSION/NEW_AUTOMATION/AUTOMATION_ENHANCEMENT/AUTOMATION_FIX)
  -> IMPACT_ANALYSIS                    (evidence-based scope; gate A-11.4.4)
  -> COVERAGE_DECISION                  (SUFFICIENT/PARTIAL/MISSING/UNKNOWN; only after impact)
  -> BRANCH_DECISION                    (REGRESSION->NONE; AUTOMATION->feature/fix BEFORE modify)
  -> PLANNING
  -> EXPLORATION                        (real browser/MCP evidence)
  -> GENERATION                         (evidence-gated; refuses without verified evidence)
  -> LOCAL_EXECUTION                    (new tests only)
  -> FAILURE_ANALYSIS                   (if failures; never for REGRESSION-mode failures)
  -> HEALING                            (AUTOMATION only, max 3)
  -> RE_EXECUTION
  -> REGRESSION_EXECUTION               (computed scope; may expand, never shrink; FULL when trigger)
  -> REVIEW                             (explicit APPROVED/PASS only)
  -> DOCKER_VALIDATION
  -> ALLURE_VALIDATION
  -> FINAL_QUALITY_GATE
  -> COMPLETED | CICD_READY -> COMMIT -> PUSH -> CI_VALIDATION -> CI_HEALING -> PR_READY
```

Terminal / blocking states:
`COMPLETED` (REGRESSION terminator), `PR_READY` (AUTOMATION terminator),
`CICD_LOCKED`, `HEALING_EXHAUSTED`, `REGRESSION_FAILURE`, `BLOCKED`.

### 4.4 GateEngine

A gate is a small evaluable predicate over the run state:

```yaml
- id: gate_required_condition
  stage: LOCAL_EXECUTION
  check: "execution.passed == {total} and execution.failed == 0 and execution.skipped == 0 and execution.unresolved == 0"
- id: gate_regression_scope
  stage: REGRESSION_EXECUTION
  check: "impact.full_regression_needed == false OR execution.full_run_completed == true"
- id: gate_reviewer
  stage: REVIEW
  check: "reviewer.verdict in ['APPROVED','PASS']"
- id: gate_healing_cap
  stage: HEALING
  check: "healing.attempts < 3 and automation_mode != 'REGRESSION'"
```

All gate checks are pure functions over persisted state; nothing is inferred from agent
claims.

### 4.5 ScopeEngine

Deterministic resolution of `TARGETED / IMPACTED_REGRESSION / FULL_REGRESSION`:

1. `FULL_REGRESSION` when: confidence LOW, or shared/core component changed, or shared app
   area risk, or insufficient evidence to exclude a suite, or narrower scope failed.
2. `IMPACTED_REGRESSION` when: confidence HIGH/MEDIUM and a bounded proven set is impacted.
3. `TARGETED` when: confidence HIGH and only the requirement-owned suite is impacted.

Dependency proof uses file-level probes (imports, resource refs, POM references) — never
filename similarity. Default on uncertainty: expand toward FULL_REGRESSION.

### 4.6 HealingCounter

Orchestrator-owned. `max_attempts = 3`. Only incremented on failed heal+rerun. Never
resettable by Healer/Generator/Reviewer. Blocks the 4th attempt. REGRESSION-mode failures
never enter healing (immediate `REGRESSION_FAILURE -> BLOCKED`).

### 4.7 EvidenceBus

Every transition writes evidence (file paths/hashes) that the gate consumed. Claims like
"browser executed", "test passed", "allure generated" are only true when an artifact is
recorded and verified. Examples:

- `results/output.xml` + exit code for LOCAL/REGRESSION execution.
- `results/allure-results/` presence + status parity for ALLURE_VALIDATION.
- `docker run` exit code for DOCKER_VALIDATION.
- `.playwright-mcp/explore-*.md` + console/snapshot for EXPLORATION.

## 5. Failure Taxonomy (reconciled)

The framework uses **exactly six canonical categories** (HARD contract). Legacy names
(TEST_DEFECT / LOCATOR_DEFECT / DATA_DEFECT / CONFIGURATION_DEFECT /
ENVIRONMENT_INFRASTRUCTURE / ENVIRONMENT_DEFECT / EXTERNAL_SERVICE_DEFECT / FLAKE /
TRANSIENT_FAILURE) are translated deterministically via `taxonomy.yaml` `legacy_mapping`,
so older evidence stays comparable:

```yaml
AUTOMATION_DEFECT        # replace TEST_DEFECT + LOCATOR_DEFECT + AUTOMATION_DEFECT; HEAL
TEST_DATA_DEFECT         # replace DATA_DEFECT + CONFIGURATION_DEFECT; HEAL (deterministic only)
APPLICATION_DEFECT       # do not heal; report
ENVIRONMENT_FAILURE      # replace ENVIRONMENT_INFRASTRUCTURE + ENVIRONMENT_DEFECT +
                         # EXTERNAL_SERVICE_DEFECT; do not heal, do not modify automation
FLAKY                    # replace FLAKE + TRANSIENT_FAILURE; inconsistent repeats only; report
UNKNOWN                  # needs more evidence; never auto-heal
```

Public-demo protection is a HARD framework guarantee: when the target is a public demo
(`PUBLIC_DEMO_ENVIRONMENT=true` in `config/settings.py`, env-overridable via
`QA_PUBLIC_DEMO_ENVIRONMENT`), any failure carrying a concrete environment marker (page
not rendered, `/auth/validate` hang, network timeout, server unresponsive) is classified
`ENVIRONMENT_FAILURE` on first occurrence, is never healable (guard
`gate_public_demo_environment`), never consumes a healing attempt, and never results in a
locator/assertion/wait change. The final gate derives a deterministic outcome — GREEN /
RED_AUTOMATION / RED_DATA / RED_APPLICATION / RED_ENVIRONMENT / RED_FLAKY /
RED_UNKNOWN — where a RED_* outcome (incl. RED_ENVIRONMENT) is legitimate and NEVER
masquerades as a pass.

The 8/7->6 mapping is declared in `taxonomy.yaml` and validated at load (unit-tested).

## 6. Security Integration

- Credentials remain env/config-driven; kernel **never** prints or commits them.
- `variables/credentials.py` plaintext fallbacks are flagged (Phase 1 design: remove
  fallbacks; fail-fast if env missing, or gate on explicit config).
- Secret scan on any staged diff (Phase 2 COMMIT path) is a kernel hook.
- Evidence artifacts are scanned for `Password/Tokend` leakage before allowing
  ALLURE_VALIDATION / report.

## 7. Test / Verification Strategy for the Kernel

- **Dry-run harness**: run the machine end-to-end against mock evidence to validate all
  transitions and gate logic — proves delegation, state transitions, healing loop
  bounds, branch decision rules. This does NOT claim browser/test PASS.
- **Architecture validation mode**: read-only; probes structure/contracts; refuses any
  execution.
- **Regression guard**: any kernel change re-runs the 32/32 baseline before a claim of
  non-regression.
- Golden-path + failure-branch unit tests for the state machine (transitions, gate
  predicates, scope rules, healing cap).

## 8. Guardrails

- NEVER modify `tests/`, `pages/`, `resources/`, `variables/`, `Dockerfile`,
  `Jenkinsfile` implicitly. Only the authorized requirement's change set + the new
  `orchestra/` + `ARCHITECTURE.md` are touched.
- Never re-assert-away a test, never delete/skip, never arbitrary sleeps.
- Never push origin/main; never auto-merge; never auto-PR.
- Dirty worktrees never reset/stashed automatically.
- Evidence or die: no artifact = no PASS.

## 9. Deliverables for this Phase

| Artifact | Type |
|---|---|
| This `ARCHITECTURE.md` | Design |
| `orchestra/` package skeleton | Implementation |
| `config/stages.yaml`, `gates.yaml`, `taxonomy.yaml` | Configuration |
| Dry-run + arch-validation harness + unit tests | Verification |
| Post-Phase-1 audit (DOCUMENTED/IMPLEMENTED/EXECUTABLE/PARTIAL/MISSING) | Report |

## 10. Design Decisions (LOCKED)

Confirmed during the Phase 1 design checkpoint:

1. **Kernel language/runtime: PYTHON** — matches the Robot Framework/Python ecosystem;
   runs Robot tests and collects evidence directly.
2. **StateStore backend: LOCAL JSONL EVENT LOG** — append-only, auditable, diffable;
   good for a single-node QA kernel.
3. **Kernel integration: STANDALONE PYTHON CLI** — the kernel is a Python CLI that
   delegates to opencode/LLM agents and runs Robot directly; clear separation of
   deterministic kernel vs cognitive agents.
4. **LLM boundary: KERNEL CALLS AGENTS VIA CLI** — kernel invokes agent subprocesses
   (plan/explore/generate/heal/review), then verifies their recorded evidence before
   advancing state.

These are locked and NOT to be re-opened during Phase 2 implementation unless a hard
technical blocker emerges.
