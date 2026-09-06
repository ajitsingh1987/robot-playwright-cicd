*** Settings ***
Library    Browser
Variables    ../variables/credentials.py
Variables    ../variables/urls.py
Variables    ../data/orangehrm_login_data.py
Resource    ../resources/browser.resource
Resource    ../pages/orangehrm_login_page.robot
Resource    ../pages/orangehrm_forgot_password_page.robot
Suite Setup    Start Browser
Test Setup    Start Isolated Context
Test Teardown    Stop Isolated Context
Suite Teardown    Stop Browser

*** Test Cases ***
Forgot Password Link Opens Reset Page
    [Documentation]    Verify the forgot password link navigates to the password reset page.
    Go To OrangeHRM Login Page
    Click Forgot Password Link
    Verify Forgot Password Page Open

# Forgot Password end-to-end coverage.
# NOTE: Submitting the reset request with a real demo account username (e.g. Admin)
# is excluded from assertions: the public demo server consistently returns
# HTTP 504 Gateway Time-out on that path (/auth/requestResetPassword). The
# deterministic flows covered here are navigation, rendering, validation,
# Cancel, and the generic reset-link-sent confirmation returned for unknown usernames.

Reset Password Page Is Displayed Correctly
    [Documentation]    Verify the reset password page renders its heading, instruction, username field and action buttons.
    Go To OrangeHRM Login Page
    Click Forgot Password Link
    Verify Reset Password Page Displayed

Reset Password Requires Username
    [Documentation]    Verify submitting an empty username shows the Required validation message.
    Go To OrangeHRM Login Page
    Click Forgot Password Link
    Click Reset Password Submit Button
    Verify Required Reset Password Username Message

Reset Password Sends Link For Unknown Username
    [Documentation]    Verify an unknown username produces the generic reset-link-sent confirmation page.
    Go To OrangeHRM Login Page
    Click Forgot Password Link
    Enter Reset Password Username    ${FORGOT_PASSWORD_UNKNOWN_USERNAME}
    Click Reset Password Submit Button
    Verify Reset Password Link Sent Message

Reset Password Cancel Returns To Login
    [Documentation]    Verify Cancel from the reset password page returns to the login page.
    Go To OrangeHRM Login Page
    Click Forgot Password Link
    Click Reset Password Cancel Button
    Verify Login Page Displayed