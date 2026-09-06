*** Settings ***
Variables    ../variables/urls.py
Variables    ../data/orangehrm_employee_data.py

*** Variables ***
${EMPLOYEE_FORM_SCOPE}    //div[contains(@class,"orangehrm-employee-form")]
${EMP_ID_INPUT}    ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Employee Id"]]//input
${USERNAME_INPUT}    ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Username"]]//input
${PASSWORD_INPUT}    ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Password"]]//input
${CONFIRM_PASSWORD_INPUT}    ${EMPLOYEE_FORM_SCOPE}//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Confirm Password"]]//input
${CREATE_LOGIN_TOGGLE}    css=.orangehrm-employee-form .oxd-switch-input

*** Keywords ***
Go To Add Employee Page
    Open Page    ${ORANGEHRM_BASE_URL}/web/index.php/pim/addEmployee

Verify Add Employee Page Displayed
    Wait For Elements State    //h6[normalize-space()="Add Employee"]    visible
    Wait For Elements State    input[name="firstName"]    visible
    Wait For Elements State    input[name="lastName"]    visible
    Wait For Elements State    //button[normalize-space()="Save"]    visible

Enter Employee First Name
    [Arguments]    ${first_name}
    Fill Text    input[name="firstName"]    ${first_name}

Enter Employee Middle Name
    [Arguments]    ${middle_name}
    Fill Text    input[name="middleName"]    ${middle_name}

Enter Employee Last Name
    [Arguments]    ${last_name}
    Fill Text    input[name="lastName"]    ${last_name}

Enter Employee Id
    [Arguments]    ${employee_id}
    Fill Text    ${EMP_ID_INPUT}    ${employee_id}

Enable Create Login Details
    ${checked}=    Get Property    .orangehrm-employee-form input[type="checkbox"]    checked
    IF    not ${checked}
        Click    ${CREATE_LOGIN_TOGGLE}
    END

Enter Employee Username
    [Arguments]    ${username}
    Enable Create Login Details
    Fill Text    ${USERNAME_INPUT}    ${username}

Enter Employee Password
    [Arguments]    ${password}
    Enable Create Login Details
    Fill Secret    ${PASSWORD_INPUT}    $password

Enter Confirm Employee Password
    [Arguments]    ${password}
    Enable Create Login Details
    Fill Secret    ${CONFIRM_PASSWORD_INPUT}    $password

Click Add Employee Save
    Click    //button[normalize-space()="Save"]

Verify Employee Saved Successfully
    Wait For Elements State    //h6[normalize-space()="Personal Details"]    visible
    ${url}=    Get Url
    Should Contain    ${url}    /web/index.php/pim/viewPersonalDetails/empNumber/

Verify Required First Name Message
    Wait For Elements State    //input[@name="firstName"]/../following-sibling::span[normalize-space()="Required"]    visible

Verify Required Last Name Message
    Wait For Elements State    //input[@name="lastName"]/../following-sibling::span[normalize-space()="Required"]    visible

Verify Required Username Message
    Wait For Elements State    //div[contains(@class,"orangehrm-employee-form")]//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Username"]]//span[normalize-space()="Required"]    visible

Verify Required Password Message
    Wait For Elements State    //div[contains(@class,"orangehrm-employee-form")]//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Password"]]//span[normalize-space()="Required"]    visible

Verify Passwords Do Not Match Message
    Wait For Elements State    //div[contains(@class,"orangehrm-employee-form")]//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Confirm Password"]]//span[normalize-space()="Passwords do not match"]    visible

Verify Username Already Exists Message
    Wait For Elements State    //div[contains(@class,"orangehrm-employee-form")]//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Username"]]//span[normalize-space()="Username already exists"]    visible

Verify Weak Password Message
    [Arguments]    ${expected_hint}
    Wait For Elements State    //div[contains(@class,"orangehrm-employee-form")]//*[contains(@class,"oxd-input-group")][.//label[normalize-space()="Password"]]//span[normalize-space()="${expected_hint}"]    visible

Verify Employee Present In Employee List
    [Arguments]    ${first_name}    ${last_name}
    Open Page    ${ORANGEHRM_BASE_URL}/web/index.php/pim/viewEmployeeList
    Fill Text    input[placeholder="Type for hints..."] >> nth=0    ${first_name} ${last_name}
    Wait For Elements State    //div[contains(@class,"oxd-autocomplete-dropdown")]//*[@role="option"][normalize-space()="${first_name} ${last_name}"]    visible
    Click    //div[contains(@class,"oxd-autocomplete-dropdown")]//*[@role="option"][normalize-space()="${first_name} ${last_name}"]
    Click    //button[normalize-space()="Search"]
    Wait For Elements State    //div[contains(@class,"oxd-table")]//*[contains(@class,"oxd-table-cell")][normalize-space()="${first_name}"]    visible
    Wait For Elements State    //div[contains(@class,"oxd-table")]//*[contains(@class,"oxd-table-cell")][normalize-space()="${last_name}"]    visible
