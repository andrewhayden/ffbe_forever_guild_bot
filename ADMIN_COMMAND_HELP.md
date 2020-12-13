# Commands
`!admin-add-esper name|url|[left-of|right-of]|column-identifier`
><br>**Add an esper having the specified name and informational URL** either left-of or right-of the specified column (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the esper). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The column should be in 'A1' notation, e.g. 'AA' for the 27th column.
<br> Example: *!admin-add-esper Death Machine|XX:wotv-calc.com/esper/death-machine|left-of|C*

<hr>

`!admin-add-unit name|url|[above|below]|row-identifier`
>**Add a unit having the specified name and informational URL** either above or below the specified row (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the unit). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The row should be the literal row number from the spreadsheet, i.e. it is 1-based (not 0-based).
<br>Example: *!admin-add-unit Rain|XX:wotv-calc.com/unit/rain|above|16*

<hr>

`!admin-add-vc name|url|[above|below]|row-identifier`
> **Add a vision card having the specified name and informational URL** either above or below the specified row (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the card). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The row should be the literal row number from the spreadsheet, i.e. it is 1-based (not 0-based).
<br>Example: *!admin-add-vc Death Machine|XX:wotv-calc.com/card/death-machine|above|16*

<hr>

`!admin-add-user snowflake_id|nickname|admin`
> <br>**Add a new user.** This will register the user in the administrative spreadsheet and will add a tab for them in the Esper resonance tracker. If the final parameter, 'admin', is the literal string 'admin' (without quotes), then this user shall be an admin. Otherwise (if the parameter has any other value) the user is a normal (non-admin) user.
<br>Example: *!admin-add-user 123456789|JohnDoe|normal*

<hr>

# Additional Notes
`!admin-add-esper` and `!admin-add-unit` commands can be prefixed with "sandbox-" to perform the operations on the configured sandbox instead of the true resource. Once you're certain you have the command correct, just remove the "sandbox-" prefix to write to the true resource (e.g., the esper resonance spreadsheet for the guild). This functionality will likely be removed in the future in favor of editing commands to alter an existing entry, remove it, etceteras.
