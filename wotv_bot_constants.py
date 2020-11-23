"""Constants used by the WOTV Bot"""
import re

class WotvBotConstants:
    """Constants used by the WOTV Bot"""
    HELP = '''`!resonance unit-name/esper-name`
    > Get **your own** resonance for the named unit and esper. Example: *!resonance mont/cactuar*

    `!resonance unit-or-esper-name`
    > Get a full listing of **your own** resonances for the named unit *or* esper. This will generate a listing, in the same order as the spreadsheet, of all the resonance data for the specified unit *or* esper. Example: *!resonance lamia*

    `!resonance-set unit-name/esper-name level[/priority[/comment]]`
    > Set **your own** resonance for the named unit and esper to the specified level. Optionally, include a priority at the end (H/High/M/Medium/L/Low). If a priority has already been set, it will be preserved. If no priority has been set, the default is "Low". Finally, you can add a comment like "for evade build" as the final string, or the string "<blank>" (without the quotes) to clear an existing comment. Example: *!resonance-set mont/cactuar 9/m/because everyone loves cactuars*

    `!resonance-lookup discord-nickname unit-name/esper-name`
    > Get **someone else's** resonance for the named unit and esper. Unlike !resonance and !resonance-set, the discord-nickname here is not resolved against the user's snowflake ID. Put another way, it's just the name of the tab in the spreadsheet. This can access data of a former guild members, if your guild leader hasn't deleted it. Example: *!resonance-lookup JohnDoe mont/cactuar*

    `!vc-set`
    > Send this message with no other text, and attach a screenshot of a vision card. The bot will save your vision card stats. If it doesn't work, see *!vc-debug* below.

    `!vc-debug`
    > Send this message with no other text, and attach a screenshot of a vision card. Instead of saving your vision card stats, the bot will extract debugging images and respond with them as an attachment.

    `!vc vision-card-name`
    > Get **your own** stats for the named vision card. Example: *!vc Odin*

    **Names of Espers, Units, Vision Cards, etceteras**
    You don't have to type out "Sterne Leonis" and "Tetra Sylphid"; you can just shorthand it as "stern/tetra", or even "st/te". Specifically, here's how searching works:
    1. If you enclose the name of the unit, esper, vision card (etc) in double quotes, only an EXACT MATCH will be performed. This is handy to force the correct unit when dealing with some unique situations like "Little Leela" and "Little Leela (Halloween)"
    2. Otherwise, if there's only one possible name that STARTS WITH the shorthand, that's enough. For example, there's only one unit whose name starts with "Lass" (Lasswell), so you can just type "Lass" (without the quotes).
    3. Otherwise, if there's only one possible name that HAS ALL THE WORDS YOU ENTERED, that's enough. For example, there's only one unit whose name contains both "Lee" and "Hallow", it's "Little Leela (Halloween)". So this is enough to identify her.
    4. Otherwise, an error will be returned - either because (1) there was no exact match or, in the case of (2) and (3) above there were multiple possible matches and you need to be more specific.

    You can also abbreviate "resonance" as just "res" in all the resonance commands.

    View your guild's Esper resonance data here: <https://docs.google.com/spreadsheets/d/{0}>
    '''

    # Pattern for getting your own resonance value
    RES_FETCH_SELF_PATTERN = re.compile(r'^!res(?:onance)? (.+)/(.+)$')

    # Pattern for getting your own list of resonance values for a given esper/unit. Note the lack of a '/' separator.
    RES_LIST_SELF_PATTERN = re.compile(r'^!res(?:onance)? (?P<target_name>.+)$')

    # Pattern for setting your own resonance value
    RES_SET_PATTERN = re.compile(
        r'^!res(?:onance)?-set (?P<unit>.+)/(?P<esper>.+)\s+(?P<resonance_level>[0-9]+)\s*(/\s*(?P<priority>[^\/]+)(/\s*(?P<comment>[^\/]+))?)?$')

    # Pattern for getting someone else's resonance value
    RES_FETCH_OTHER_PATTERN = re.compile(
        r'^!res(?:onance)?-lookup (\S+) (.+)/(.+)$')

    # Pattern to save a Vision Card to your account, extracting text from an attached screenshot.
    VISION_CARD_SET_PATTERN = re.compile(r'^!vc-set$')

    # Pattern to debug problems with vision card setting
    VISION_CARD_DEBUG_PATTERN = re.compile(r'^!vc-debug$')

    # Pattern to retieve one of your own vision card's stats.
    VISION_CARD_FETCH_BY_NAME_PATTERN = re.compile(r'^!vc (?P<target_name>.+)$')

    # (Hidden) Pattern for getting your own user ID out of Discord
    WHOIS_PATTERN = re.compile(r'^!whois (?P<server_handle>.+)$')

    ADMIN_HELP = '''
    **NOTE**
    Due to discord formatting of URLs, in the commands below, the "https://" prefix is displayed as "XX:". This is to prevent Discord from mangling the examples and converting the pipe-delimiters of the commands into URL parameters. where you see "XX:" in a command, you should type "https://" as you normally would to start a URL.

    !admin-add-esper name|url|[left-of|right-of]|column-identifier
    Add an esper having the specified name and informational URL either left-of or right-of the specified column (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the esper). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The column should be in 'A1' notation, e.g. 'AA' for the 27th column. Example: !admin-add-esper Death Machine|XX:wotv-calc.com/esper/death-machine|left-of|C

    !admin-add-unit name|url|[above|below]|row-identifier
    Add a unit having the specified name and informational URL either above or below the specified row (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the unit). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The row should be the literal row number from the spreadsheet, i.e. it is 1-based (not 0-based). Example: !admin-add-unit Rain|XX:wotv-calc.com/unit/rain|above|16

    !admin-add-vc name|url|[above|below]|row-identifier
    Add a vision card having the specified name and informational URL either above or below the specified row (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the card). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The row should be the literal row number from the spreadsheet, i.e. it is 1-based (not 0-based). Example: !admin-add-vc Death Machine|XX:wotv-calc.com/card/death-machine|above|16

    !admin-add-user snowflake_id|nickname|admin
    Add a new user to the bot. This will register the user in the administrative spreadsheet and will add a tab for them in the Esper resonance tracker. If the final parameter, 'admin', is the literal string 'admin' (without quotes), then this user shall be an admin. Otherwise (if the parameter has any other value) the user is a normal (non-admin) user. Example: !admin-add-user 123456789|JohnDoe|normal

    **Admin Notes**
    Prefix any admin command with "sandbox-" to perform the operations on the configured sandbox instead of the true resource. Once you're certain you have the command correct, just remove the "sandbox-" prefix to write to the true resource (e.g., the esper resonance spreadsheet for the guild).

    The guild's configured Esper Resonance spreadsheet is at <https://docs.google.com/spreadsheets/d/{0}> and its sandbox is at <https://docs.google.com/spreadsheets/d/{1}>.
    '''

    # (Admin only) Pattern for adding an Esper column.
    # Sandbox mode uses a different sheet, for testing.
    ADMIN_ADD_ESPER_PATTERN = re.compile(
        r'^!admin-add-esper (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<left_or_right_of>.+)\|(?P<column>.+)$')
    SANDBOX_ADMIN_ADD_ESPER_PATTERN = re.compile(
        r'^!sandbox-admin-add-esper (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<left_or_right_of>.+)\|(?P<column>.+)$')

    # (Admin only) Pattern for adding a Unit row.
    # Sandbox mode uses a different sheet, for testing.
    ADMIN_ADD_UNIT_PATTERN = re.compile(
        r'^!admin-add-unit (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<above_or_below>.+)\|(?P<row1Based>.+)$')
    SANDBOX_ADMIN_ADD_UNIT_PATTERN = re.compile(
        r'^!sandbox-admin-add-unit (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<above_or_below>.+)\|(?P<row1Based>.+)$')

    # (Admin only) Pattern for adding a Unit row.
    ADMIN_ADD_VC_PATTERN = re.compile(
        r'^!admin-add-vc (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<above_or_below>.+)\|(?P<row1Based>.+)$')

    # (Admin only) Pattern to add a new user.
    ADMIN_ADD_USER_PATTERN = re.compile(
        r'^!admin-add-user (?P<snowflake_id>[^\|].+)\|(?P<nickname>[^\|]+)\|(?P<user_type>.+)$')

    # List of all ignore patterns, to iterate over.
    ALL_IGNORE_PATTERNS = [
        # Ignore any lines that start with a "!" followed by any non-letter character, since these are definitely not bot commands.
        # This prevents people's various exclamations like "!!!!!" from being acknolwedged by the bot.
        re.compile(r'^![^a-zA-Z]'),
        # Similarly, ignore the raw "!" message. Separate from the pattern above for regex sanity.
        re.compile(r'^!$')]
