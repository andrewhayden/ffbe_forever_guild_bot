from __future__ import print_function
import discord
import logging
import pickle
import pprint  # for pretty-printing JSON during debugging, etc
import json
import os.path
import re
from vision_card_screenshot_extractor import downloadScreenshotFromUrl, extractNiceTextFromVisionCard
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------
# Where the main config file for the bot lives.
CONFIG_FILE_PATH = 'bot_config.json'

# Where the token is pickled to, after approving the bot for access to the Google account where the data is to be maintained.
GOOGLE_TOKEN_PICKLE_PATH = 'google_token.pickle'

# The path to the credentials for the bot, downloaded from the Google Developers Console.
GOOGLE_CREDENTIALS_PATH = 'google_credentials.json'

# Scopes required for the bot to maintain data
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# The ID of the Esper Resonance spreadsheet that the bot maintains
ESPER_RESONANCE_SPREADSHEET_ID = None

# The ID of a sandbox Esper Resonance spreadsheet that the bot can use for testing operations
SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID = None

# The ID of the spreadsheet that provides Discord User ID <-> Alias mappings for access control.
ACCESS_CONTROL_SPREADSHEET_ID = None

# The name of the tab that contains the user bindings that map Discord IDs to data tabs.
USERS_TAB_NAME = 'Users'

# The token of the Discord bot, needed to log into Discord.
DISCORD_BOT_TOKEN = None

# Maximum length of a Discord message. Messages longer than this need to be split up.
# The actual limit is 2000 characters but there seems to be some formatting inflation that takes place.
DISCORD_MESSAGE_LENGTH_LIMIT = 1000

# Templates for the various resonance quantities. These match validation rules in the spreadsheet.
RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE = 'Low Priority: {0}/10'
RESONANCE_MEDIUM_PRIORITY_VALUE_TEMPLATE = 'Medium Priority: {0}/10'
RESONANCE_HIGH_PRIORITY_VALUE_TEMPLATE = 'High Priority: {0}/10'
RESONANCE_MAX_VALUE = '10/10'

# -----------------------------------------------------------------------------
# Command Regexes & Help
# -----------------------------------------------------------------------------
HELP = '''`!resonance unit-name/esper-name`
> Get **your own** resonance for the named unit and esper. Example: *!resonance mont/cactuar*

`!resonance unit-or-esper-name`
> Get a full listing of **your own** resonances for the named unit *or* esper. This will generate a listing, in the same order as the spreadsheet, of all the resonance data for the specified unit *or* esper. Example: *!resonance lamia*

`!resonance-set unit-name/esper-name level[/priority[/comment]]`
> Set **your own** resonance for the named unit and esper to the specified level. Optionally, include a priority at the end (H/High/M/Medium/L/Low). If a priority has already been set, it will be preserved. If no priority has been set, the default is "Low". Finally, you can add a comment like "for evade build" as the final string, or the string "<blank>" (without the quotes) to clear an existing comment. Example: *!resonance-set mont/cactuar 9/m/because everyone loves cactuars*

`!resonance-lookup discord-nickname unit-name/esper-name`
> Get **someone else's** resonance for the named unit and esper. Unlike !resonance and !resonance-set, the discord-nickname here is not resolved against the user's snowflake ID. Put another way, it's just the name of the tab in the spreadsheet. This can access data of a former guild members, if your guild leader hasn't deleted it. Example: *!resonance-lookup JohnDoe mont/cactuar*

`!xocr`
> EXPERIMENTAL (might break!): Send this message with no other text, and attach a screenshot of a vision card. The bot will attempt to extract the stats from the vision card image.

**Names of Espers and Units**
You don't have to type out "Sterne Leonis" and "Tetra Sylphid"; you can just shorthand it as "stern/tetra", or even "st/te". Specifically, here's how searching works:
1. If you enclose the name of the unit or esper in double quotes, only an EXACT MATCH will be performed. This is handy to force the correct unit when dealing with some unique situations like "Little Leela" and "Little Leela (Halloween)"
2. Otherwise, if there's only one possible unit name or esper name that STARTS WITH the shorthand, that's enough. For example, there's only one unit whose name starts with "Lass" (Lasswell), so you can just type "Lass" (without the quotes).
3. Otherwise, if there's only one possible unit name or esper name that HAS ALL THE WORDS YOU ENTERED, that's enough. For example, there's only one unit whose name contains both "Lee" and "Hallow", it's "Little Leela (Halloween)". So this is enough to identify her.
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

# Pattern for getting your own list of resonance values for a given esper/unit. Note the lack of a '/' separator.
EXPERIMENTAL_VISION_CARD_OCR_PATTERN = re.compile(r'^!xocr$')

# (Hidden) Pattern for getting your own user ID out of Discord
WHOIS_PATTERN = re.compile(r'^!whois (?P<server_handle>.+)$')

ADMIN_HELP='''
**NOTE**
Due to discord formatting of URLs, in the commands below, the "https://" prefix is displayed as "XX:". This is to prevent Discord from mangling the examples and converting the pipe-delimiters of the commands into URL parameters. where you see "XX:" in a command, you should type "https://" as you normally would to start a URL.

!admin-add-esper name|url|[left-of|right-of]|column-identifier
Add an esper having the specified name and informational URL either left-of or right-of the specified column (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the esper). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The column should be in 'A1' notation, e.g. 'AA' for the 27th column. Example: !admin-add-esper Death Machine|XX:wotv-calc.com/esper/death-machine|left-of|C

