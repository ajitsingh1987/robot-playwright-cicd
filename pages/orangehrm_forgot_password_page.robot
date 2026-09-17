*** Settings ***
Library    Browser
Variables    ../variables/urls.py

*** Variables ***
${FORGOT_PASSWORD_LINK}       p.orangehrm-login-forgot-header
${FORGOT_PASSWORD_TITLE}      h6.orangehrm-forgot-password-title
${RESET_USERNAME_INPUT}       input[name="username"]
${RESET_BUTTON}               //button[normalize-space()="Reset Password"]
${CANCEL_BUTTON}              //button[normalize-space()="Cancel"]
${RESET_SUCCESS_HEADING}      //h6[normalize-space()="Reset Password link sent successfully"]
${RESET_SUCCESS_MESSAGE}      //p[normalize-space()="A reset password link has been sent to you via email." and not(p)]

*** Keywords ***
Click Forgot Password Link
    Wait For Elements State
    ...    ${FORGOT_PASSWORD_LINK}
    ...    visible
    ...    timeout=30s

    Click    ${FORGOT_PASSWORD_LINK}

    Wait Until Forgot Password Page Is Ready

Wait Until Forgot Password Page Is Ready
    Wait For Elements State
    ...    ${FORGOT_PASSWORD_TITLE}
    ...    visible
    ...    timeout=60s

    ${url}=    Get Url
    Should Contain    ${url}    requestPasswordResetCode

Verify Forgot Password Page Open
    Wait Until Forgot Password Page Is Ready

Verify Reset Password Page Displayed
    Wait For Elements State
    ...    ${FORGOT_PASSWORD_TITLE}
    ...    visible
    ...    timeout=60s

    ${heading}=    Get Text    ${FORGOT_PASSWORD_TITLE}
    Should Be Equal    ${heading}    Reset Password

    Wait For Elements State
    ...    //p[normalize-space()="Please enter your username to identify your account to reset your password" and not(p)]
    ...    visible
    ...    timeout=30s

    Wait For Elements State
    ...    ${RESET_USERNAME_INPUT}
    ...    visible
    ...    timeout=30s

    Wait For Elements State
    ...    ${RESET_BUTTON}
    ...    visible
    ...    timeout=30s

    Wait For Elements State
    ...    ${CANCEL_BUTTON}
    ...    visible
    ...    timeout=30s

Enter Reset Password Username
    [Arguments]    ${username}

    Wait For Elements State
    ...    ${RESET_USERNAME_INPUT}
    ...    visible
    ...    timeout=30s

    Fill Text    ${RESET_USERNAME_INPUT}    ${username}

Click Reset Password Submit Button
    Wait For Elements State
    ...    ${RESET_BUTTON}
    ...    visible
    ...    timeout=30s

    Click    ${RESET_BUTTON}

Click Reset Password Cancel Button
    Wait For Elements State
    ...    ${CANCEL_BUTTON}
    ...    visible
    ...    timeout=30s

    Click    ${CANCEL_BUTTON}

Verify Required Reset Password Username Message
    Wait For Elements State
    ...    //input[@name="username"]/ancestor::div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Reset Password Link Sent Message
    Wait For Elements State
    ...    ${RESET_SUCCESS_HEADING}
    ...    visible
    ...    timeout=60s

    Wait For Elements State
    ...    ${RESET_SUCCESS_MESSAGE}
    ...    visible
    ...    timeout=30s

    ${url}=    Get Url
    Should Contain    ${url}    sendPasswordReset