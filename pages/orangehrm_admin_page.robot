*** Settings ***
Library    Browser
Variables    ../variables/urls.py
Variables    ../data/orangehrm_admin_data.py

*** Variables ***
# ── Admin URLs ─────────────────────────────────────────────
${ADMIN_SYSTEM_USERS_URL}       ${ORANGEHRM_BASE_URL}/web/index.php/admin/viewSystemUsers
${ADMIN_ADD_USER_URL}           ${ORANGEHRM_BASE_URL}/web/index.php/admin/saveSystemUser
${ADMIN_JOB_TITLES_URL}         ${ORANGEHRM_BASE_URL}/web/index.php/admin/viewJobTitleList
${ADMIN_PAY_GRADES_URL}         ${ORANGEHRM_BASE_URL}/web/index.php/admin/viewPayGrades
${ADMIN_SKILLS_URL}             ${ORANGEHRM_BASE_URL}/web/index.php/admin/viewSkills
${ADMIN_LOCATIONS_URL}          ${ORANGEHRM_BASE_URL}/web/index.php/admin/viewLocations

# ── Headings ───────────────────────────────────────────────
${SYSTEM_USERS_HEADING}         //h5[normalize-space()="System Users"]
${ADD_USER_HEADING}             //h6[normalize-space()="Add User"]
${JOB_TITLES_HEADING}           //h6[normalize-space()="Job Titles"]
${PAY_GRADES_HEADING}           //h6[normalize-space()="Pay Grades"]
${SKILLS_HEADING}               //h6[normalize-space()="Skills"]
${LOCATIONS_HEADING}            //h5[normalize-space()="Locations"]

# ── Common buttons ─────────────────────────────────────────
${SAVE_BUTTON}                  //button[normalize-space()="Save"]
${CANCEL_BUTTON}                //button[normalize-space()="Cancel"]
${SEARCH_BUTTON}                //button[normalize-space()="Search"]
${RESET_BUTTON}                 //button[normalize-space()="Reset"]
${ADD_BUTTON}                   //button[contains(@class,"oxd-button")][normalize-space()=" Add"]

# ── Success toast ──────────────────────────────────────────
${SUCCESS_TOAST_MESSAGE}        //p[normalize-space()="Successfully Saved"]

# ── Delete confirmation dialog ─────────────────────────────
${DELETE_CONFIRM_YES}           //button[normalize-space()="Yes, Delete"]
${DELETE_CONFIRM_NO}            //button[normalize-space()="No, Cancel"]
${DELETE_DIALOG_TEXT}           //div[contains(@class,"oxd-dialog")]//p[contains(normalize-space(),"Are you sure")]

*** Keywords ***
# ═══════════════════════ SYSTEM USERS PAGE ═══════════════════════
Go To System Users Page
    Open Page    ${ADMIN_SYSTEM_USERS_URL}
    Wait Until System Users Page Ready

Wait Until System Users Page Ready
    Wait For Elements State    ${SYSTEM_USERS_HEADING}    visible    timeout=60s

Verify System Users Page Displayed
    Wait Until System Users Page Ready
    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewSystemUsers

# ═══════════════════════ ADD SYSTEM USER FORM ═══════════════════════
Go To Add System User Page
    Open Page    ${ADMIN_ADD_USER_URL}
    Wait Until Add System User Page Ready

Wait Until Add System User Page Ready
    Wait For Elements State    ${ADD_USER_HEADING}    visible    timeout=60s
    Wait For Elements State    ${SAVE_BUTTON}    visible    timeout=30s

Verify Add System User Page Displayed
    Wait Until Add System User Page Ready
    ${url}=    Get Url
    Should Contain    ${url}    /admin/saveSystemUser

Select User Role In Add Form
    [Arguments]    ${role}
    ${trigger}=    Set Variable
    ...    //div[contains(@class,"oxd-input-group")][.//label[contains(normalize-space(),"User Role")]]//div[contains(@class,"oxd-select-text-input")]
    Click    ${trigger}
    Wait For Elements State
    ...    //div[contains(@class,"oxd-select-dropdown")]//div[contains(@class,"oxd-select-option")][normalize-space()="${role}"]
    ...    visible
    ...    timeout=10s
    Click
    ...    //div[contains(@class,"oxd-select-dropdown")]//div[contains(@class,"oxd-select-option")][normalize-space()="${role}"]

Select Status In Add Form
    [Arguments]    ${status}
    ${trigger}=    Set Variable
    ...    //div[contains(@class,"oxd-input-group")][.//label[contains(normalize-space(),"Status")]]//div[contains(@class,"oxd-select-text-input")]
    Click    ${trigger}
    Wait For Elements State
    ...    //div[contains(@class,"oxd-select-dropdown")]//div[contains(@class,"oxd-select-option")][normalize-space()="${status}"]
    ...    visible
    ...    timeout=10s
    Click
    ...    //div[contains(@class,"oxd-select-dropdown")]//div[contains(@class,"oxd-select-option")][normalize-space()="${status}"]

