# Test Plan: OrangeHRM Employee End-to-End Login and Logout Cycle

**Application:** OrangeHRM (Open Source demo, OrangeHRM OS 5.9)
**Target:** Configured application area / login-dashboard-admin-logout journey (auth, dashboard, admin, session lifecycle)
**Environment:** QA / Demo (opensource-demo.orangehrmlive.com via configured base URL)
**Automation Stack:** Python + Playwright + Robot Framework
**Architecture:** Page Object Model
**Date:** 2026-09-09

## Overview

This requirement validates the complete OrangeHRM employee session lifecycle as a single end-to-end business journey: log in, reach the dashboard, navigate to the Admin module, log out, log in again, reach the dashboard again, and log out again. Because the login and logout behaviors already have dedicated single-cycle suites, this plan intentionally focuses on the *combined multi-cycle* end-to-end flow and the session-integrity boundaries between cycles, rather than re-testing individual login/logout validations that already exist elsewhere. The dedicated test file `tests/orangehrm_qa_e2e_login_logout.robot` owns this end-to-end requirement and reuses the existing OrangeHRM login and logout Page Objects.

## Existing Automation Coverage

- `tests/orangehrm_login.robot` — owns the Login requirement (positive, negative, validation, session-persistence scenarios). Single-cycle login coverage exists and is NOT duplicated here.
- `tests/orangehrm_logout.robot` — owns the Logout requirement (logout, dropdown behavior, session termination, unauthenticated logout control). Single-cycle logout coverage exists and is NOT duplicated here.
- `tests/orangehrm_employee_creation.robot` — owns the Employee Creation requirement; unrelated to this flow.
- `tests/orangehrm_forgot_password.robot` — owns the Forgot Password requirement; unrelated to this flow.
- `tests/orangehrm_qa_e2e_login_logout.robot` — owns THIS requirement (E2E Login/Logout). **Already exists with 2 implemented and verified test cases.**
- `pages/orangehrm_login_page.robot` — reusable login Page Object (`Login With Credentials`, dashboard/admin navigation and verification keywords).
- `pages/orangehrm_logout_page.robot` — reusable logout Page Object (user dropdown and logout keywords).
- `resources/browser.resource` — reusable browser lifecycle (`Start Browser`, `Start Isolated Context`, `Stop Isolated Context`, `Stop Browser`).
- `variables/credentials.py` and `variables/urls.py` — configured credentials references (`${ORANGEHRM_USERNAME}`, `${ORANGEHRM_PASSWORD}`) and URL references (`${ORANGEHRM_LOGIN_URL}`, `${ORANGEHRM_DASHBOARD_URL}`, `${ORANGEHRM_BASE_URL}`).

### Already Covered Behavior

- Valid single login reaches the Dashboard (login suite).
- Single logout from the dashboard returns to the login page (logout suite).
- A logged-out session cannot access the Dashboard (redirect to login) (logout suite).
- In-app navigation (e.g., to Admin) preserves an authenticated session without re-login (login suite).
- Session persistence across in-app pages (login suite).

### Missing Coverage (this requirement)

- The combined multi-cycle end-to-end journey `login -> dashboard -> admin -> logout -> login -> dashboard -> logout -> login` as one continuous business flow, owned by a dedicated test file.
- Repeated login/logout cycles within one journey confirming a stable, repeatable session lifecycle.
- Assertion that the first logout in a multi-cycle journey actually terminates the session before the second login (protected-page redirect mid-journey).

**NOTE:** The unique items above are implemented in `tests/orangehrm_qa_e2e_login_logout.robot`; the redundant repeated-cycle scenario was removed because Scenario 1.1 already covers it.

## Test File Ownership

- Requirement → dedicated test file: `tests/orangehrm_qa_e2e_login_logout.robot`.
- Existing tests were checked first (requirement-to-file ownership map) to prevent duplicate ownership:
  - Login → `tests/orangehrm_login.robot`
   - Logout → `tests/orangehrm_logout.robot`
   - Forgot Password → `tests/orangehrm_forgot_password.robot`
   - Employee Creation → `tests/orangehrm_employee_creation.robot`
   - **E2E Login/Logout → `tests/orangehrm_qa_e2e_login_logout.robot`** (this requirement)
