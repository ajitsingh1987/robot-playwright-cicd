*** Settings ***
Library    Browser
Variables    ../variables/urls.py

*** Variables ***
${LOGIN_USERNAME}       input[name="username"]
${LOGIN_PASSWORD}       input[name="password"]
${LOGIN_BUTTON}         //button[normalize-space()="Login"]
${DASHBOARD_HEADING}    //h6[normalize-space()="Dashboard"]
${LOGIN_ERROR}          //p[normalize-space()="Invalid credentials"]

*** Keywords ***
Go To OrangeHRM Login Page
    Open Page    ${ORANGEHRM_LOGIN_URL}
    Wait Until Login Page Is Ready

Wait Until Login Page Is Ready
    Wait For Elements State    ${LOGIN_USERNAME}    visible    timeout=60s
    Wait For Elements State    ${LOGIN_PASSWORD}    visible    timeout=60s
    Wait For Elements State    ${LOGIN_BUTTON}    visible    timeout=30s

Open Login Page And Wait For Username Field
    Go To OrangeHRM Login Page

Enter Username
    [Arguments]    ${username}
    Wait For Elements State    ${LOGIN_USERNAME}    visible    timeout=30s
    Fill Text    ${LOGIN_USERNAME}    ${username}

Enter Password
    [Arguments]    ${password}
    Wait For Elements State    ${LOGIN_PASSWORD}    visible    timeout=30s
    Fill Secret    ${LOGIN_PASSWORD}    $password

Click Login
    Wait For Elements State    ${LOGIN_BUTTON}    visible    timeout=30s
    Click    ${LOGIN_BUTTON}

Login With Credentials
    [Arguments]    ${username}    ${password}

    # Always establish a deterministic login-page state.
    Go To OrangeHRM Login Page

    # Enter credentials only after the page is ready.
    Enter Username    ${username}
    Enter Password    ${password}

    # Submit only after the login button is available.
    Click Login

Wait Until Dashboard Is Ready
    Wait For Elements State    ${DASHBOARD_HEADING}    visible    timeout=90s

Verify Dashboard Page Contains
    [Arguments]    ${expected_dashboard_text}

    ${dashboard_locator}=    Set Variable
    ...    //h6[normalize-space()="${expected_dashboard_text}"]

    # Wait for the actual application state, not an arbitrary sleep.
    Wait For Elements State    ${dashboard_locator}    visible    timeout=90s

    ${url}=    Get Url
    Should Contain    ${url}    /dashboard

Verify Error Message Contains
    [Arguments]    ${expected_error}
    Wait For Elements State
    ...    //p[normalize-space()="${expected_error}"]
    ...    visible
    ...    timeout=30s

Verify Required Field Message For Username
    Wait For Elements State
    ...    //input[@name="username"]/ancestor::div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Required Field Message For Password
    Wait For Elements State
    ...    //input[@name="password"]/ancestor::div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Two Required Field Messages
    Verify Required Field Message For Username
    Verify Required Field Message For Password

Verify Login Page Displayed
    Wait Until Login Page Is Ready

    ${url}=    Get Url
    Should Contain    ${url}    /auth/login

Verify Redirected To Login Page
    Wait Until Login Page Is Ready

    ${url}=    Get Url
    Should Contain    ${url}    /auth/login

Verify OrangeHRM Login Branding
    Wait For Elements State    img[alt="company-branding"]    visible    timeout=30s

    ${title}=    Get Text    h5.orangehrm-login-title
    Should Be Equal    ${title}    Login

Password Field Should Be Masked
    Wait For Elements State    ${LOGIN_PASSWORD}    visible    timeout=30s

    ${type}=    Get Attribute    ${LOGIN_PASSWORD}    type
    Should Be Equal    ${type}    password

Navigate To Admin Page
    Wait For Elements State    //a[normalize-space()="Admin"]    visible    timeout=60s
    Click    //a[normalize-space()="Admin"]

Verify Admin Page Displayed
    Wait For Elements State
    ...    //h5[normalize-space()="System Users"]
    ...    visible
    ...    timeout=60s

    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewSystemUsers