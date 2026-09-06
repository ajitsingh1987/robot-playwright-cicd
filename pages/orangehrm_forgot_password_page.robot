*** Settings ***
Variables    ../variables/urls.py

*** Keywords ***
Click Forgot Password Link
    Click    p.orangehrm-login-forgot-header

Verify Forgot Password Page Open
    Wait For Elements State    h6.orangehrm-forgot-password-title    visible
    ${url}=    Get Url
    Should Contain    ${url}    requestPasswordResetCode

Verify Reset Password Page Displayed
    Wait For Elements State    h6.orangehrm-forgot-password-title    visible
    ${heading}=    Get Text    h6.orangehrm-forgot-password-title
    Should Be Equal    ${heading}    Reset Password
    Wait For Elements State    //p[normalize-space()="Please enter your username to identify your account to reset your password" and not(p)]    visible
    Wait For Elements State    input[placeholder="Username"]    visible
    Wait For Elements State    //button[normalize-space()="Reset Password"]    visible
    Wait For Elements State    //button[normalize-space()="Cancel"]    visible

Enter Reset Password Username
    [Arguments]    ${username}
    Fill Text    input[placeholder="Username"]    ${username}

Click Reset Password Submit Button
    Click    //button[normalize-space()="Reset Password"]

Click Reset Password Cancel Button
    Click    //button[normalize-space()="Cancel"]

Verify Required Reset Password Username Message
    Wait For Elements State    //input[@placeholder="Username"]/ancestor::div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]    visible

Verify Reset Password Link Sent Message
    Wait For Elements State    //h6[normalize-space()="Reset Password link sent successfully"]    visible
    Wait For Elements State    //p[normalize-space()="A reset password link has been sent to you via email." and not(p)]    visible
    ${url}=    Get Url
    Should Contain    ${url}    sendPasswordReset