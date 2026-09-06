# AI QA Multi-Agent Project Rules

## 1. Project Objective

This project is an AI-assisted end-to-end QA automation system using:

- Python
- Robot Framework
- Robot Framework Browser
- Playwright
- Allure
- Docker
- Jenkins
- GitHub
- OpenCode AI Agents
- MCP

The objective is to automate the QA lifecycle from test-case planning through browser exploration, automation, execution, failure analysis, healing and reporting.

The architecture must support:

- UI automation
- API automation in future phases
- Mobile automation in future phases
- CI/CD execution
- AI-assisted failure analysis
- Controlled automation healing
- Evidence-based reporting

Current implementation focus is UI automation using Robot Framework Browser + Playwright.

---

## 2. Mandatory Technology Rules

Use:

- Python
- Robot Framework
- Robot Framework Browser
- Playwright
- Allure
- Docker
- Jenkins
- GitHub
- OpenCode Agents
- MCP

Do NOT introduce Selenium.

Do NOT replace Robot Framework Browser with Selenium.

Do NOT introduce another UI automation framework unless explicitly approved.

---

## 3. Project Architecture

Use the following structure:

```text
tests/
    Business-level Robot Framework test scenarios.

pages/
    Page-specific keywords, locators and UI actions.

resources/
    Reusable framework keywords and browser lifecycle.

variables/
    Python configuration and reusable test variables.

.opencode/
    OpenCode project configuration, seed instructions and agents.

.opencode/agents/
    Agent-specific instruction files.

results/
    Robot Framework and Allure execution results.

allure-report/
    Generated Allure reports.

Dockerfile
Jenkinsfile
AGENTS.md

```

---

## 4. Phase 2: Autonomous CI/CD Contract

The Orchestrator drives the Git -> Jenkins flow in this order:

1. FINAL_QUALITY_GATE is the ONLY authorizer of COMMIT. Any mandatory gate
   failure blocks the commit/push (CICD_LOCKED).
2. COMMIT stages only the intended files, runs a staged-diff secret scan,
   and creates one meaningful commit. Empty "kick" commits are forbidden.
3. PUSH pushes ONLY the active feature/fix branch
   (feature/qa-auto-* or fix/qa-auto-*). Autonomous push to origin/main is
   forbidden. The GitHub webhook is the ONLY mechanism allowed to start
   Jenkins job Robot-Playwright-Sanity; manual "Build Now" and remote-trigger
   tokens are prohibited.
4. CI_VALIDATION confirms Jenkins checks out the pushed SHA, executes every
   test under tests/, and publishes Allure results on the build.
5. CI_HEALING permits at most 3 autonomous repair attempts. A Git -> Jenkins ->
   Git loop is forbidden, and a healing fix must not modify deployment/release
   logic, Jenkinsfile, Dockerfile, or the test architecture.

---

## 5. Test File Ownership Rule (ONE REQUIREMENT -> ONE TEST FILE)

This is a HARD project rule. Every requirement is owned by exactly one
dedicated test file under `tests/`.

1. Before generating any test, inspect existing tests under `tests/` and build
   a requirement-to-file ownership map to prevent duplicate ownership.
2. Create and own a dedicated test file under `tests/` for every new
   requirement BEFORE writing the requirement's scenarios:
   `tests/<requirement-kebab-case>.robot`.
3. NEVER add scenarios of a new requirement to an unrelated existing test file
   (for example: never place Forgot Password scenarios inside the Login test
   file). An existing test file may ONLY contain scenarios of its own
   requirement.
4. Existing test files are owned by their original requirement and must not be
   used to host another requirement's scenarios.
5. Shared Page Objects under `pages/`, resources under `resources/`, and
   variables under `variables/` MAY be reused across requirements.
   Shared keyword/Page Object files are allowed; shared TEST files are not.
6. Refactors that split a mixed test file into per-requirement files are
   permitted and encouraged to restore the rule.
7. The Reviewer MUST reject the work if requirement isolation is violated
   (for example: a new requirement's scenarios living inside an unrelated
   test file). Such a violation is a blocking gate failure.

---

## 6. Requirement Classification Contract (HARD RULE)

Every incoming requirement MUST be classified BEFORE any automation
modification. The classification order is fixed:

```text
classify -> impact -> coverage decision -> branch decision -> modify
```

1. REQUIREMENT_CLASSIFICATION assigns exactly one AUTOMATION_MODE:
   - REGRESSION
   - NEW_AUTOMATION
   - AUTOMATION_ENHANCEMENT
   - AUTOMATION_FIX
2. COVERAGE_DECISION assigns exactly one value:
   - SUFFICIENT
   - PARTIAL
   - MISSING
   - UNKNOWN
3. IMPACT_ANALYSIS runs AFTER classification and BEFORE the coverage and
   branch decisions: classify -> impact -> coverage decision -> branch
   decision -> modify.
4. COVERAGE_DECISION is evaluated ONLY after IMPACT_ANALYSIS and assigns one
   value: SUFFICIENT / PARTIAL / MISSING / UNKNOWN.
5. Classification and coverage drive the branch decision:
   - COVERAGE_DECISION = SUFFICIENT and no new scenario intent
     -> AUTOMATION_MODE = REGRESSION: NO branch, NO automation
     modification, and NO commit, NO push; the regression run terminates at
     COMPLETED.
   - COVERAGE_DECISION = PARTIAL / MISSING with new scenarios required
     -> NEW_AUTOMATION or AUTOMATION_ENHANCEMENT: create a feature branch
     (feature/qa-auto-*) BEFORE any modification.
   - Defect in existing automation -> AUTOMATION_FIX: create a fix branch
     (fix/qa-auto-*) BEFORE any modification.
6. COVERAGE_DECISION = UNKNOWN requires deeper analysis before any branch
   or modification decision; it never authorizes a branch on guesswork and
   MUST never auto-assign AUTOMATION_MODE = NEW_AUTOMATION.

## 7. Impact-Driven Branch Lifecycle Contract (HARD RULE)

```text
classify -> impact -> coverage decision -> branch decision -> modify
```

1. CREATE_FEATURE_BRANCH happens BEFORE any automation modification and ONLY
   for NEW_AUTOMATION / AUTOMATION_ENHANCEMENT / AUTOMATION_FIX.
2. Branch naming contract (lowercase; spaces converted to hyphens; no unsafe
   characters, no duplicate hyphens, no secrets):
   - feature/qa-auto-<functionality>
   - feature/qa-auto-<functionality>-<enhancement>
   - fix/qa-auto-<functionality>-<problem>
3. Protected default branches (main/master) are NEVER directly modified for
   automation work.
4. REGRESSION-only work runs on the current/default branch with NO branch, NO
   modification, NO commit, NO push, and terminates at COMPLETED; it never
   enters COMMIT, PUSH, or PR_READY.
5. A dirty worktree is NEVER reset or stashed automatically. User changes are
   always preserved. Branch collisions are never blindly recreated; they must
   be resolved.
6. COMMIT and PUSH happen ONLY for NEW_AUTOMATION / AUTOMATION_ENHANCEMENT /
   AUTOMATION_FIX, ONLY after FINAL_QUALITY_GATE = PASS, and ONLY on the
   active feature/fix branch. Autonomous push to origin/main is forbidden.
7. PR_READY is the terminal stage for automation modes: report and stop. No
   auto-merge and no auto-PR creation. REGRESSION never reaches COMMIT, PUSH,
   or PR_READY.
8. Impact analysis and coverage decision are computed BEFORE the branch
   decision; a branch is never created or bypassed on guesswork. Regression
   failures are never auto-healed and never auto-converted into AUTOMATION_FIX.