!admin-add-unit name|url|[above|below]|row-identifier
Add a unit having the specified name and informational URL either above or below the specified row (whose style will be copied; use this to copy the UR/MR/SR/R/N style as appropriate for the unit). Pipes are used as delimiters in order to accommodate spaces and special characters in names and URLs. The row should be the literal row number from the spreadsheet, i.e. it is 1-based (not 0-based). Example: !admin-add-unit Rain|XX:wotv-calc.com/unit/rain|above|16

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

# Ignore any lines that start with a "!" followed by any non-letter character, since these are definitely not bot commands.
# This prevents people's various exclamations like "!!!!!" from being acknolwedged by the bot.
IGNORE_PATTERN_1 = re.compile(r'^![^a-zA-Z]')

# Similarly, ignore the raw "!" message. Separate from the pattern above for regex sanity.
IGNORE_PATTERN_2 = re.compile(r'^!$')

# List of all ignore patterns, to iterate over.
ALL_IGNORE_PATTERNS = [IGNORE_PATTERN_1, IGNORE_PATTERN_2]

class DiscordSafeException(Exception):
    """An exception whose error text is safe to show in Discord.
    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message


# Reads the configuration file and bootstraps the application. Call this first.
def readConfig():
    global ACCESS_CONTROL_SPREADSHEET_ID
    global ESPER_RESONANCE_SPREADSHEET_ID
    global SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID
    global DISCORD_BOT_TOKEN
    with open(CONFIG_FILE_PATH) as config_file:
        data = json.load(config_file)
        ACCESS_CONTROL_SPREADSHEET_ID = data['access_control_spreadsheet_id']
        ESPER_RESONANCE_SPREADSHEET_ID = data['esper_resonance_spreadsheet_id']
        SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID = data['sandbox_esper_resonance_spreadsheet_id']
        print('esper resonance spreadsheet id: %s' %
              (ESPER_RESONANCE_SPREADSHEET_ID))
        print('sandbox esper resonance spreadsheet id: %s' %
              (SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID))
        DISCORD_BOT_TOKEN = data['discord_bot_token']
        if DISCORD_BOT_TOKEN:
            print('discord bot token: [redacted, but read successfully]')


def safeWorksheetName(sheet_name):
    if "'" in sheet_name:
        raise DiscordSafeException('Names must not contain apostrophes.')
    return "'" + sheet_name + "'"


# If the given message is longer than DISCORD_MESSAGE_LENGTH_LIMIT, splits the message into as many
# chunks as necessary in order to stay under the limit for each message. Tries to respect newlines.
# If a line is too long, this method will fail.
# Returns a list of message fragments, all under DISCORD_MESSAGE_LENGTH_LIMIT in size.
def maybeSplitMessageNicely(message_text):
    if len(message_text) < DISCORD_MESSAGE_LENGTH_LIMIT:
        return [message_text]
    result = []
    buffer = ''
    lines = message_text.splitlines(keepends=True)
    for line in lines:
        if len(line) > DISCORD_MESSAGE_LENGTH_LIMIT:
            # TODO: Support splitting on words?
            raise DiscordSafeException('response too long')
        if (len(buffer) + len(line)) < DISCORD_MESSAGE_LENGTH_LIMIT:
            buffer += line
        else:
            result.append(buffer)
            buffer = line
    if len(buffer) > 0:
        result.append(buffer)
    return result

# Convert an integer value to "A1 Notation", i.e. the column name in a spreadsheet. Max value 26*26.


def toA1(intValue):
    if (intValue > 26*26):
        raise Exception('number too large')
    if (intValue <= 26):
        return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[intValue - 1]
    bigPart = intValue // 26
    remainder = intValue - (bigPart * 26)
    return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[bigPart - 1] + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[remainder - 1]


def fromA1(a1Value):
    numChars = len(a1Value)
    if numChars > 2:
        raise DiscordSafeException('number too large: ' + a1Value)
    a1Value = a1Value.upper()
    result = (ord(a1Value[-1]) - ord('A')) + 1
    if numChars == 2:
        upper = (ord(a1Value[-2]) - ord('A')) + 1
        result = (26 * upper) + result
    return result


# Normalize a name, lowercasing it and replacing spaces with hyphens.
def normalizeName(fancy_name):
    return fancy_name.strip().lower().replace(' ', '-')

# Open the spreadsheet and return a tuple of the service object and the spreadsheets object.


def openSpreadsheets():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(GOOGLE_TOKEN_PICKLE_PATH):
        with open(GOOGLE_TOKEN_PICKLE_PATH, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'google_credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(GOOGLE_TOKEN_PICKLE_PATH, 'wb') as token:
            pickle.dump(creds, token)

    service = build('sheets', 'v4', credentials=creds)
    spreadsheetApp = service.spreadsheets() # pylint: disable=no-member
    return spreadsheetApp

# Return the name of the tab to which the specified Discord snowflake/user ID is bound.
# If the ID can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.


def findAssociatedTab(spreadsheetApp, discord_user_id):
    # Discord IDs are in column A, the associated tab name is in column B
    range_name = safeWorksheetName(USERS_TAB_NAME) + '!A:B'
    rows = None
    try:
        values = spreadsheetApp.values().get(
            spreadsheetId=ACCESS_CONTROL_SPREADSHEET_ID, range=range_name).execute()
        rows = values.get('values', [])
        if not rows:
            raise Exception('')
    except:
        raise DiscordSafeException('Spreadsheet misconfigured')

    for row in rows:
        if (str(row[0]) == str(discord_user_id)):
            return row[1]
    raise DiscordSafeException(
        'User with ID {0} is not configured, or is not allowed to access this data. Ask your guild administrator for assistance.'.format(discord_user_id))


# Return True if the specified discord user id has administrator permissions.
def isAdmin(spreadsheetApp, discord_user_id):
    # Discord IDs are in column A, the associated tab name is in column B, and if 'Admin' is in column C, then it's an admin.
    range_name = safeWorksheetName(USERS_TAB_NAME) + '!A:C'
    rows = None
    try:
        values = spreadsheetApp.values().get(
            spreadsheetId=ACCESS_CONTROL_SPREADSHEET_ID, range=range_name).execute()
        rows = values.get('values', [])
        if not rows:
            raise Exception('')
    except:
        raise DiscordSafeException('Spreadsheet misconfigured')

    for row in rows:
        if (str(row[0]) == str(discord_user_id)):
            result = (len(row) > 2 and row[2] and row[2].lower() == 'admin')
            print('Admin check for discord user {0}: {1}'.format(
                discord_user_id, result))
            return result
    return False


# Return the column (A1 notation value) and fancy-printed name of the esper for the given user's esper.
# If the esper can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.
# Search works as follows:
# 1. If the search_text starts with and ends with double quotes, only an case-insensitive exact matches and is returned.
# 2. Else, if there is exactly one esper whose case-insensitive name starts with the specified search_text, it is returned.
# 3. Else, if there is exactly one esper whose case-insensitive name contains all of the words in the specified search_text, it is returned.
# 4. Else, an exception is raised.
def findEsperColumn(spreadsheetApp, user_name, search_text):
    # Read the esper names row. Esper names are on row 2.
    range_name = safeWorksheetName(user_name) + '!2:2'
    esper_name_rows = None
    esper_name = normalizeName(search_text)
    try:
        values = spreadsheetApp.values().get(
            spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
        esper_name_rows = values.get('values', [])
        if not esper_name_rows:
            raise Exception('')
    except:
        raise DiscordSafeException(
            'Esper resonance tracking info not found for user {0}'.format(user_name))

    # Search for a match and return when found.
    fuzzy_matches = []
    prefix_matches = []
    exact_match_string = None
    if search_text.startswith('"') and search_text.endswith('"'):
        exact_match_string = (search_text[1:-1])
    for esper_name_row in esper_name_rows:
        column_count = 0
        for pretty_name in esper_name_row:
            column_count += 1
            if exact_match_string and (pretty_name.lower() == exact_match_string.lower()):
                esper_column_A1 = toA1(column_count)
                return (esper_column_A1, pretty_name)
            if normalizeName(pretty_name).startswith(esper_name):
                esper_column_A1 = toA1(column_count)
                prefix_matches.append((esper_column_A1, pretty_name))
            if (fuzzyMatches(pretty_name, search_text)):
                esper_column_A1 = toA1(column_count)
                fuzzy_matches.append((esper_column_A1, pretty_name))
    if exact_match_string or (len(fuzzy_matches) == 0 and len(prefix_matches) == 0):
        raise DiscordSafeException(
            'No esper matching text ```{0}``` is being tracked by user {1}, perhaps they do not have it yet.'.format(search_text, user_name))
    if len(prefix_matches) == 1: # Prefer prefix match.
        return prefix_matches[0]
    if len(fuzzy_matches) == 1: # Fall back to fuzzy match
        return fuzzy_matches[0]
    all_matches = set()
    all_matches.update(prefix_matches)
    all_matches.update(fuzzy_matches)
    all_matches_string = ""
    all_matches = list(all_matches)
    max_results = min(5, len(all_matches))
    for index in range(0, max_results):
        all_matches_string += all_matches[index][1]
        if (index < max_results - 1):
            all_matches_string += ", "
    raise DiscordSafeException(
            'Multiple espers matched the text: ```{0}``` Please make your text more specific and try again. For an exact match, enclose your text in double quotes. Possible matches (max 5) are {1}'.format(search_text, all_matches_string))

# Breaks the specified search_text on whitespace, then does a case-insensitive substring match on each of the
# resulting words. If ALL the words are found somewhere in the sheet_text, then it is considered to be a
# match and the method returns True; otherwise, returns False.
def fuzzyMatches(sheet_text, search_text):
    words = search_text.split() # by default splits on all whitespace PRESERVING punctuation, which is important...
    for word in words:
        if not (word.lower() in sheet_text.lower()):
            return False
    return True

# Return the row number (integer value, 1-based) and fancy-printed name of the unit for the given user's unit.
# If the unit can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.
# Search works as follows:
# 1. If the search_text starts with and ends with double quotes, only an case-insensitive exact matches and is returned.
# 2. Else, if there is exactly one unit whose case-insensitive name starts with the specified search_text, it is returned.
# 3. Else, if there is exactly one unit whose case-insensitive name contains all of the words in the specified search_text, it is returned.
# 4. Else, an exception is raised.
def findUnitRow(spreadsheetApp, user_name, search_text):
    # Unit names are on column B.
    range_name = safeWorksheetName(user_name) + '!B:B'
    unit_name_rows = None
    unit_name = normalizeName(search_text)
    try:
        values = spreadsheetApp.values().get(
            spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
        unit_name_rows = values.get('values', [])
        if not unit_name_rows:
            raise Exception('')
    except:
        raise DiscordSafeException(
            'Esper resonance tracking info not found for user {0}'.format(user_name))

    fuzzy_matches = []
    prefix_matches = []
    row_count = 0
    exact_match_string = None
    if search_text.startswith('"') and search_text.endswith('"'):
        exact_match_string = (search_text[1:-1])
    for unit_name_row in unit_name_rows:
        row_count += 1
        for pretty_name in unit_name_row:
            if exact_match_string and (pretty_name.lower() == exact_match_string.lower()):
                return (row_count, pretty_name)
            if normalizeName(pretty_name).startswith(unit_name):
                prefix_matches.append((row_count, pretty_name))
            if (fuzzyMatches(pretty_name, search_text)):
                fuzzy_matches.append((row_count, pretty_name))
    if exact_match_string or (len(fuzzy_matches) == 0 and len(prefix_matches) == 0):
        raise DiscordSafeException(
            'No unit matching text ```{0}``` is being tracked by user {1}, perhaps they do not have it yet.'.format(search_text, user_name))
    if len(prefix_matches) == 1: # Prefer prefix match.
        return prefix_matches[0]
    if len(fuzzy_matches) == 1: # Fall back to fuzzy match
        return fuzzy_matches[0]
    all_matches = set()
    all_matches.update(prefix_matches)
    all_matches.update(fuzzy_matches)
    all_matches_string = ""
    all_matches = list(all_matches)
    max_results = min(5, len(all_matches))
    for index in range(0, max_results):
        all_matches_string += all_matches[index][1]
        if (index < max_results - 1):
            all_matches_string += ", "
    raise DiscordSafeException(
            'Multiple units matched the text: ```{0}``` Please make your text more specific and try again. For an exact match, enclose your text in double quotes. Possible matches (max 5) are {1}'.format(search_text, all_matches_string))


# Add a new column for an esper.
# The left_or_right_of parameter needs to be either the string 'left-of' or 'right-of'. The column should be in A1 notation.
# If sandbox is True, uses a sandbox sheet so that the admin can ensure the results are good before committing to everyone.
def addEsperColumn(discord_user_id, esper_name, esper_url, left_or_right_of, columnA1, sandbox):
    columnInteger = fromA1(columnA1)
    if left_or_right_of == 'left-of':
        inheritFromBefore = False  # Meaning, inherit from right
    elif left_or_right_of == 'right-of':
        inheritFromBefore = True  # Meaning, inherit from left
        columnInteger += 1
    else:
        raise DiscordSafeException(
            'Incorrect parameter for position of new column, must be "left-of" or "right-of": ' + left_or_right_of)

    spreadsheetApp = openSpreadsheets()
    if not isAdmin(spreadsheetApp, discord_user_id):
        raise DiscordSafeException(
            'You do not have permission to add an esper.')

    targetSpreadsheetId = None
    if (sandbox):
        targetSpreadsheetId = SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID
    else:
        targetSpreadsheetId = ESPER_RESONANCE_SPREADSHEET_ID
    spreadsheet = spreadsheetApp.get(
        spreadsheetId=targetSpreadsheetId).execute()

    allRequests = []
    for sheet in spreadsheet['sheets']:
        sheetId = sheet['properties']['sheetId']
        # First create an 'insertDimension' request to add a blank column on each sheet.
        insertDimensionRequest = {
            'insertDimension': {
                # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#insertdimensionrequest
                'inheritFromBefore': inheritFromBefore,
                'range': {
                    'sheetId': sheetId,
                    'dimension': 'COLUMNS',
                    'startIndex': columnInteger - 1,
                    'endIndex': columnInteger
                }
            }
        }
        allRequests.append(insertDimensionRequest)

        # Now add the esper data to the new column on each sheet.
        startColumnIndex = columnInteger - 1
        updateCellsRequest = {
            'updateCells': {
                # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#updatecellsrequest
                'rows': [{
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/sheets#RowData
                    'values': [{
                        # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/cells#CellData
                        'userEnteredValue': {
                            # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/other#ExtendedValue
                            'formulaValue': '=HYPERLINK("' + esper_url + '", "' + esper_name + '")'
                        }
                    }]
                }],
                'fields': 'userEnteredValue',
                'range': {
                    'sheetId': sheetId,
                    'startRowIndex': 1,  # inclusive
                    'endRowIndex': 2,  # exclusive
                    'startColumnIndex': startColumnIndex,  # inclusive
                    'endColumnIndex': startColumnIndex+1  # exclusive
                }
            }
        }
        allRequests.append(updateCellsRequest)

    requestBody = {
        'requests': [allRequests]
    }
    # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
    spreadsheetApp.batchUpdate(
        spreadsheetId=targetSpreadsheetId, body=requestBody).execute()

    return


# Add a new row for a unit.
# The above_or_below parameter needs to be either the string 'above' or 'below'. The row should be in 1-based notation,
# i.e. the first row is row 1, not row 0.
# If sandbox is True, uses a sandbox sheet so that the admin can ensure the results are good before committing to everyone.
def addUnitRow(discord_user_id, unit_name, unit_url, above_or_below, row1Based, sandbox):
    rowInteger = int(row1Based)
    if above_or_below == 'above':
        inheritFromBefore = False  # Meaning, inherit from below
    elif above_or_below == 'below':
        inheritFromBefore = True  # Meaning, inherit from above
        rowInteger += 1
    else:
        raise DiscordSafeException(
            'Incorrect parameter for position of new row, must be "above" or "below": ' + above_or_below)

    spreadsheetApp = openSpreadsheets()
    if not isAdmin(spreadsheetApp, discord_user_id):
        raise DiscordSafeException(
            'You do not have permission to add a unit.')

    targetSpreadsheetId = None
    if (sandbox):
        targetSpreadsheetId = SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID
    else:
        targetSpreadsheetId = ESPER_RESONANCE_SPREADSHEET_ID
    spreadsheet = spreadsheetApp.get(
        spreadsheetId=targetSpreadsheetId).execute()

    allRequests = []
    for sheet in spreadsheet['sheets']:
        sheetId = sheet['properties']['sheetId']
        # First create an 'insertDimension' request to add a blank row on each sheet.
        insertDimensionRequest = {
            'insertDimension': {
                # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#insertdimensionrequest
                'inheritFromBefore': inheritFromBefore,
                'range': {
                    'sheetId': sheetId,
                    'dimension': 'ROWS',
                    'startIndex': rowInteger - 1,
                    'endIndex': rowInteger
                }
            }
        }
        allRequests.append(insertDimensionRequest)

        # Now add the unit data to the new row on each sheet.
        startRowIndex = rowInteger - 1
        updateCellsRequest = {
            'updateCells': {
                # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#updatecellsrequest
                'rows': [{
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/sheets#RowData
                    'values': [{
                        # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/cells#CellData
                        'userEnteredValue': {
                            # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/other#ExtendedValue
                            'formulaValue': '=HYPERLINK("' + unit_url + '", "' + unit_name + '")'
                        }
                    }]
                }],
                'fields': 'userEnteredValue',
                'range': {
                    'sheetId': sheetId,
                    'startRowIndex': startRowIndex,  # inclusive
                    'endRowIndex': startRowIndex+1,  # exclusive
                    'startColumnIndex': 1,  # inclusive
                    'endColumnIndex': 2  # exclusive
                }
            }
        }
        allRequests.append(updateCellsRequest)

    requestBody = {
        'requests': [allRequests]
    }
    # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
    spreadsheetApp.batchUpdate(
        spreadsheetId=targetSpreadsheetId, body=requestBody).execute()

    return


# Read and return the esper resonance, pretty unit name, and pretty esper name for the given (unit, esper) tuple, for the given user.
# Set either the user name or the discord user ID, but not both. If the ID is set, the tab name for the resonance lookup is done the
# same way as setResonance - an indirection through the access control spreadsheet is used to map the ID of the discord user to the
# right tab. This is best for self-lookups, so that even if a user changes their own nickname, they are still reading their own data
# and not the data of, e.g., another user who has their old nickname.
def readResonance(user_name, discord_user_id, unit_name, esper_name):
    spreadsheetApp = openSpreadsheets()
    if (user_name is not None) and (discord_user_id is not None):
        print('internal error: both user_name and discord_user_id specified. Specify one or the other, not both.')
        raise DiscordSafeException('Internal error')
    if discord_user_id is not None:
        user_name = findAssociatedTab(spreadsheetApp, discord_user_id)

    esper_column_A1, pretty_esper_name = findEsperColumn(
        spreadsheetApp, user_name, esper_name)
    unit_row, pretty_unit_name = findUnitRow(
        spreadsheetApp, user_name, unit_name)

    # We have the location. Get the value!
    range_name = safeWorksheetName(
        user_name) + '!' + esper_column_A1 + str(unit_row) + ':' + esper_column_A1 + str(unit_row)
    result = spreadsheetApp.values().get(
        spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
    final_rows = result.get('values', [])

    if not final_rows:
        raise DiscordSafeException('{0} is not tracking any resonance for esper {1} on unit {2}'.format(
            user_name, pretty_esper_name, pretty_unit_name))

    return final_rows[0][0][0], pretty_unit_name, pretty_esper_name


# Read and return the pretty name of the query subject (either a unit or an esper), along with a list of resonances
# (either unit/resonance, or esper/resonance tuples), for the given user.
# Set either the user name or the discord user ID, but not both. If the ID is set, the tab name for the resonance lookup is done the
# same way as setResonance - an indirection through the access control spreadsheet is used to map the ID of the discord user to the
# right tab. This is best for self-lookups, so that even if a user changes their own nickname, they are still reading their own data
# and not the data of, e.g., another user who has their old nickname.
def readResonanceList(user_name, discord_user_id, query_string):
    spreadsheetApp = openSpreadsheets()
    if (user_name is not None) and (discord_user_id is not None):
        print('internal error: both user_name and discord_user_id specified. Specify one or the other, not both.')
        raise DiscordSafeException('Internal error')
    if discord_user_id is not None:
        user_name = findAssociatedTab(spreadsheetApp, discord_user_id)

    esper_column_A1 = None
    pretty_esper_name = None
    unit_row_index = None
    pretty_unit_name = None
    mode = None
    target_name = None

    # First try to look up a unit whose name matches.
    unit_lookup_exception_message = None
    try:
        unit_row_index, pretty_unit_name = findUnitRow(
            spreadsheetApp, user_name, query_string)
        mode = 'for unit'
        target_name = pretty_unit_name
    except DiscordSafeException as ex:
        unit_lookup_exception_message = ex.message
        pass

    # Try an esper lookup instead
    esper_lookup_exception_message = None
    if mode is None:
        try:
            esper_column_A1, pretty_esper_name = findEsperColumn(
                spreadsheetApp, user_name, query_string)
            mode = 'for esper'
            target_name = pretty_esper_name
        except DiscordSafeException as ex:
            esper_lookup_exception_message = ex.message
            pass

    # If neither esper or unit is found, fail now.
    if mode is None:
        raise DiscordSafeException(
            'Unable to find a singular match for: ```{0}```\nUnit lookup results: {1}\nEsper lookup results: {2}'.format(query_string, unit_lookup_exception_message, esper_lookup_exception_message))

    # Grab all the data in one call, so we can read everything at once and have atomicity guarantees.
    result = spreadsheetApp.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID,
                                         range=safeWorksheetName(user_name)).execute()
    result_rows = result.get('values', [])
    resonances = []
    if mode == 'for esper':
        esper_index = fromA1(esper_column_A1) - 1  # 0-indexed in result
        rowCount = 0
        for row in result_rows:
            rowCount += 1
            if rowCount < 3:
                # skip headers
                continue
            # rows collapse to the left, so only the last non-empty column exists in the data
            if len(row) > esper_index:
                # annnnd as a result, there might be a value to the right, while this column could be empty.
                if row[esper_index]:
                    resonances.append(row[1] + ': ' + row[esper_index])
    else:  # mode == 'for unit'
        colCount = 0
        unit_row = result_rows[unit_row_index - 1]  # 0-indexed in result
        for column in unit_row:
            colCount += 1
            if colCount < 3:
                # skip headers
                continue
            if column:
                # Grab the esper name from the top of this column, and then append the column value.
                resonances.append(result_rows[1][colCount - 1] + ': ' + column)

    # Format the list nicely for responding in Discord
    resultString = ''
    for resonance in resonances:
        resultString += resonance + '\n'
    resultString = resultString.strip()
    return (target_name, resultString)


# Set the esper resonance. Returns the old value, new value, pretty unit name, and pretty esper name for the given (unit, esper) tuple, for the given user.
def setResonance(discord_user_id, unit_name, esper_name, resonance_numeric_string, priority, comment):
    resonance_int = None
    try:
        resonance_int = int(resonance_numeric_string)
    except:
        raise DiscordSafeException(
            'Invalid resonance level: "{0}"'.format(resonance_numeric_string))
    if (resonance_int < 0) or (resonance_int > 10):
        raise DiscordSafeException(
            'Resonance must be a value in the range 0 - 10')

    spreadsheetApp = openSpreadsheets()
    user_name = findAssociatedTab(spreadsheetApp, discord_user_id)

    esper_column_A1, pretty_esper_name = findEsperColumn(
        spreadsheetApp, user_name, esper_name)
    unit_row, pretty_unit_name = findUnitRow(
        spreadsheetApp, user_name, unit_name)

    spreadsheet = spreadsheetApp.get(
        spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID).execute()
    sheetId = None
    for sheet in spreadsheet['sheets']:
        sheetTitle = sheet['properties']['title']
        if sheetTitle == user_name:
            sheetId = sheet['properties']['sheetId']
            break
    if sheetId is None:
        raise DiscordSafeException(
            'Internal error: sheet not found for {0}.'.format(user_name))

    # We have the location. Get the old value first.
    range_name = safeWorksheetName(
        user_name) + '!' + esper_column_A1 + str(unit_row) + ':' + esper_column_A1 + str(unit_row)
    result = spreadsheetApp.values().get(
        spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
    final_rows = result.get('values', [])
    old_value_string = '(not set)'
    if final_rows:
        old_value_string = final_rows[0][0]

    # Now that we have the old value, try to update the new value.
    # If priority is blank, leave the level (high/medium/low) alone.
    if priority is not None:
        priority = priority.lower()
    priorityString = None
    if (resonance_int == 10):
        priorityString = '10/10'
    elif (priority == 'l') or (priority == 'low') or (priority is None and 'low' in old_value_string.lower()):
        priorityString = RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE.format(
            resonance_int)
    elif (priority == 'm') or (priority == 'medium') or (priority is None and 'medium' in old_value_string.lower()):
        priorityString = RESONANCE_MEDIUM_PRIORITY_VALUE_TEMPLATE.format(
            resonance_int)
    elif (priority == 'h') or (priority == 'high') or (priority is None and 'high' in old_value_string.lower()):
        priorityString = RESONANCE_HIGH_PRIORITY_VALUE_TEMPLATE.format(
            resonance_int)
    elif (priority is None):
        # Priority not specified, and old value doesn't have high/medium/low -> old value was blank, or old value was 10.
        # Default to low priority.
        priorityString = RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE.format(
            resonance_int)
    else:
        raise DiscordSafeException(
            'Unknown priority value. Priority should be blank or one of "L", "low", "M", "medium", "H", "high"')

    # Now write the new value
    updateValueRequest = {
        'updateCells': {
            'rows': [{
                'values': [{
                    'userEnteredValue': {
                        'stringValue': priorityString
                    }
                }]
            }],
            'fields': 'userEnteredValue',
            'range': {
                'sheetId': sheetId,
                'startRowIndex': unit_row-1,  # inclusive
                'endRowIndex': unit_row,  # exclusive
                'startColumnIndex': fromA1(esper_column_A1)-1,  # inclusive
                'endColumnIndex': fromA1(esper_column_A1)  # exclusive
            }
        }
    }
    allRequests = []
    allRequests.append(updateValueRequest)

    if comment:
        commentText = comment
        if comment == '<blank>':  # Allow clearing the comment
            commentText = ''
        updateCommentRequest = {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'note': commentText
                    }]
                }],
                'fields': 'note',
                'range': {
                    'sheetId': sheetId,
                    'startRowIndex': unit_row-1,  # inclusive
                    'endRowIndex': unit_row,  # exclusive
                    'startColumnIndex': fromA1(esper_column_A1)-1,  # inclusive
                    'endColumnIndex': fromA1(esper_column_A1)  # exclusive
                }
            }
        }
        allRequests.append(updateCommentRequest)

    requestBody = {
        'requests': [allRequests]
    }
    # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
    spreadsheetApp.batchUpdate(
        spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, body=requestBody).execute()
    return old_value_string, priorityString, pretty_unit_name, pretty_esper_name

# Generate a safe response for a message from discord, or None if no response is needed.

def prettyPrintVisionCardOcrText(structured):
    result = 'Stats:\n'
    result += '  HP: ' + str(structured['HP']) + '\n'
    result += '  ATK: ' + str(structured['ATK']) + '\n'
    result += '  MAG: ' + str(structured['MAG']) + '\n'
    result += 'Bestowed Effects:\n'
    for effect in structured['Bestowed Effects']:
        result += '  ' + effect + '\n'
    result += 'Party Ability:\n'
    result += '  ' + structured['Party Ability']
    return result

def getDiscordSafeResponse(message):
    if message.author == discord_client.user:
        return (None, None)

    if not message.content:
        return (None, None)

    if not message.content.startswith('!'):
        return (None, None)

    for ignore_pattern in ALL_IGNORE_PATTERNS:
        if ignore_pattern.match(message.content):
            return (None, None)

    from_name = message.author.display_name
    from_id = message.author.id
    from_discrim = message.author.discriminator

    match = RES_FETCH_SELF_PATTERN.match(message.content.lower())
    if match:
        unit_name = match.group(1).strip()
        esper_name = match.group(2).strip()
        print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (
            from_name, from_discrim, from_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = readResonance(
            None, from_id, unit_name, esper_name)
        responseText = '<@{0}>: {1}/{2} has resonance {3}'.format(
            from_id, pretty_unit_name, pretty_esper_name, resonance)
        return (responseText, None)

    match = RES_LIST_SELF_PATTERN.match(message.content.lower())
    if match:
        target_name = match.group('target_name').strip()
        print('resonance list fetch from user %s#%s, for target %s' %
              (from_name, from_discrim, target_name))
        pretty_name, resonance_listing = readResonanceList(
            None, from_id, target_name)
        responseText = '<@{0}>: resonance listing for {1}:\n{2}'.format(
            from_id, pretty_name, resonance_listing)
        return (responseText, None)

    match = RES_FETCH_OTHER_PATTERN.match(message.content.lower())
    if match:
        target_user_name = match.group(1).strip()
        unit_name = match.group(2).strip()
        esper_name = match.group(3).strip()
        print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (
            from_name, from_discrim, target_user_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = readResonance(
            target_user_name, None, unit_name, esper_name)
        responseText = '<@{0}>: for user {1}, {2}/{3} has resonance {4}'.format(
            from_id, target_user_name, pretty_unit_name, pretty_esper_name, resonance)
        return (responseText, None)

    match = RES_SET_PATTERN.match(message.content.lower())
    if match:
        unit_name = match.group('unit').strip()
        esper_name = match.group('esper').strip()
        resonance_numeric_string = match.group('resonance_level').strip()
        priority = None
        if match.group('priority'):
            priority = match.group('priority').strip()
        comment = None
        if match.group('comment'):
            comment = match.group('comment').strip()
        print('resonance set from user %s#%s, for unit %s, for esper %s, to resonance %s, with priority %s, comment %s' % (
            from_name, from_discrim, unit_name, esper_name, resonance_numeric_string, priority, comment))
        old_resonance, new_resonance, pretty_unit_name, pretty_esper_name = setResonance(
            from_id, unit_name, esper_name, resonance_numeric_string, priority, comment)
        responseText = '<@{0}>: {1}/{2} resonance has been set to {3} (was: {4})'.format(
            from_id, pretty_unit_name, pretty_esper_name, new_resonance, old_resonance)
        if (resonance_numeric_string and int(resonance_numeric_string) == 10):
            # reaction = '\U0001F4AA' # CLDR: flexed biceps
            reaction = '\U0001F3C6'  # CLDR: trophy
        else:
            reaction = '\U00002705'  # CLDR: check mark button
        return (responseText, reaction)

    # Hidden utility command to look up the snowflake ID of your own user. This isn't secret or insecure,
    # but it's also not common, so it isn't listed in help.
    if message.content.lower().startswith('!whoami'):
        responseText = '<@{0}>: Your snowflake ID is {1}'.format(
            from_id, from_id)
        return (responseText, None)

    # Hidden utility command to look up the snowflake ID of a member. This isn't secret or insecure,
    # but it's also not common, so it isn't listed in help.
    match = WHOIS_PATTERN.match(message.content.lower())
    if match:
        match = WHOIS_PATTERN.match(message.content) # Fetch original-case name
        target_member_name = match.group('server_handle').strip()
        members = message.guild.members
        for member in members:
            if (member.name == target_member_name):
                responseText = '<@{0}>: the snowflake ID for {1} is {2}'.format(from_id, target_member_name, member.id)
                return (responseText, None)
        responseText = '<@{0}>: no such member {1}'.format(
            from_id, target_member_name)
        return (responseText, None)

    # (Admin only) Pattern for adding an Esper column.
    match = ADMIN_ADD_ESPER_PATTERN.match(message.content)
    sandbox_match = SANDBOX_ADMIN_ADD_ESPER_PATTERN.match(message.content)
    admin_add_esper_match = None
    sandbox = False
    if match:
        admin_add_esper_match = match
    elif sandbox_match:
        admin_add_esper_match = sandbox_match
        sandbox = True

    if admin_add_esper_match:
        esper_name = admin_add_esper_match.group('name').strip()
        esper_url = admin_add_esper_match.group('url').strip()
        left_or_right_of = admin_add_esper_match.group(
            'left_or_right_of').strip()
        column = admin_add_esper_match.group('column').strip()
        print('esper add (sandbox mode={6}) from user {0}#{1}, for esper {2}, url {3}, position {4}, column {5}'.format(
            from_name, from_discrim, esper_name, esper_url, left_or_right_of, column, sandbox))
        addEsperColumn(from_id, esper_name, esper_url,
                       left_or_right_of, column, sandbox)
        responseText = '<@{0}>: Added esper {1}!'.format(from_id, esper_name)
        return (responseText, None)

    # (Admin only) Pattern for adding a Unit row.
    match = ADMIN_ADD_UNIT_PATTERN.match(message.content)
    sandbox_match = SANDBOX_ADMIN_ADD_UNIT_PATTERN.match(message.content)
    admin_add_unit_match = None
    sandbox = False
    if match:
        admin_add_unit_match = match
    elif sandbox_match:
        admin_add_unit_match = sandbox_match
        sandbox = True

    if admin_add_unit_match:
        unit_name = admin_add_unit_match.group('name').strip()
        unit_url = admin_add_unit_match.group('url').strip()
        above_or_below = admin_add_unit_match.group('above_or_below').strip()
        row1Based = admin_add_unit_match.group('row1Based').strip()
        print('unit add (sandbox mode={6}) from user {0}#{1}, for unit {2}, url {3}, position {4}, row {5}'.format(
            from_name, from_discrim, unit_name, unit_url, above_or_below, row1Based, sandbox))
        addUnitRow(from_id, unit_name, unit_url,
                       above_or_below, row1Based, sandbox)
        responseText = '<@{0}>: Added unit {1}!'.format(from_id, unit_name)
        return (responseText, None)

    if message.content.lower().startswith('!resonance'):
        responseText = '<@{0}>: Invalid !resonance command. Use !help for more information.'.format(
            from_id)
        return (responseText, None)

    match = EXPERIMENTAL_VISION_CARD_OCR_PATTERN.match(message.content.lower())
    if match:
        # Try to extract text from a vision card screenshot that is sent as an attachment to this message.
        url = message.attachments[0].url
        print('vision card ocr request from user %s#%s, for url %s' % (from_name, from_discrim, url))
        screenshot = downloadScreenshotFromUrl(url)
        extractedText = extractNiceTextFromVisionCard(screenshot)
        responseText = '<@{0}>: Extracted from vision card:\n{1}'.format(from_id, prettyPrintVisionCardOcrText(extractedText))
        return (responseText, None)

    if message.content.lower().startswith('!help'):
        responseText = HELP.format(ESPER_RESONANCE_SPREADSHEET_ID)
        return (responseText, None)

    if message.content.lower().startswith('!admin-help'):
        responseText = ADMIN_HELP.format(ESPER_RESONANCE_SPREADSHEET_ID,SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID)
        return (responseText, None)

    return ('<@{0}>: Invalid or unknown command. Use !help to see all supported commands and !admin-help to see special admin commands. Please do this via a direct message to the bot, to avoid spamming the channel.'.format(from_id), None)


if __name__ == "__main__":
    readConfig()
    discord_client = discord.Client()
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    # logger.setLevel(logging.DEBUG)
    # handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)


def getDiscordClient():
    return discord_client


@discord_client.event
async def on_ready():
    print('Bot logged in: {0.user}'.format(discord_client))


@discord_client.event
async def on_message(message):
    responseText = None
    reaction = None
    try:
        responseText, reaction = getDiscordSafeResponse(message)
    except DiscordSafeException as safeException:
        responseText = safeException.message
    if responseText:
        fullTextToSend = maybeSplitMessageNicely(responseText)
        for chunk in fullTextToSend:
            await message.channel.send(chunk)
    if reaction:
        await message.add_reaction(reaction)

if __name__ == "__main__":
    discord_client.run(DISCORD_BOT_TOKEN)
