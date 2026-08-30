*** Settings ***
Library    Browser

*** Test Cases ***
Verify Rahul Shetty Academy Homepage
    New Browser    chromium    headless=True
    New Page    https://rahulshettyacademy.com/    wait_until=domcontentloaded

    ${url}=    Get Url
    Log    Current URL: ${url}

    Should Contain    ${url}    rahulshettyacademy.com

    ${title}=    Get Title
    Log    Page Title: ${title}

    Close Browser