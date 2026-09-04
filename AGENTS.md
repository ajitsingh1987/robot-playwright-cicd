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