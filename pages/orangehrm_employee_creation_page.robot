*** Settings ***
Library    Browser
Variables    ../variables/urls.py
Variables    ../data/orangehrm_employee_data.py

*** Variables ***
${EMPLOYEE_FORM_SCOPE}          //div[contains(@class,"orangehrm-employee-form")]

${FIRST_NAME_INPUT}             input[name="firstName"]
${MIDDLE_NAME_INPUT}            input[name="middleName"]
${LAST_NAME_INPUT}              input[name="lastName"]

${EMP_ID_INPUT}                 ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Employee Id"]]//input
${USERNAME_INPUT}               ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Username"]]//input
${PASSWORD_INPUT}               ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Password"]]//input
${CONFIRM_PASSWORD_INPUT}       ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Confirm Password"]]//input

${CREATE_LOGIN_TOGGLE}          css=.orangehrm-employee-form .oxd-switch-wrapper label .oxd-switch-input
${CREATE_LOGIN_CHECKBOX}        css=.orangehrm-employee-form .oxd-switch-wrapper label input[type="checkbox"]
${SAVE_BUTTON}                  //button[normalize-space()="Save"]

${ADD_EMPLOYEE_HEADING}         //h6[normalize-space()="Add Employee"]
${PERSONAL_DETAILS_HEADING}     //h6[normalize-space()="Personal Details"]

${EMPLOYEE_INFORMATION_HEADING}    //h5[normalize-space()="Employee Information"]
${SEARCH_BUTTON}                //button[normalize-space()="Search"]

*** Keywords ***
Go To Add Employee Page
    Open Page    ${ORANGEHRM_BASE_URL}/web/index.php/pim/addEmployee
    Wait Until Add Employee Page Is Ready

Wait Until Add Employee Page Is Ready
    Wait For Elements State
    ...    ${ADD_EMPLOYEE_HEADING}
    ...    visible
    ...    timeout=60s

    Wait For Elements State
    ...    ${FIRST_NAME_INPUT}
    ...    visible
    ...    timeout=60s

    Wait For Elements State
    ...    ${LAST_NAME_INPUT}
    ...    visible
    ...    timeout=60s

    Wait For Elements State
    ...    ${SAVE_BUTTON}
    ...    visible
    ...    timeout=30s

Verify Add Employee Page Displayed
    Wait Until Add Employee Page Is Ready

Enter Employee First Name
    [Arguments]    ${first_name}

    Wait For Elements State
    ...    ${FIRST_NAME_INPUT}
    ...    visible
    ...    timeout=30s

    Fill Text    ${FIRST_NAME_INPUT}    ${first_name}

Enter Employee Middle Name
    [Arguments]    ${middle_name}

    Wait For Elements State
    ...    ${MIDDLE_NAME_INPUT}
    ...    visible
    ...    timeout=30s

    Fill Text    ${MIDDLE_NAME_INPUT}    ${middle_name}

Enter Employee Last Name
    [Arguments]    ${last_name}

    Wait For Elements State
    ...    ${LAST_NAME_INPUT}
    ...    visible
    ...    timeout=30s

    Fill Text    ${LAST_NAME_INPUT}    ${last_name}

Enter Employee Id
    [Arguments]    ${employee_id}

    Wait For Elements State
    ...    ${EMP_ID_INPUT}
    ...    visible
    ...    timeout=30s

    Fill Text    ${EMP_ID_INPUT}    ${employee_id}

Ensure Create Login Details Enabled
    Wait For Elements State
    ...    ${CREATE_LOGIN_TOGGLE}
    ...    visible
    ...    timeout=30s

    # The rendered switch is a decorative SPAN; the authoritative state lives
    # on the real checkbox input inside the switch wrapper. Reading the span's
    # checked property returns undefined, so the toggle must be read via the
    # checkbox input. Get Checkbox State returns a boolean, not a string.
    ${toggle_state}=    Get Checkbox State    ${CREATE_LOGIN_CHECKBOX}

    IF    not ${toggle_state}
        Click    ${CREATE_LOGIN_TOGGLE}

        Wait For Elements State
        ...    ${USERNAME_INPUT}
        ...    visible
        ...    timeout=30s

        Wait For Elements State
        ...    ${PASSWORD_INPUT}
        ...    visible
        ...    timeout=30s

        Wait For Elements State
        ...    ${CONFIRM_PASSWORD_INPUT}
        ...    visible
        ...    timeout=30s
    END