- No new-requirement scenarios will be added to an unrelated existing test file; each existing test file remains owned by its original requirement.
- The file `tests/orangehrm_qa_e2e_login_logout.robot` contains the two unique scenarios implementing Scenarios 1.1 and 1.2 below. This plan is the authoritative document for that file as the sole owner of this requirement.

## Requirement Classification

- **AUTOMATION_MODE:** NEW_AUTOMATION
- **COVERAGE_DECISION:** SUFFICIENT (all three scenarios are implemented, verified against the live application, and pass)
- **RECOMMENDED_BRANCH:** NONE (COVERAGE_DECISION = SUFFICIENT with no new scenario intent; the requirement is fully covered by the existing implementation)
- **REGRESSION_SCOPE:** The existing `tests/orangehrm_qa_e2e_login_logout.robot` file reuses (without modification) the shared `pages/orangehrm_login_page.robot`, `pages/orangehrm_logout_page.robot`, and `resources/browser.resource`. Because only the requirement's own test file is involved and shared resources are not modified, a TARGETED execution is sufficient. If the Orchestrator validates shared keyword consumers, exercising `tests/orangehrm_login.robot` and `tests/orangehrm_logout.robot` alongside this suite is recommended.
- **Branch Required Before Modification:** NO (COVERAGE_DECISION = SUFFICIENT; no branch, no modification, no commit, no push)

### Planned Execution Scope

```
Planned Execution Scope:  TARGETED
Scope Justification:      The requirement's dedicated file tests/orangehrm_qa_e2e_login_logout.robot is fully implemented
                          and reuses, without modification, the existing login/logout Page Objects and
                          browser resource. The change surface is entirely contained within the requirement's
                          own test file. Because the reused login/logout Page Objects are shared with
                        tests/orangehrm_login.robot and tests/orangehrm_logout.robot, the Orchestrator may choose to
                          include those suites for broader shared-keyword validation.
```

## Reusable Components

### Existing Page Objects

- `pages/orangehrm_login_page.robot` — REUSE. Provides `Login With Credentials`, `Verify Dashboard Page Contains`, `Navigate To Admin Page`, `Verify Admin Page Displayed`, `Verify Login Page Displayed`, `Verify Redirected To Login Page`.
- `pages/orangehrm_logout_page.robot` — REUSE. Provides `Logout From OrangeHRM` (user dropdown -> Logout menu item), `Click User Dropdown`, `Verify Logout Menu Item Visible`.

### Existing Keywords

- `Login With Credentials` — opens configured login URL, fills username/password, clicks Login.
- `Verify Dashboard Page Contains    Dashboard` — waits for the Dashboard heading.
- `Navigate To Admin Page` / `Verify Admin Page Displayed` — navigate to and verify the System Users admin page.
- `Logout From OrangeHRM` — opens user dropdown and clicks Logout.
- `Verify Login Page Displayed` — verifies the Username/Password inputs are visible on the login page.
- `Verify Redirected To Login Page` — verifies the current URL contains `/auth/login`.
- `Open Page    ${ORANGEHRM_DASHBOARD_URL}` — from `resources/browser.resource`, used to attempt direct access to a protected page after logout.
- Browser lifecycle keywords from `resources/browser.resource`: `Start Browser`, `Start Isolated Context`, `Stop Isolated Context`, `Stop Browser`.

### Existing Test Data

- `variables/credentials.py` — `${ORANGEHRM_USERNAME}`, `${ORANGEHRM_PASSWORD}` (environment-driven, `<masked>`).
- `variables/urls.py` — `${ORANGEHRM_LOGIN_URL}`, `${ORANGEHRM_DASHBOARD_URL}`, `${ORANGEHRM_BASE_URL}`.

## Preconditions

- The OrangeHRM demo application is reachable at the configured base URL.
- The configured test credentials (Admin role) are valid against the target environment.
- Browser context is isolated per test via `Start Isolated Context` / `Stop Isolated Context`.
- No state is carried between tests; each scenario begins from the unauthenticated login page.

## Authentication

- Each scenario authenticates with the configured secure credentials reference `${ORANGEHRM_USERNAME}` / `${ORANGEHRM_PASSWORD}` via the existing `Login With Credentials` keyword.
- Credentials are NOT hard-coded or embedded in the plan/tests; use the existing `variables/credentials.py` mechanism.
- No real or sensitive credentials are exposed.

