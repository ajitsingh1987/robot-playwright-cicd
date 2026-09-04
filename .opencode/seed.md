# Robot Framework Playwright Automation Project Seed

## Framework
- Robot Framework
- Robot Framework Browser / Playwright
- Python
- Allure
- Docker
- Jenkins
- GitHub

## Selenium
- Selenium must NOT be introduced.

## Test Architecture
- `tests/` contains business-level test scenarios only.
- `pages/` contains page-specific keywords and locators.
- `resources/` contains reusable framework/common keywords.
- `variables/` contains centralized configuration/test variables.

## Page Object Model
- No low-level locators inside test cases.
- Page-specific navigation, actions, locators and validations belong in `pages/`.
- Reusable browser lifecycle belongs in `resources/browser.resource`.

## Variables
- `variables/urls.py` must remain a real Python variable file.
- Example:
  ```
  RAHUL_SHETTY_URL = "https://rahulshettyacademy.com/"
  GOOGLE_URL = "https://www.google.com"
  ```
- Robot Framework imports it using: `Variables    ../variables/urls.py`

## Browser
- Use Robot Framework Browser / Playwright keywords.
- Do not create recursive wrapper keywords.
- Prefer clearly named wrappers such as:
  - `Start Browser`
  - `Open Page`
  - `Stop Browser`

## Test Preservation
- Never delete existing test coverage.
- Before modifying tests, understand existing behavior.
- Existing tests must remain passing unless the user explicitly requests a behavior change.

## Allure
- Do not break: `allure_robotframework:results/allure-results`

## CI/CD
- Keep Dockerfile and Jenkinsfile compatible.
- Do not modify them unless explicitly requested.

## Git Safety
- Never commit or push automatically.
- Do not perform git add/commit/push unless explicitly requested.

## Windows Compatibility
- Commands must be compatible with Windows PowerShell.
- Do not use Linux-only commands such as: `&&`, `cat`, `grep`, `sed`

## Current Project Baseline
- 3 tests, 3 passed, 0 failed.
- Robot Framework + Playwright
- Page Object structure
- Allure reporting
- Docker execution
- Jenkins CI/CD
- GitHub webhook