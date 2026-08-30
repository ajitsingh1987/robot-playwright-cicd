*** Settings ***
Library    Browser

*** Test Cases ***
Verify Rahul Shetty Academy Homepage
    New Browser    chromium    headless=True
    New Page    https://rahulshettyacademy.com/

    ${title}=    Get Title
    Log    Page Title: ${title}

    Should Contain    ${title}    Rahul Shetty Academy

    ${url}=    Get Url
    Log    Current URL: ${url}

    Should Contain    ${url}    rahulshettyacademy.com

    Close Browser