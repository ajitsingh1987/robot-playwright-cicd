*** Settings ***
Variables    ../variables/urls.py

*** Keywords ***
Verify User Dropdown Tab Visible
    Wait For Elements State    //span[contains(@class,"oxd-userdropdown-tab")]    visible

Verify User Dropdown Tab Hidden
    Wait For Elements State    //span[contains(@class,"oxd-userdropdown-tab")]    hidden

Verify User Dropdown Menu Hidden
    Wait For Elements State    ul.oxd-dropdown-menu    hidden

Click User Dropdown
    Click    //span[contains(@class,"oxd-userdropdown-tab")]

Verify Logout Menu Item Visible
    Wait For Elements State    //ul[contains(@class,"oxd-dropdown-menu")]//a[normalize-space()="Logout"]    visible

Click Logout Menu Item
    Click    //ul[contains(@class,"oxd-dropdown-menu")]//a[normalize-space()="Logout"]

Logout From OrangeHRM
    Click User Dropdown
    Verify Logout Menu Item Visible
    Click Logout Menu Item