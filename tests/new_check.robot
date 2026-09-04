*** Settings ***
Library    Browser
Variables    ../variables/urls.py
Resource    ../resources/browser.resource
Resource    ../pages/rahulshetty_page.robot
Suite Setup    Start Browser
Suite Teardown    Stop Browser

*** Test Cases ***
Verify Rahul Shetty Academy Homepage With Page Object
    Go To Rahul Shetty Academy Homepage
    Verify Rahul Shetty Academy Page Title
    Verify Rahul Shetty Academy URL