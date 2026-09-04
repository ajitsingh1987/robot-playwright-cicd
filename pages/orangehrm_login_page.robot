*** Settings ***
Variables    ../variables/urls.py

*** Keywords ***
Go To OrangeHRM Login Page
    Open Page    ${ORANGEHRM_LOGIN_URL}
    Wait For Elements State    input[placeholder="Username"]    visible

Enter Username
    [Arguments]    ${username}
    Fill Text    input[placeholder="Username"]    ${username}

Enter Password
    [Arguments]    ${password}
    Fill Secret    input[placeholder="Password"]    $password

Click Login
    Click    //button[normalize-space()="Login"]

Login With Credentials
    [Arguments]    ${username}    ${password}
    Go To OrangeHRM Login Page
    Enter Username    ${username}
    Enter Password    ${password}
    Click Login

Verify Dashboard Page Contains
    [Arguments]    ${expected_dashboard_text}
    Wait For Elements State    //h6[normalize-space()="${expected_dashboard_text}"]    visible

Verify Error Message Contains
    [Arguments]    ${expected_error}
    Wait For Elements State    //p[normalize-space()="${expected_error}"]    visible

Verify Required Field Message For Username
    Wait For Elements State    //input[@placeholder="Username"]/ancestor::div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]    visible

Verify Required Field Message For Password
    Wait For Elements State    //input[@placeholder="Password"]/ancestor::div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]    visible

Verify Two Required Field Messages
    Verify Required Field Message For Username
    Verify Required Field Message For Password

Verify Login Page Displayed
    Wait For Elements State    input[placeholder="Username"]    visible
    Wait For Elements State    input[placeholder="Password"]    visible

Logout From OrangeHRM
    # NOTE: oxd-userdropdown-tab is a framework-generated class from OrangeHRM.
    # If the OrangeHRM frontend framework updates its class naming convention,
    # this selector will need to be updated.
    Click    //span[contains(@class,"oxd-userdropdown-tab")]
    Click    //a[normalize-space()="Logout"]
    Verify Login Page Displayed

Verify Redirected To Login Page
    ${url}=    Get Url
    Should Contain    ${url}    /auth/login

Click Forgot Password Link
    Click    p.orangehrm-login-forgot-header

Verify Forgot Password Page Open
    Wait For Elements State    h6.orangehrm-forgot-password-title    visible
    ${url}=    Get Url
    Should Contain    ${url}    requestPasswordResetCode

Verify OrangeHRM Login Branding
    Wait For Elements State    img[alt="company-branding"]    visible
    ${title}=    Get Text    h5.orangehrm-login-title
    Should Be Equal    ${title}    Login

Password Field Should Be Masked
    ${type}=    Get Attribute    input[placeholder="Password"]    type
    Should Be Equal    ${type}    password

Navigate To Admin Page
    Click    //a[normalize-space()="Admin"]

Verify Admin Page Displayed
    Wait For Elements State    //h5[normalize-space()="System Users"]    visible
    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewSystemUsers
