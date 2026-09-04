*** Keywords ***
Go To Google Page
    Open Page    ${GOOGLE_URL}

Get Page Title
    ${title}=    Get Title
    RETURN    ${title}

Verify Page Title Contains
    [Arguments]    ${expected_title}
    ${title}=    Get Title
    Should Contain    ${title}    ${expected_title}

Verify Google Page Title
    Verify Page Title Contains    Google

Close Current Page
    Close Page