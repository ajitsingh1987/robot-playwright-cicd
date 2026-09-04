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

---

## 4. Phase 2: Autonomous CI/CD Contract

The Orchestrator drives the Git -> Jenkins flow in this order:

1. FINAL_QUALITY_GATE is the ONLY authorizer of CI_COMMIT. Any mandatory gate
   failure blocks the commit/push (CICD_LOCKED).
2. CI_COMMIT stages only the intended files, runs a staged-diff secret scan,
   and creates one meaningful commit. Empty "kick" commits are forbidden.
3. CI_TRIGGER pushes to origin/main. The GitHub webhook is the ONLY mechanism
   allowed to start Jenkins job Robot-Playwright-Sanity; manual "Build Now"
   and remote-trigger tokens are prohibited.
4. CI_VALIDATION confirms Jenkins checks out the pushed SHA, executes every
   test under tests/, and publishes Allure results on the build.
5. CI_HEALING permits at most 3 autonomous repair attempts. A Git -> Jenkins ->
   Git loop is forbidden, and a healing fix must not modify deployment/release
   logic, Jenkinsfile, Dockerfile, or the test architecture.