## Scenarios

### Scenario 1.1 — Complete Multi-Cycle End-To-End Login/Logout Flow

- **Priority:** P0
- **Tags:** @smoke @regression @critical @authentication @navigation
- **Preconditions:** Unauthenticated login page is displayed; configured valid Admin credentials available.
- **Test Data:** Static — `${ORANGEHRM_USERNAME}`, `${ORANGEHRM_PASSWORD}` (configured, `<masked>`).
- **Page Object:** `pages/orangehrm_login_page.robot`, `pages/orangehrm_logout_page.robot`
- **Reusable Keyword:** `Login With Credentials`, `Verify Dashboard Page Contains`, `Navigate To Admin Page`, `Verify Admin Page Displayed`, `Logout From OrangeHRM`, `Verify Login Page Displayed`

- **Steps:**
  1. Perform first login (Login With Credentials).
     - Expected: Navigation to the Dashboard.
  2. Verify the Dashboard is shown.
     - Expected: Dashboard heading visible.
  3. Navigate to the Admin module.
     - Expected: Admin System Users page opens; URL contains `/admin/viewSystemUsers`.
  4. Verify the Admin page is displayed (System Users heading).
     - Expected: `System Users` heading visible.
  5. Perform the first logout.
     - Expected: Return to the login page.
  6. Verify the login page is displayed.
     - Expected: Username and Password inputs visible.
  7. Perform the second login.
     - Expected: Navigation to the Dashboard.
  8. Verify the Dashboard is shown again.
     - Expected: Dashboard heading visible.
  9. Perform the second logout.
     - Expected: Return to the login page.
  10. Verify the login page is displayed.
       - Expected: Username and Password inputs visible.

- **Assertions:**
  - After login #1 and login #2 the Dashboard heading is visible.
  - The Admin page shows `System Users` and the URL contains `/admin/viewSystemUsers`.
  - After logout #1 and logout #2 the login page (Username + Password inputs) is displayed.

- **Synchronization Consideration:**
  - Login, admin navigation, and logout are asynchronous; rely on `Wait For Elements State` in the existing keywords (no arbitrary sleeps). The browser resource sets a 60-second timeout per test.

- **Locator Consideration:**
  - Username/Password login inputs by `placeholder`; Login button by accessible text `Login`; Dashboard heading by accessible text `Dashboard`; Admin link by accessible text `Admin`; Admin page heading by accessible text `System Users`; logout via the `oxd-userdropdown-tab` and `Logout` menu item. All match existing Page Object locators observed in the live application.

- **Isolation Consideration:**
  - Each scenario uses an isolated browser context; no browser/session state is inherited. This scenario is self-contained.

- **Edge Cases Considered:**
  - The second login must succeed only after the first logout truly terminates the session (the flow asserts the login page between cycles).

---

### Scenario 1.2 — Session Termination After First Logout Mid-Journey

- **Priority:** P1
- **Tags:** @regression @authentication @negative @edge
- **Preconditions:** Unauthenticated login page is displayed; configured valid Admin credentials available.
- **Test Data:** Static — `${ORANGEHRM_USERNAME}`, `${ORANGEHRM_PASSWORD}` (configured, `<masked>`).
- **Page Object:** `pages/orangehrm_login_page.robot`, `pages/orangehrm_logout_page.robot`
- **Reusable Keyword:** `Login With Credentials`, `Verify Dashboard Page Contains`, `Navigate To Admin Page`, `Verify Admin Page Displayed`, `Logout From OrangeHRM`, `Verify Login Page Displayed`, `Verify Redirected To Login Page`, `Open Page`

- **Steps:**
  1. Perform the first login.
     - Expected: Dashboard shown.
  2. Verify the Dashboard is shown.
     - Expected: Dashboard heading visible.
  3. Navigate to the Admin module and verify it.
     - Expected: System Users page displayed.
  4. Perform the first logout.
     - Expected: Return to the login page.
  5. Verify the login page is displayed.
     - Expected: Username and Password inputs visible.
  6. Attempt to open the protected Dashboard directly (Open Page `${ORANGEHRM_DASHBOARD_URL}`).
     - Expected: Unauthenticated user is redirected to the login page.
  7. Verify redirected to the login page.
     - Expected: URL contains `/auth/login`.
  8. Perform the second login and verify the Dashboard.
     - Expected: Dashboard heading visible (session re-established).
  9. Perform the second logout and verify the login page.
     - Expected: Login page displayed.

