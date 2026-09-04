*** Settings ***
Library    Browser
Variables    ../variables/credentials.py
Variables    ../variables/urls.py
Resource    ../resources/browser.resource
Resource    ../pages/orangehrm_login_page.robot
Suite Setup    Start Browser
Test Setup    Start Isolated Context
Test Teardown    Stop Isolated Context
Suite Teardown    Stop Browser

*** Test Cases ***
Login Page Is Available
    [Documentation]    Verify the OrangeHRM login page loads successfully.
    Go To OrangeHRM Login Page
    Verify Login Page Displayed

Valid OrangeHRM Login
    [Documentation]    Verify a user can log in with valid credentials.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard

Valid Login Can Be Logged Out
    [Documentation]    Verify a valid session can be ended.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Logout From OrangeHRM

Invalid Username With Valid Password
    [Documentation]    Reject an unknown username.
    Login With Credentials    invalid_user    ${ORANGEHRM_PASSWORD}
    Verify Error Message Contains    Invalid credentials

Valid Username With Invalid Password
    [Documentation]    Reject an incorrect password.
    Login With Credentials    ${ORANGEHRM_USERNAME}    wrongpassword
    Verify Error Message Contains    Invalid credentials

Invalid Username And Password
    [Documentation]    Reject two invalid credentials.
    Login With Credentials    invalid_user    wrongpassword
    Verify Error Message Contains    Invalid credentials

Empty Username
    [Documentation]    Require a username when the password is supplied.
    Go To OrangeHRM Login Page
    Enter Password    ${ORANGEHRM_PASSWORD}
    Click Login
    Verify Required Field Message For Username

Empty Password
    [Documentation]    Require a password when the username is supplied.
    Go To OrangeHRM Login Page
    Enter Username    ${ORANGEHRM_USERNAME}
    Click Login
    Verify Required Field Message For Password

Empty Username And Password
    [Documentation]    Require credentials when both fields are empty.
    Go To OrangeHRM Login Page
    Click Login
    Verify Two Required Field Messages

Username Is Case Insensitive
    [Documentation]    Verify a valid username is accepted with different casing.
    Login With Credentials    Admin    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard

Case Sensitive Password
    [Documentation]    Reject a password with incorrect casing.
    Login With Credentials    ${ORANGEHRM_USERNAME}    Admin123
    Verify Error Message Contains    Invalid credentials

Unauthenticated Protected Page
    [Documentation]    Redirect unauthenticated users away from the dashboard.
    Open Page    ${ORANGEHRM_DASHBOARD_URL}
    Verify Redirected To Login Page

Authenticated Session Persists Across Pages
    [Documentation]    Verify a valid session survives in-app navigation without re-authentication.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Navigate To Admin Page
    Verify Admin Page Displayed

Login Page Branding Is Shown
    [Documentation]    Verify the OrangeHRM login page renders its brand and login panel heading.
    Go To OrangeHRM Login Page
    Verify OrangeHRM Login Branding

Password Field Is Masked
    [Documentation]    Verify the password field masks input by being of type password.
    Go To OrangeHRM Login Page
    Password Field Should Be Masked

Username With Surrounding Whitespace Is Rejected
    [Documentation]    Verify leading and trailing spaces in the username are not trimmed and login is rejected.
    Login With Credentials    ${SPACE}${SPACE}${ORANGEHRM_USERNAME}${SPACE}${SPACE}    ${ORANGEHRM_PASSWORD}
    Verify Error Message Contains    Invalid credentials

Forgot Password Link Opens Reset Page
    [Documentation]    Verify the forgot password link navigates to the password reset page.
    Go To OrangeHRM Login Page
    Click Forgot Password Link
    Verify Forgot Password Page Open