Enter Employee Username
    [Arguments]    ${username}

    Ensure Create Login Details Enabled

    Fill Text
    ...    ${USERNAME_INPUT}
    ...    ${username}

Enter Employee Password
    [Arguments]    ${password}

    Ensure Create Login Details Enabled

    Fill Secret
    ...    ${PASSWORD_INPUT}
    ...    $password

Enter Confirm Employee Password
    [Arguments]    ${password}

    Ensure Create Login Details Enabled

    Fill Secret
    ...    ${CONFIRM_PASSWORD_INPUT}
    ...    $password

Click Add Employee Save
    Wait For Elements State
    ...    ${SAVE_BUTTON}
    ...    visible
    ...    timeout=30s

    Click    ${SAVE_BUTTON}

Verify Employee Saved Successfully
    Wait For Elements State
    ...    ${PERSONAL_DETAILS_HEADING}
    ...    visible
    ...    timeout=90s

    ${url}=    Get Url
    Should Contain
    ...    ${url}
    ...    /web/index.php/pim/viewPersonalDetails/empNumber/

Verify Required First Name Message
    Wait For Elements State
    ...    //input[@name="firstName"]/../following-sibling::span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Required Last Name Message
    Wait For Elements State
    ...    //input[@name="lastName"]/../following-sibling::span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Required Username Message
    Wait For Elements State
    ...    ${USERNAME_INPUT}/ancestor::*[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Required Password Message
    Wait For Elements State
    ...    ${PASSWORD_INPUT}/ancestor::*[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Passwords Do Not Match Message
    Wait For Elements State
    ...    ${CONFIRM_PASSWORD_INPUT}/ancestor::*[contains(@class,"oxd-input-group")]//span[normalize-space()="Passwords do not match"]
    ...    visible
    ...    timeout=30s

Verify Username Already Exists Message
    Wait For Elements State
    ...    ${USERNAME_INPUT}/ancestor::*[contains(@class,"oxd-input-group")]//span[normalize-space()="Username already exists"]
    ...    visible
    ...    timeout=30s

Verify Weak Password Message
    [Arguments]    ${expected_hint}

    Wait For Elements State
    ...    ${PASSWORD_INPUT}/ancestor::*[contains(@class,"oxd-input-group")]//span[normalize-space()="${expected_hint}"]
    ...    visible
    ...    timeout=30s

Verify Employee Not Saved
    ${url}=    Get Url

    Should Contain
    ...    ${url}
    ...    /web/index.php/pim/addEmployee

    Wait For Elements State
    ...    ${PERSONAL_DETAILS_HEADING}
    ...    hidden
    ...    timeout=30s

Verify Employee Present In Employee List
    [Arguments]    ${first_name}    ${last_name}

    Open Page
    ...    ${ORANGEHRM_BASE_URL}/web/index.php/pim/viewEmployeeList

    Wait For Elements State
    ...    ${EMPLOYEE_INFORMATION_HEADING}
    ...    visible
    ...    timeout=60s

    ${employee_search}=    Set Variable    input[placeholder="Type for hints..."] >> nth=0

    Wait For Elements State
    ...    ${employee_search}
    ...    visible
    ...    timeout=30s

    Fill Text
    ...    ${employee_search}
    ...    ${first_name} ${last_name}

    Wait For Elements State
    ...    //div[contains(@class,"oxd-autocomplete-dropdown")]//*[@role="option"][normalize-space()="${first_name} ${last_name}"]
    ...    visible
    ...    timeout=60s

    Click
    ...    //div[contains(@class,"oxd-autocomplete-dropdown")]//*[@role="option"][normalize-space()="${first_name} ${last_name}"]

    Wait For Elements State
    ...    ${SEARCH_BUTTON}
    ...    visible
    ...    timeout=30s

    Click    ${SEARCH_BUTTON}

    Wait For Elements State
    ...    //div[contains(@class,"oxd-table")]//*[contains(@class,"oxd-table-cell")][normalize-space()="${first_name}"]
    ...    visible
    ...    timeout=60s

    Wait For Elements State
    ...    //div[contains(@class,"oxd-table")]//*[contains(@class,"oxd-table-cell")][normalize-space()="${last_name}"]
    ...    visible
    ...    timeout=60s