*** Settings ***
Library    Browser
Variables    ../variables/credentials.py
Variables    ../variables/urls.py
Variables    ../data/orangehrm_employee_data.py
Resource    ../resources/browser.resource
Resource    ../pages/orangehrm_login_page.robot
Resource    ../pages/orangehrm_employee_creation_page.robot
Suite Setup    Start Browser
Test Setup    Start Isolated Context
Test Teardown    Stop Isolated Context
Suite Teardown    Stop Browser

*** Test Cases ***
Add Employee Page Is Displayed Correctly
    [Documentation]    Verify an authenticated admin user can open the Add Employee form and sees the expected fields.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Verify Add Employee Page Displayed

Employee Can Be Created Without Login Details
    [Documentation]    Verify an employee can be created with only full name fields and appears afterwards.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Enter Employee First Name    ${EMPLOYEE_FIRST_NAME_NO_LOGIN}
    Enter Employee Last Name    ${EMPLOYEE_LAST_NAME_NO_LOGIN}
    Click Add Employee Save
    Verify Employee Saved Successfully
    Verify Employee Present In Employee List    ${EMPLOYEE_FIRST_NAME_NO_LOGIN}    ${EMPLOYEE_LAST_NAME_NO_LOGIN}

Employee Can Be Created With Login Details
    [Documentation]    Verify an employee can be created together with an enabled login account and appears afterwards.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Enter Employee First Name    ${EMPLOYEE_FIRST_NAME_WITH_CREDENTIALS}
    Enter Employee Last Name    ${EMPLOYEE_LAST_NAME_WITH_CREDENTIALS}
    Enter Employee Id    ${VALID_EMPLOYEE_ID}
    Enter Employee Username    ${EMPLOYEE_USERNAME}
    Enter Employee Password    ${EMPLOYEE_PASSWORD}
    Enter Confirm Employee Password    ${EMPLOYEE_PASSWORD}
    Click Add Employee Save
    Verify Employee Saved Successfully
    Verify Employee Present In Employee List    ${EMPLOYEE_FIRST_NAME_WITH_CREDENTIALS}    ${EMPLOYEE_LAST_NAME_WITH_CREDENTIALS}

Employee Creation Requires First And Last Name
    [Documentation]    Verify saving an empty employee form highlights First Name and Last Name as required.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Click Add Employee Save
    Verify Required First Name Message
    Verify Required Last Name Message

Employee Creation Rejects Mismatched Passwords
    [Documentation]    Verify password and confirm password must match when creating login details.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Enter Employee First Name    ${EMPLOYEE_FIRST_NAME_NO_LOGIN}
    Enter Employee Last Name    ${EMPLOYEE_LAST_NAME_NO_LOGIN}
    Enter Employee Username    ${MISMATCH_USERNAME}
    Enter Employee Password    ${EMPLOYEE_PASSWORD}
    Enter Confirm Employee Password    ${EMPLOYEE_PASSWORD_DIFFERENT}
    Click Add Employee Save
    Verify Passwords Do Not Match Message

Employee Creation Requires Login Details When Enabled
    [Documentation]    Verify enabling login details makes the username required when the form is saved empty.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Enter Employee First Name    ${EMPLOYEE_FIRST_NAME_NO_LOGIN}
    Enter Employee Last Name    ${EMPLOYEE_LAST_NAME_NO_LOGIN}
    Enter Employee Username    ${EMPTY}
    Enter Employee Password    ${EMPTY}
    Click Add Employee Save
    Verify Required Username Message
    Verify Employee Not Saved

Employee Creation Rejects Existing Username
    [Documentation]    Verify a username already used by another employee cannot be reused.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Enter Employee First Name    ${EMPLOYEE_FIRST_NAME_DUPLICATE}
    Enter Employee Last Name    ${EMPLOYEE_LAST_NAME_DUPLICATE}
    Enter Employee Username    ${DUPLICATE_USERNAME}
    Enter Employee Password    ${EMPLOYEE_PASSWORD}
    Enter Confirm Employee Password    ${EMPLOYEE_PASSWORD}
    Click Add Employee Save
    Verify Employee Saved Successfully
    Go To Add Employee Page
    Enter Employee First Name    ${EMPLOYEE_FIRST_NAME_NO_LOGIN}
    Enter Employee Last Name    ${EMPLOYEE_LAST_NAME_NO_LOGIN}
    Enter Employee Username    ${DUPLICATE_USERNAME}
    Enter Employee Password    ${EMPLOYEE_PASSWORD}
    Enter Confirm Employee Password    ${EMPLOYEE_PASSWORD}
    Click Add Employee Save
    Verify Username Already Exists Message

Employee Creation Rejects Weak Password
    [Documentation]    Verify a weak password is rejected with the number requirement hint.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add Employee Page
    Enter Employee First Name    ${EMPLOYEE_FIRST_NAME_NO_LOGIN}
    Enter Employee Last Name    ${EMPLOYEE_LAST_NAME_NO_LOGIN}
    Enter Employee Username    ${WEAK_PASSWORD_USERNAME}
    Enter Employee Password    ${EMPLOYEE_PASSWORD_WEAK}
    Enter Confirm Employee Password    ${EMPLOYEE_PASSWORD_WEAK}
    Click Add Employee Save
    Verify Weak Password Message    ${EMPLOYEE_PASSWORD_WEAK_HINT}