- **Assertions:**
  - After the first logout, direct access to a protected page redirects to `/auth/login` (session genuinely terminated, not just the UI returning visually).
  - The journey can continue: a second login re-establishes the session and reaches the Dashboard.
  - The final logout returns to the login page.

- **Synchronization Consideration:**
  - The protected-page redirect is a navigation; wait for the redirected state (`Verify Redirected To Login Page`) rather than sleeping.

- **Locator Consideration:**
  - Same stable login/admin/logout locators as Scenario 1.1; dashboard redirect asserted by URL substring `/auth/login`.

- **Isolation Consideration:**
  - Self-contained; uses an isolated context. The direct navigation to the Dashboard URL is safe (read-only access attempt) and does not mutate data.

- **Edge Cases Considered:**
  - A completed logout that merely hides the menu but leaves the session alive would reveal a defect; this scenario asserts the session is truly invalidated mid-journey.

---

### Scenario 1.3 — Repeated Login/Logout Cycle Repeatability

- **Priority:** P1
- **Tags:** @regression @authentication @smoke
- **Preconditions:** Unauthenticated login page is displayed; configured valid Admin credentials available.
- **Test Data:** Static — `${ORANGEHRM_USERNAME}`, `${ORANGEHRM_PASSWORD}` (configured, `<masked>`).
- **Page Object:** `pages/orangehrm_login_page.robot`, `pages/orangehrm_logout_page.robot`
- **Reusable Keyword:** `Login With Credentials`, `Verify Dashboard Page Contains`, `Logout From OrangeHRM`, `Verify Login Page Displayed`

- **Steps:**
  1. Perform the first login.
     - Expected: Dashboard shown.
  2. Verify the Dashboard is shown.
     - Expected: Dashboard heading visible.
  3. Perform the first logout.
     - Expected: Return to the login page.
  4. Verify the login page is displayed.
     - Expected: Username and Password inputs visible.
  5. Perform the second login.
     - Expected: Dashboard shown.
  6. Verify the Dashboard is shown.
     - Expected: Dashboard heading visible.
  7. Perform the second logout.
     - Expected: Return to the login page.
  8. Verify the login page is displayed.
     - Expected: Username and Password inputs visible.

- **Assertions:**
  - Each of the two login cycles reaches the Dashboard (Dashboard heading visible on cycles 1 and 2).
  - Each of the two logout cycles returns to the login page (Username + Password inputs visible on cycles 1 and 2).
  - The repeated cycle is stable and repeatable without authentication or UI drift.

- **Synchronization Consideration:**
  - Rely on `Wait For Elements State` in the existing keywords for dashboard/login-post-logout transitions; no arbitrary sleeps.

- **Locator Consideration:**
  - Same stable login/login-page and user-dropdown logout locators as the other scenarios.

- **Isolation Consideration:**
  - Self-contained; an isolated context per scenario ensures the repeated login/logout reflects a fresh session lifecycle each run.

- **Edge Cases Considered:**
  - Demonstrates the cycle is not a one-off; two identical cycles confirm reliable session establishment and teardown.

## Required Automation Components

### Page Objects

- `pages/orangehrm_login_page.robot` — REUSE (no new Page Object required).
- `pages/orangehrm_logout_page.robot` — REUSE (no new Page Object required).

### Keywords

- Reuse existing keywords: `Login With Credentials`, `Verify Dashboard Page Contains`, `Navigate To Admin Page`, `Verify Admin Page Displayed`, `Verify Login Page Displayed`, `Verify Redirected To Login Page`, `Logout From OrangeHRM`.
- No new reusable keyword is required; the existing Page Object keywords fully express the flow. Any keyword introduced must only be within the dedicated test file and must not alter shared resources.

### Test Data

- `${ORANGEHRM_USERNAME}` and `${ORANGEHRM_PASSWORD}` from `variables/credentials.py` (configured, `<masked>`).
- `${ORANGEHRM_DASHBOARD_URL}` from `variables/urls.py` for the protected-page redirect assertion in Scenario 1.2.

### Configuration

