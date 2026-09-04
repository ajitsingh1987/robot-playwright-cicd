*** Settings ***
Library    Browser

*** Keywords ***
Start Browser
    [Arguments]    ${browser}=chromium    ${headless}=True
    New Browser    ${browser}    headless=${headless}

Start Isolated Context
    New Context
    Set Browser Timeout    30 seconds    scope=Test

Open Page
    [Arguments]    ${url}
    New Page    ${url}    wait_until=domcontentloaded

Stop Browser
    Close Browser

Stop Isolated Context
    Close Context

Close Current Page
    Close Page