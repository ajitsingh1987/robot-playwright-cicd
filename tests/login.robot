*** Settings ***
Library    Browser

*** Test Cases ***
Verify Google Page
    New Browser    chromium    headless=False
    New Page    https://www.google.com
    ${title}=    Get Title
    Log    Page Title: ${title}
    Should Contain    ${title}    Google
    Close Browser