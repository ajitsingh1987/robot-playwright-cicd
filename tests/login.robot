*** Settings ***
Library    Browser
Variables    ../variables/urls.py
Resource    ../resources/browser.resource
Resource    ../pages/google_page.robot
Suite Setup    Start Browser
Suite Teardown    Stop Browser

*** Test Cases ***
Verify Google Page
    Go To Google Page
    Verify Google Page Title