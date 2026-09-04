*** Keywords ***
Go To Rahul Shetty Academy Homepage
    Open Page    ${RAHUL_SHETTY_URL}

Get Page Title
    ${title}=    Get Title
    RETURN    ${title}

Verify Page Title Contains
    [Arguments]    ${expected_title}
    ${title}=    Get Title
    Should Contain    ${title}    ${expected_title}

Verify Rahul Shetty Academy Page Title
    Verify Page Title Contains    Rahul Shetty Academy

Verify Current URL Contains
    [Arguments]    ${expected_fragment}
    ${url}=    Get Url
    Should Contain    ${url}    ${expected_fragment}

Verify Rahul Shetty Academy URL
    Verify Current URL Contains    rahulshettyacademy.com

Close Current Page
    Close Page