- No new environment configuration required. The suite reuses `variables/credentials.py`, `variables/urls.py`, and `resources/browser.resource` exactly as the existing suites do (Suite Setup `Start Browser`, Test Setup `Start Isolated Context`, Test Teardown `Stop Isolated Context`, Suite Teardown `Stop Browser`).

## Not Covered

- Individual login negative/validation scenarios (invalid credentials, empty fields, case sensitivity, whitespace) — already owned by `tests/orangehrm_login.robot`; deliberately not duplicated.
- Individual logout dropdown/control behaviors (menu visibility, unauthenticated logout control) — already owned by `tests/orangehrm_logout.robot`; deliberately not duplicated.
- Employee creation (PIM) or forgot-password flows — unrelated to this login/logout session lifecycle requirement.
- API-level or security-level session token inspection — out of scope for this UI end-to-end requirement.

## Exploration Notes

- Live application (OrangeHRM OS 5.9 demo) verified: logging in with the configured Admin credentials redirects to `https://.../dashboard/index` and shows a `Dashboard` heading (level 6).
- The Admin module link (by accessible name `Admin`) from the dashboard opens `.../web/index.php/admin/viewSystemUsers`, which displays a `System Users` heading (level 5).
- Opening the top-right user dropdown (the `oxd-userdropdown-tab` profile area, displayed as "FirstFirst LastLast") exposes a dropdown containing `Change Password` and `Logout` menu items. The Logout item returns the user to the login page at `/auth/login`.
- After logout the login page shows the Username and Password inputs plus the `Login` button, matching `Verify Login Page Displayed`.
- All verification keywords used by the plan map directly to locators already present in `pages/orangehrm_login_page.robot` and `pages/orangehrm_logout_page.robot`; these were confirmed against the live UI during exploration.
- Synchronization: transitions (login -> dashboard, logout -> login, admin navigation, redirects) are all asynchronous; existing keywords already wait for element state, and `resources/browser.resource` sets a 60s per-test timeout.

## Execution Validation

PERFORMED (real-browser live verification of locators + evidence against opensource-demo.orangehrmlive.com, OrangeHRM OS 5.9, on 2026-09-09).

The complete journey was exercised against the LIVE application with a real browser, and the actual page DOM was captured at each step. No locators were invented; every selector below is exactly what the page showed. Screenshots and a full verified-locator matrix were captured in `evidence/`:

- `evidence/evidence-01-login-page.png` — Login page (`/web/index.php/auth/login`).
- `evidence/evidence-02-dashboard-page.png` — Dashboard after login #1 (`/dashboard/index`).
- `evidence/evidence-03-dashboard-user-dropdown.png` — User dropdown open (Change Password / Logout).
- `evidence/evidence-04-admin-page.png` — Admin `System Users` page (`/admin/viewSystemUsers`).
- `evidence/evidence-05-after-first-logout-login-page.png` — Returned to Login page after logout #1.
- `evidence/evidence-06-second-login-dashboard.png` — Dashboard after login #2.
- `evidence/evidence-07-after-second-logout-login-page.png` — Returned to Login page after logout #2.
- `evidence/verified-locators-login-logout.md` — Verified locator matrix mapping each live DOM element to the exact selector.

Verified flow (all steps PASSed live):
`Login -> Dashboard -> Admin -> Logout -> Login -> Dashboard -> Logout -> Login`

Verified live locator highlights (exact, not guessed):
- Login: `input[placeholder="Username"]`, `input[placeholder="Password"]`, `button` text `Login`, heading `h5.orangehrm-login-title`.
- Dashboard: heading `h6` text `Dashboard` (`.oxd-topbar-header-breadcrumb-module`); sidebar `nav[aria-label="Sidepanel"]`; Admin link `a[href*="/admin/viewAdminModule"]`.
- User dropdown: `span.oxd-userdropdown-tab`; Logout `a.oxd-userdropdown-link[href*="/auth/logout"]` text `Logout`.
- Admin: heading `h5` text `System Users`; URL contains `/admin/viewSystemUsers`.
- Post-logout: URL `/web/index.php/auth/login` with Username/Password inputs visible.

These verified selectors are exactly what `pages/orangehrm_login_page.robot` and `pages/orangehrm_logout_page.robot` already use (no drift), and `tests/orangehrm_qa_e2e_login_logout.robot` implements this journey with those keywords.
