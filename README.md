# Robot Framework + Playwright QA Automation (CI/CD)

AI-assisted end-to-end QA automation for the OrangeHRM demo application using
Robot Framework Browser (Playwright), Allure reporting, Docker and Jenkins.

## Stack

- Python 3.12 + Robot Framework 7
- Robot Framework Browser (Playwright) -- Selenium is not used by design
- Allure (allure-robotframework)
- Docker, Jenkins, GitHub webhook-driven CI/CD
- OpenCode AI agents + MCP (`.opencode/`)

## Structure

```text
tests/       Business-level Robot Framework test scenarios (one file per requirement)
pages/       Page-specific keywords, locators and UI actions (POM)
resources/   Reusable framework keywords and browser lifecycle
variables/   Python configuration and test variables
data/        Requirement-specific test data
orchestra/   Phase 2 executable orchestration kernel (classify -> impact -> coverage -> branch -> gates)
specs/       Requirement test plans
results/     Robot Framework and Allure execution results
```

Roadmap: `AGENTS.md` (project hard rules), `ARCHITECTURE.md` (Phase 1 baseline).

## Local run

```text
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\rfbrowser init
.venv\Scripts\python -m robot --outputdir results tests
```

## Framework / Phase 2 validation

```text
.venv\Scripts\python -m pytest orchestra/tests -q
.venv\Scripts\python -m orchestra arch
.venv\Scripts\python -m orchestra dry-run --mode NEW_AUTOMATION --scope FULL_REGRESSION
.venv\Scripts\python -m orchestra local-gate
```

`local-gate` is the executable LOCAL QUALITY GATE: it runs the checks above
(plus a branch-policy check and, when executed artifacts exist, the CI quality
gate) and exits `0` GREEN / `1` RED. GREEN is the ONLY authorizer of COMMIT/PUSH
and its verdict (`results/run/local-quality-gate.json`) is bound to the current
worktree fingerprint (status code + path + file CONTENT hash + branch + HEAD),
so a stale GREEN can never authorize new or content-modified changes. A change
that touches the Robot automation surface (`tests/`, `pages/`, `resources/`,
`variables/`, `data/`, `*.robot`, `*.resource`) requires actual Robot execution
evidence; without it the gate is RED. The only wired real commit/push path is
`python -m orchestra deliver --run-id <id> [--execute]`
(`CommitPlanner` -> `local_gate_fresh` -> `GitDelivery`).

## CI/CD

The GitHub webhook is the only allowed trigger for the Jenkins pipeline
`Robot-Playwright-Sanity`. The job consumes the wildcards `*/feature/qa-auto-*`
AND `*/fix/qa-auto-*` (never a hard-coded branch). The pipeline builds the Docker
image, runs the orchestrator gates, executes all Robot tests, and publishes
Allure results.
<!-- Jenkins webhook validation: 2026-09-21 -->
