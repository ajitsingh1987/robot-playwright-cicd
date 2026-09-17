*** Settings ***
Library    Browser
Variables    ../variables/credentials.py
Variables    ../variables/urls.py
Resource    ../resources/browser.resource
Resource    ../pages/orangehrm_login_page.robot
Resource    ../pages/orangehrm_logout_page.robot
Suite Setup    Start Browser
Test Setup    Start Isolated Context
Test Teardown    Stop Isolated Context
Suite Teardown    Stop Browser

*** Test Cases ***
User Can Logout From OrangeHRM
    [Documentation]    Verify an authenticated user can log out from the dashboard and return to the login page.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Logout From OrangeHRM
    Verify Login Page Displayed

Logout Menu Item Appears When User Dropdown Opens
    [Documentation]    Verify the user dropdown is hidden by default and exposes the Logout menu item when opened.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Verify User Dropdown Tab Visible
    Verify User Dropdown Menu Hidden
    Click User Dropdown
    Verify Logout Menu Item Visible

Logged Out Session Cannot Access Dashboard
    [Documentation]    Verify the session is terminated so a protected page redirects an already-logged-out user to login.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Logout From OrangeHRM
    Open Page    ${ORANGEHRM_DASHBOARD_URL}
    Verify Redirected To Login Page

Logout Control Is Not Available To Unauthenticated Users
    [Documentation]    Verify unauthenticated users have no logout control on the login page.
    Go To OrangeHRM Login Page
    Verify User Dropdown Tab Hidden
    Verify User Dropdown Menu Hidden