*** Settings ***
Library    Browser
Variables    ../variables/credentials.py
Variables    ../variables/urls.py
Variables    ../data/orangehrm_admin_data.py
Resource    ../resources/browser.resource
Resource    ../pages/orangehrm_login_page.robot
Resource    ../pages/orangehrm_admin_page.robot
Suite Setup    Start Browser
Test Setup    Start Isolated Context
Test Teardown    Stop Isolated Context
Suite Teardown    Stop Browser

*** Test Cases ***
Admin Module System Users Page Loads
    [Documentation]    Verify an authenticated admin user can navigate to Admin > System Users and sees the expected heading.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To System Users Page
    Verify System Users Page Displayed

System User Add Form Validates Required Fields
    [Documentation]    Verify saving an empty Add User form highlights all required fields.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add System User Page
    Click Add User Save
    Verify Add User Form Shows Required Errors    4

System User Can Be Created Successfully
    [Documentation]    Verify a complete system user can be created with all required fields and a success message appears.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add System User Page
    Fill Complete Add User Form
    Click Add User Save
    Verify Success Toast Displayed
    Verify Redirected To System Users List

System User Creation Rejects Duplicate Username
    [Documentation]    Verify a username already used by another user is rejected with an Already exists error.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add System User Page
    Fill Complete Add User Form    username=${ADMIN_DUPLICATE_USERNAME}
    Click Add User Save
    Verify Success Toast Displayed
    Go To Add System User Page
    Fill Complete Add User Form    username=${ADMIN_DUPLICATE_USERNAME}
    Click Add User Save
    Verify Username Already Exists Error

System Users Search Finds Created User
    [Documentation]    Verify the Username search filter returns a created test user.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add System User Page
    Fill Complete Add User Form    username=${ADMIN_SEARCH_USERNAME}
    Click Add User Save
    Verify Success Toast Displayed
    Verify Redirected To System Users List
    Search System Users By Username    ${ADMIN_SEARCH_USERNAME}
    Verify User Found In Table    ${ADMIN_SEARCH_USERNAME}

Delete Confirmation Dialog Appears
    [Documentation]    Verify clicking delete on a user opens the confirmation dialog and cancel closes it.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Add System User Page
    Fill Complete Add User Form    username=${ADMIN_DELETE_USERNAME}
    Click Add User Save
    Verify Success Toast Displayed
    Verify Redirected To System Users List
    Search System Users By Username    ${ADMIN_DELETE_USERNAME}
    Click Delete Button For User    ${ADMIN_DELETE_USERNAME}
    Verify Delete Confirmation Dialog Displayed
    Click Delete Confirm No

Job Titles Page Loads With Records
    [Documentation]    Verify the Job Titles page loads and displays a table with records.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Job Titles Page
    Verify Job Titles Page Displayed
    Verify Job Titles Has Records

Pay Grades Page Loads With Records
    [Documentation]    Verify the Pay Grades page loads and displays a table with records.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Pay Grades Page
    Verify Pay Grades Page Displayed
    Verify Pay Grades Has Records

Skills Page Loads With Records
    [Documentation]    Verify the Skills page loads and displays a table with records.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Skills Page
    Verify Skills Page Displayed
    Verify Skills Has Records

Locations Page Loads With Records
    [Documentation]    Verify the Locations page loads and displays a table with records.
    Login With Credentials    ${ORANGEHRM_USERNAME}    ${ORANGEHRM_PASSWORD}
    Verify Dashboard Page Contains    Dashboard
    Go To Locations Page
    Verify Locations Page Displayed
    Verify Locations Has Records