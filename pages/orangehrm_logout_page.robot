*** Settings ***
Library    Browser
Variables    ../variables/urls.py

*** Variables ***
${USER_DROPDOWN_TAB}       //span[contains(@class,"oxd-userdropdown-tab")]
${USER_DROPDOWN_MENU}      //ul[contains(@class,"oxd-dropdown-menu")]
${LOGOUT_MENU_ITEM}        //ul[contains(@class,"oxd-dropdown-menu")]//a[normalize-space()="Logout"]
${LOGIN_USERNAME_INPUT}    input[name="username"]
${LOGIN_PASSWORD_INPUT}    input[name="password"]

*** Keywords ***
Verify User Dropdown Tab Visible
    Wait For Elements State
    ...    ${USER_DROPDOWN_TAB}
    ...    visible
    ...    timeout=60s

Verify User Dropdown Tab Hidden
    Wait For Elements State
    ...    ${USER_DROPDOWN_TAB}
    ...    hidden
    ...    timeout=30s

Verify User Dropdown Menu Hidden
    Wait For Elements State
    ...    ${USER_DROPDOWN_MENU}
    ...    hidden
    ...    timeout=30s

Click User Dropdown
    Wait For Elements State
    ...    ${USER_DROPDOWN_TAB}
    ...    visible
    ...    timeout=60s

    Click    ${USER_DROPDOWN_TAB}

    Wait For Elements State
    ...    ${USER_DROPDOWN_MENU}
    ...    visible
    ...    timeout=30s

Verify Logout Menu Item Visible
    Wait For Elements State
    ...    ${LOGOUT_MENU_ITEM}
    ...    visible
    ...    timeout=30s

Click Logout Menu Item
    Wait For Elements State
    ...    ${LOGOUT_MENU_ITEM}
    ...    visible
    ...    timeout=30s

    Click    ${LOGOUT_MENU_ITEM}

Wait Until Logout Is Complete
    # Logout must end in the unauthenticated login state.
    Wait For Elements State
    ...    ${LOGIN_USERNAME_INPUT}
    ...    visible
    ...    timeout=60s

    Wait For Elements State
    ...    ${LOGIN_PASSWORD_INPUT}
    ...    visible
    ...    timeout=60s

    ${url}=    Get Url
    Should Contain    ${url}    /auth/login

Verify Login Page After Logout
    Wait Until Logout Is Complete

Verify User Is Logged Out
    # Authenticated UI must no longer be available.
    Wait For Elements State
    ...    ${USER_DROPDOWN_TAB}
    ...    hidden
    ...    timeout=30s

    Wait Until Logout Is Complete

Logout From OrangeHRM
    # Ensure authenticated navigation is ready.
    Verify User Dropdown Tab Visible

    Click User Dropdown

    Verify Logout Menu Item Visible

    Click Logout Menu Item

    # Do not return control until logout is actually complete.
    Wait Until Logout Is Complete