Resolve Existing Employee Name
    # Resolves an employee that actually exists at run time. The Add User
    # form's Employee Name autocomplete requires a real employee, and the
    # shared demo database is modified by other automation runs, so a name
    # hard-coded at authoring time can stop matching. Query the same PIM
    # employees endpoint the autocomplete widget uses and pick a non-empty,
    # non-terminated match. The widget matches a first name substring, so
    # the returned first name is typed into the autocomplete.
    ${expression}=    Set Variable    async () => { const res = await fetch('/web/index.php/api/v2/pim/employees?nameOrId=a&limit=20'); const payload = await res.json(); const rows = payload.data || []; const pick = rows.find(row => row.firstName && row.terminationId === null); return pick ? pick.firstName.trim() : ''; }
    ${employee}=    Evaluate JavaScript    ${EMPTY}    ${expression}
    Should Not Be Empty    ${employee}
    RETURN    ${employee}

Type Employee Name In Add Form
    [Arguments]    ${search_text}
    ${input}=    Set Variable
    ...    //div[contains(@class,"oxd-input-group")][.//label[contains(normalize-space(),"Employee Name")]]//input
    Click    ${input}
    Fill Text    ${input}    ${search_text}
    Wait For Elements State
    ...    (//div[contains(@class,"oxd-autocomplete-dropdown")]//*[contains(@class,"oxd-autocomplete-option")][not(contains(normalize-space(),"Searching"))][not(contains(normalize-space(),"No Records"))])[1]
    ...    visible
    ...    timeout=60s
    Click
    ...    (//div[contains(@class,"oxd-autocomplete-dropdown")]//*[contains(@class,"oxd-autocomplete-option")][not(contains(normalize-space(),"Searching"))][not(contains(normalize-space(),"No Records"))])[1]

Fill Username In Add Form
    [Arguments]    ${username}
    ${input}=    Set Variable
    ...    //div[contains(@class,"oxd-input-group")][.//label[contains(normalize-space(),"Username")]]//input
    Wait For Elements State    ${input}    visible    timeout=30s
    Fill Text    ${input}    ${username}

Fill Password In Add Form
    [Arguments]    ${password}
    ${input}=    Set Variable    input[type="password"] >> nth=0
    Wait For Elements State    ${input}    visible    timeout=30s
    Fill Secret    ${input}    $password

Fill Confirm Password In Add Form
    [Arguments]    ${password}
    ${input}=    Set Variable    input[type="password"] >> nth=1
    Wait For Elements State    ${input}    visible    timeout=30s
    Fill Secret    ${input}    $password

Click Add User Save
    Wait For Elements State    ${SAVE_BUTTON}    visible    timeout=30s
    Click    ${SAVE_BUTTON}

Fill Complete Add User Form
    [Arguments]
    ...    ${role}=Admin
    ...    ${employee_name}=${EMPTY}
    ...    ${status}=Enabled
    ...    ${username}=${ADMIN_TEST_USERNAME}
    ...    ${password}=${ADMIN_TEST_PASSWORD}

    IF    '${employee_name}' == '${EMPTY}'
        ${employee_name}=    Resolve Existing Employee Name
    END

    Select User Role In Add Form    ${role}
    Type Employee Name In Add Form    ${employee_name}
    Select Status In Add Form    ${status}
    Fill Username In Add Form    ${username}
    Fill Password In Add Form    ${password}
    Fill Confirm Password In Add Form    ${password}

# ═══════════════════════ VALIDATION & ASSERTIONS ═══════════════════════
Verify Add User Form Shows Required Errors
    [Arguments]    ${min_count}=4
    Wait For Elements State
    ...    //div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"] >> nth=0
    ...    visible
    ...    timeout=30s
    ${count}=    Get Element Count    //div[contains(@class,"oxd-input-group")]//span[normalize-space()="Required"]
    Should Be True    ${count} >= ${min_count}    Expected at least ${min_count} Required messages, got ${count}

Verify Username Field Shows Required
    Wait For Elements State
    ...    //div[contains(@class,"oxd-input-group")][.//label[contains(normalize-space(),"Username")]]//span[normalize-space()="Required"]
    ...    visible
    ...    timeout=30s

Verify Success Toast Displayed
    Wait For Elements State    ${SUCCESS_TOAST_MESSAGE}    visible    timeout=30s

Verify Redirected To System Users List
    Wait For Elements State    ${SYSTEM_USERS_HEADING}    visible    timeout=60s
    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewSystemUsers

Verify Username Already Exists Error
    Wait For Elements State
    ...    //div[contains(@class,"oxd-input-group")][.//label[contains(normalize-space(),"Username")]]//span[contains(normalize-space(),"Already exists")]
    ...    visible
    ...    timeout=30s

# ═══════════════════════ SEARCH & FILTER ═══════════════════════
Search System Users By Username
    [Arguments]    ${username}
    ${filter_input}=    Set Variable
    ...    //div[contains(@class,"oxd-form")]//div[contains(@class,"oxd-input-group")][.//div[normalize-space()="Username"] or .//label[normalize-space()="Username"]]//input
    Wait For Elements State    ${filter_input}    visible    timeout=30s
    Fill Text    ${filter_input}    ${username}
    Wait For Elements State    ${SEARCH_BUTTON}    visible    timeout=30s
    Click    ${SEARCH_BUTTON}

Verify User Found In Table
    [Arguments]    ${username}
    Wait For Elements State
    ...    //div[contains(@class,"oxd-table-cell")][normalize-space()="${username}"]
    ...    visible
    ...    timeout=60s

# ═══════════════════════ DELETE CONFIRMATION ═══════════════════════
Click Delete Button For User
    [Arguments]    ${username}
    ${delete_btn}=    Set Variable
    ...    //div[contains(@class,"oxd-table-row")][.//div[contains(@class,"oxd-table-cell")][normalize-space()="${username}"]]//div[contains(@class,"oxd-table-cell-actions")]//button[1]
    Wait For Elements State    ${delete_btn}    visible    timeout=30s
    Click    ${delete_btn}

Verify Delete Confirmation Dialog Displayed
    Wait For Elements State    ${DELETE_DIALOG_TEXT}    visible    timeout=10s
    Wait For Elements State    ${DELETE_CONFIRM_YES}    visible    timeout=10s
    Wait For Elements State    ${DELETE_CONFIRM_NO}    visible    timeout=10s

Click Delete Confirm No
    Wait For Elements State    ${DELETE_CONFIRM_NO}    visible    timeout=10s
    Click    ${DELETE_CONFIRM_NO}

# ═══════════════════════ JOB TITLES PAGE ═══════════════════════
Go To Job Titles Page
    Open Page    ${ADMIN_JOB_TITLES_URL}
    Wait Until Job Titles Page Ready

Wait Until Job Titles Page Ready
    Wait For Elements State    ${JOB_TITLES_HEADING}    visible    timeout=60s

Verify Job Titles Page Displayed
    Wait Until Job Titles Page Ready
    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewJobTitleList

Verify Job Titles Has Records
    Wait Until Keyword Succeeds
    ...    30s
    ...    1s
    ...    Record Count Should Be Greater Than
    ...    //div[contains(@class,"oxd-table")]//div[contains(@class,"oxd-table-row")]
    ...    1
    ...    Job Titles table should have at least one record

# ═══════════════════════ PAY GRADES PAGE ═══════════════════════
Go To Pay Grades Page
    Open Page    ${ADMIN_PAY_GRADES_URL}
    Wait Until Pay Grades Page Ready

Wait Until Pay Grades Page Ready
    Wait For Elements State    ${PAY_GRADES_HEADING}    visible    timeout=60s

Verify Pay Grades Page Displayed
    Wait Until Pay Grades Page Ready
    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewPayGrades

Verify Pay Grades Has Records
    Wait Until Keyword Succeeds
    ...    30s
    ...    1s
    ...    Record Count Should Be Greater Than
    ...    //div[contains(@class,"oxd-table")]//div[contains(@class,"oxd-table-row")]
    ...    1
    ...    Pay Grades table should have at least one record

# ═══════════════════════ SKILLS PAGE ═══════════════════════
Go To Skills Page
    Open Page    ${ADMIN_SKILLS_URL}
    Wait Until Skills Page Ready

Wait Until Skills Page Ready
    Wait For Elements State    ${SKILLS_HEADING}    visible    timeout=60s

Verify Skills Page Displayed
    Wait Until Skills Page Ready
    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewSkills

Verify Skills Has Records
    Wait Until Keyword Succeeds
    ...    30s
    ...    1s
    ...    Record Count Should Be Greater Than
    ...    //div[contains(@class,"oxd-table")]//div[contains(@class,"oxd-table-row")]
    ...    1
    ...    Skills table should have at least one record

# ═══════════════════════ LOCATIONS PAGE ═══════════════════════
Go To Locations Page
    Open Page    ${ADMIN_LOCATIONS_URL}
    Wait Until Locations Page Ready

Wait Until Locations Page Ready
    Wait For Elements State    ${LOCATIONS_HEADING}    visible    timeout=60s

Verify Locations Page Displayed
    Wait Until Locations Page Ready
    ${url}=    Get Url
    Should Contain    ${url}    /admin/viewLocations

Verify Locations Has Records
    Wait Until Keyword Succeeds
    ...    30s
    ...    1s
    ...    Record Count Should Be Greater Than
    ...    //div[contains(@class,"oxd-table")]//div[contains(@class,"oxd-table-row")]
    ...    1
    ...    Locations table should have at least one record

Record Count Should Be Greater Than
    [Arguments]    ${locator}    ${threshold}    ${message}
    ${count}=    Get Element Count    ${locator}
    Should Be True    ${count} > ${threshold}    ${message} (found ${count})