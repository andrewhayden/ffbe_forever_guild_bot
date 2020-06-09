from __future__ import print_function
import discord
import logging
import pickle
import pprint # for pretty-printing JSON during debugging, etc
import json
import os.path
import re
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------
# Where the main config file for the bot lives.
CONFIG_FILE_PATH = "bot_config.json"

# Where the token is pickled to, after approving the bot for access to the Google account where the data is to be maintained.
GOOGLE_TOKEN_PICKLE_PATH = "google_token.pickle"

# The path to the credentials for the bot, downloaded from the Google Developers Console.
GOOGLE_CREDENTIALS_PATH = "google_credentials.json"

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

# Templates for the various resonance quantities. These match validation rules in the spreadsheet.
RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE = 'Low Priority: {0}/10'
RESONANCE_MEDIUM_PRIORITY_VALUE_TEMPLATE = 'Medium Priority: {0}/10'
RESONANCE_HIGH_PRIORITY_VALUE_TEMPLATE = 'High Priority: {0}/10'
RESONANCE_MAX_VALUE = "10/10"

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

**Shorthand Support**
You don't have to type out "Sterne Leonis" and "Tetra Sylphid"; you can just shorthand it as "stern/tetra", or even "st/te". Specifically, a case-insensitive prefix match is used.

View your guild's Esper resonance data here: <https://docs.google.com/spreadsheets/d/{0}>
'''

# Pattern for getting your own resonance value
RES_FETCH_SELF_PATTERN = re.compile("^!resonance (.+)/(.+)$")

# Pattern for getting your own list of resonance values for a given esper/unit. Note the lack of a '/' separator.
RES_LIST_SELF_PATTERN = re.compile("^!resonance (?P<target_name>.+)$")

# Pattern for setting your own resonance value
RES_SET_PATTERN = re.compile("^!resonance-set (?P<unit>.+)/(?P<esper>.+)\s+(?P<resonance_level>[0-9]+)\s*(/\s*(?P<priority>[^\/]+)(/\s*(?P<comment>[^\/]+))?)?$")

# Pattern for getting someone else's resonance value
RES_FETCH_OTHER_PATTERN = re.compile("^!resonance-lookup (\S+) (.+)/(.+)$")

# (Hidden) Pattern for getting your own resonance value
WHOIS_PATTERN = re.compile("^!whois (.+)$")

# (Admin only) Pattern for adding an Esper column.
# Sandbox mode uses a different sheet, for testing.
ADMIN_ADD_ESPER_PATTERN = re.compile("^!admin-add-esper (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<left_or_right_of>.+)\|(?P<column>.+)$")
SANDBOX_ADMIN_ADD_ESPER_PATTERN = re.compile("^!sandbox-admin-add-esper (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<left_or_right_of>.+)\|(?P<column>.+)$")

# Maximum length of a Discord message. Messages longer than this need to be split up.
# The actual limit is 2000 characters but there seems to be some formatting inflation that takes place.
DISCORD_MESSAGE_LENGTH_LIMIT = 1000

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
        print('esper resonance spreadsheet id: %s' % (ESPER_RESONANCE_SPREADSHEET_ID))
        print('sandbox esper resonance spreadsheet id: %s' % (SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID))
        DISCORD_BOT_TOKEN = data['discord_bot_token']
        if DISCORD_BOT_TOKEN: print('discord bot token: [redacted, but read successfully]')


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
    if (intValue > 26*26): raise Exception("number too large")
    if (intValue <= 26): return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[intValue - 1]
    bigPart = intValue // 26
    remainder = intValue - (bigPart * 26)
    return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[bigPart - 1] + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[intValue - 1]


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
    return fancy_name.strip().lower().replace(" ", "-")

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
    spreadsheetApp = service.spreadsheets()
    return (service, spreadsheetApp)

# Return the name of the tab to which the specified Discord snowflake/user ID is bound.
# If the ID can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.
def findAssociatedTab(spreadsheetApp, discord_user_id):
    # Discord IDs are in column A, the associated tab name is in column B
    range_name = safeWorksheetName(USERS_TAB_NAME) + '!A:B'
    rows = None
    try:
        values = spreadsheetApp.values().get(spreadsheetId=ACCESS_CONTROL_SPREADSHEET_ID, range=range_name).execute()
        rows = values.get('values', [])
        if not rows: raise Exception('')
    except:
        raise DiscordSafeException('Spreadsheet misconfigured'.format(discord_user_id))

    for row in rows:
        if (str(row[0]) == str(discord_user_id)):
            return row[1]
    raise DiscordSafeException('User with ID {0} is not configured, or is not allowed to access this data. Ask your guild administrator for assistance.'.format(discord_user_id))


# Return True if the specified discord user id has administrator permissions.
def isAdmin(spreadsheetApp, discord_user_id):
    # Discord IDs are in column A, the associated tab name is in column B, and if "Admin" is in column C, then it's an admin.
    range_name = safeWorksheetName(USERS_TAB_NAME) + '!A:C'
    rows = None
    try:
        values = spreadsheetApp.values().get(spreadsheetId=ACCESS_CONTROL_SPREADSHEET_ID, range=range_name).execute()
        rows = values.get('values', [])
        if not rows: raise Exception('')
    except:
        raise DiscordSafeException('Spreadsheet misconfigured'.format(discord_user_id))

    for row in rows:
        if (str(row[0]) == str(discord_user_id)):
            result = (len(row) > 2 and row[2] and row[2].lower() == 'admin')
            print('Admin check for discord user {0}: {1}'.format(discord_user_id, result))
            return result
    return False


# Return the column (A1 notation value) and fancy-printed name of the esper for the given user's esper.
# If the esper can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.
def findEsperColumn(spreadsheetApp, user_name, esper_name):
    # Read the esper names row. Esper names are on row 2.
    range_name = safeWorksheetName(user_name) + '!2:2'
    esper_name_rows = None
    esper_name = normalizeName(esper_name)
    try:
        values = spreadsheetApp.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
        esper_name_rows = values.get('values', [])
        if not esper_name_rows: raise Exception('')
    except:
        raise DiscordSafeException('Esper resonance tracking info not found for user {0}'.format(user_name))

    # Search for a match and return when found.
    for esper_name_row in esper_name_rows:
        column_count = 0
        for pretty_name in esper_name_row:
            column_count += 1
            if normalizeName(pretty_name).startswith(esper_name):
                esper_column_A1 = toA1(column_count)
                return (esper_column_A1, pretty_name)

    raise DiscordSafeException('No such esper {0} is being tracked by user {1}, perhaps they do not have it yet.'.format(esper_name, user_name))


# Return the row number (integer value, 1-based) and fancy-printed name of the unit for the given user's unit.
# If the unit can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.
def findUnitRow(spreadsheetApp, user_name, unit_name):
    # Unit names are on column B.
    range_name = safeWorksheetName(user_name) + '!B:B'
    unit_name_rows = None
    unit_name = normalizeName(unit_name)
    try:
        values = spreadsheetApp.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
        unit_name_rows = values.get('values', [])
        if not unit_name_rows: raise Exception('')
    except:
        raise DiscordSafeException('Esper resonance tracking info not found for user {0}'.format(user_name))

    row_count = 0
    for unit_name_row in unit_name_rows:
        row_count += 1
        for pretty_name in unit_name_row:
            if normalizeName(pretty_name).startswith(unit_name):
                return (row_count, pretty_name)
    raise DiscordSafeException('No such unit {0} is being tracked by user {1}, perhaps they do not have it yet.'.format(unit_name, user_name))


# Add a new column for an esper.
# The left_or_right_of parameter needs to be either the string 'left-of' or 'right-of'. The column should be in A1 notation.
# If sandbox is True, uses a sandbox sheet so that the admin can ensure the results are good before committing to everyone.
def addEsperColumn(discord_user_id, esper_name, esper_url, left_or_right_of, columnA1, sandbox):
    inheritValue = None
    columnInteger = fromA1(columnA1)
    if left_or_right_of == 'left-of':
        inheritFromBefore = False # Meaning, inherit from right
    elif left_or_right_of == 'right-of':
        inheritFromBefore = True # Meaning, inherit from left
        columnInteger += 1
    else:
        raise DiscordSafeException('Incorrect parameter for position of new column, must be "left-of" or "right-of": ' + left_or_right_of)

    service, spreadsheetApp = openSpreadsheets()
    if not isAdmin(spreadsheetApp, discord_user_id):
        raise DiscordSafeException('You do not have permission to add an esper.')

    targetSpreadsheetId = None
    if (sandbox):
        targetSpreadsheetId = SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID
    else:
        targetSpreadsheetId = ESPER_RESONANCE_SPREADSHEET_ID
    spreadsheet = spreadsheetApp.get(spreadsheetId=targetSpreadsheetId).execute()

    allRequests = []
    for sheet in spreadsheet['sheets']:
        sheetId = sheet['properties']['sheetId']
        sheetTitle = sheet['properties']['title']
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
                            'formulaValue': '=HYPERLINK("' + esper_url +'", "' + esper_name + '")'
                        }
                    }]
                }],
                'fields': 'userEnteredValue',
                'range': {
                    'sheetId': sheetId,
                    'startRowIndex': 1, # inclusive
                    'endRowIndex': 2, # exclusive
                    'startColumnIndex': startColumnIndex, # inclusive
                    'endColumnIndex': startColumnIndex+1 # exclusive
                }
            }
        }
        allRequests.append(updateCellsRequest)

    requestBody = {
        'requests': [allRequests]
    }
    # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
    spreadsheetApp.batchUpdate(spreadsheetId=targetSpreadsheetId, body=requestBody).execute()

    return

# Read and return the esper resonance, pretty unit name, and pretty esper name for the given (unit, esper) tuple, for the given user.
# Set either the user name or the discord user ID, but not both. If the ID is set, the tab name for the resonance lookup is done the
# same way as setResonance - an indirection through the access control spreadsheet is used to map the ID of the discord user to the
# right tab. This is best for self-lookups, so that even if a user changes their own nickname, they are still reading their own data
# and not the data of, e.g., another user who has their old nickname.
def readResonance(user_name, discord_user_id, unit_name, esper_name):
    service, spreadsheetApp = openSpreadsheets()
    if (user_name is not None) and (discord_user_id is not None):
        print('internal error: both user_name and discord_user_id specified. Specify one or the other, not both.')
        raise DiscordSafeException('Internal error')
    if discord_user_id is not None:
        user_name = findAssociatedTab(spreadsheetApp, discord_user_id)

    esper_column_A1, pretty_esper_name = findEsperColumn(spreadsheetApp, user_name, esper_name)
    unit_row, pretty_unit_name = findUnitRow(spreadsheetApp, user_name, unit_name)

    # We have the location. Get the value!
    range_name = safeWorksheetName(user_name) + '!' + esper_column_A1 + str(unit_row) + ':' + esper_column_A1 + str(unit_row)
    result = spreadsheetApp.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
    final_rows = result.get('values', [])

    if not final_rows:
        raise DiscordSafeException('{0} is not tracking any resonance for esper {1} on unit {2}'.format(user_name, pretty_esper_name, pretty_unit_name))

    for row in final_rows:
        for value in final_rows:
            return value[0], pretty_unit_name, pretty_esper_name


# Read and return the pretty name of the query subject (either a unit or an esper), along with a list of resonances
# (either unit/resonance, or esper/resonance tuples), for the given user.
# Set either the user name or the discord user ID, but not both. If the ID is set, the tab name for the resonance lookup is done the
# same way as setResonance - an indirection through the access control spreadsheet is used to map the ID of the discord user to the
# right tab. This is best for self-lookups, so that even if a user changes their own nickname, they are still reading their own data
# and not the data of, e.g., another user who has their old nickname.
def readResonanceList(user_name, discord_user_id, query_string):
    service, spreadsheetApp = openSpreadsheets()
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
    try:
        unit_row_index, pretty_unit_name = findUnitRow(spreadsheetApp, user_name, query_string)
        mode = 'for unit'
        target_name = pretty_unit_name
    except:
        pass

    # Try an esper lookup instead
    if mode is None:
        try:
            esper_column_A1, pretty_esper_name = findEsperColumn(spreadsheetApp, user_name, query_string)
            mode = 'for esper'
            target_name = pretty_esper_name
        except:
            pass

    # If neither esper or unit is found, fail now.
    if mode is None:
        raise DiscordSafeException('No esper or unit found whose name starts with "{0}", please check the spelling and try again.'.format(query_string))

    # Grab all the data in one call, so we can read everything at once and have atomicity guarantees.
    result = spreadsheetApp.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=safeWorksheetName(user_name)).execute()
    result_rows = result.get('values', [])
    resonances = []
    if mode == 'for esper':
        esper_index = fromA1(esper_column_A1) - 1 # 0-indexed in result
        rowCount = 0
        for row in result_rows:
            rowCount += 1
            if rowCount < 3:
                # skip headers
                continue
            if len(row) > esper_index: # rows collapse to the left, so only the last non-empty column exists in the data
                if row[esper_index]: # annnnd as a result, there might be a value to the right, while this column could be empty.
                    resonances.append(row[1] + ': ' + row[esper_index])
    else: # mode == 'for unit'
        colCount = 0
        unit_row = result_rows[unit_row_index - 1] # 0-indexed in result
        for column in unit_row:
            colCount += 1
            if colCount < 3:
                # skip headers
                continue
            if column:
                # Grab the esper name from the top of this column, and then append the column value.
                resonances.append(result_rows[1][colCount - 1] + ': ' + column)

    #Format the list nicely for responding in Discord
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
        raise DiscordSafeException('Invalid resonance level: "{0}"'.format(resonance_numeric_string))
    if (resonance_int < 0) or (resonance_int > 10):
        raise DiscordSafeException('Resonance must be a value in the range 0 - 10')

    service, spreadsheetApp = openSpreadsheets()
    user_name = findAssociatedTab(spreadsheetApp, discord_user_id)

    esper_column_A1, pretty_esper_name = findEsperColumn(spreadsheetApp, user_name, esper_name)
    unit_row, pretty_unit_name = findUnitRow(spreadsheetApp, user_name, unit_name)

    spreadsheet = spreadsheetApp.get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID).execute()
    sheetId = None
    for sheet in spreadsheet['sheets']:
        sheetTitle = sheet['properties']['title']
        if sheetTitle == user_name:
            sheetId = sheet['properties']['sheetId']
            break
    if sheetId is None:
        raise DiscordSafeException('Internal error: sheet not found for {0}.'.format(user_name))

    # We have the location. Get the old value first.
    range_name = safeWorksheetName(user_name) + '!' + esper_column_A1 + str(unit_row) + ':' + esper_column_A1 + str(unit_row)
    result = spreadsheetApp.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
    final_rows = result.get('values', [])
    old_value_string = '(not set)'
    if final_rows:
        for row in final_rows:
            for value in final_rows:
                old_value_string = value[0]

    # Now that we have the old value, try to update the new value.
    # If priority is blank, leave the level (high/medium/low) alone.
    if priority is not None:
        priority = priority.lower()
    priorityString = None
    if (resonance_int == 10):
        priorityString = '10/10'
    elif (priority == 'l') or (priority == 'low') or (priority is None and 'low' in old_value_string.lower()):
        priorityString = RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE.format(resonance_int)
    elif (priority == 'm') or (priority == 'medium') or (priority is None and 'medium' in old_value_string.lower()):
        priorityString = RESONANCE_MEDIUM_PRIORITY_VALUE_TEMPLATE.format(resonance_int)
    elif (priority == 'h') or (priority == 'high') or (priority is None and 'high' in old_value_string.lower()):
        priorityString = RESONANCE_HIGH_PRIORITY_VALUE_TEMPLATE.format(resonance_int)
    elif (priority is None):
        # Priority not specified, and old value doesn't have high/medium/low -> old value was blank, or old value was 10.
        # Default to low priority.
        priorityString = RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE.format(resonance_int)
    else:
        raise DiscordSafeException('Unknown priority value. Priority should be blank or one of "L", "low", "M", "medium", "H", "high"')

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
                'startRowIndex': unit_row-1, # inclusive
                'endRowIndex': unit_row, # exclusive
                'startColumnIndex': fromA1(esper_column_A1)-1, # inclusive
                'endColumnIndex': fromA1(esper_column_A1) # exclusive
            }
        }
    }
    allRequests = []
    allRequests.append(updateValueRequest)

    if comment:
        commentText = comment
        if comment == '<blank>': # Allow clearing the comment
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
                    'startRowIndex': unit_row-1, # inclusive
                    'endRowIndex': unit_row, # exclusive
                    'startColumnIndex': fromA1(esper_column_A1)-1, # inclusive
                    'endColumnIndex': fromA1(esper_column_A1) # exclusive
                }
            }
        }
        allRequests.append(updateCommentRequest)

    requestBody = {
        'requests': [allRequests]
    }
    # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
    spreadsheetApp.batchUpdate(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, body=requestBody).execute()
    return old_value_string, priorityString, pretty_unit_name, pretty_esper_name

# Generate a safe response for a message from discord, or None if no response is needed.
def getDiscordSafeResponse(message):
    if message.author == discord_client.user:
        return

    if not message.content:
        return

    if not message.content.startswith('!'):
        return

    from_name = message.author.display_name
    from_id = message.author.id
    from_discrim = message.author.discriminator

    match = RES_FETCH_SELF_PATTERN.match(message.content);
    if match:
        unit_name = match.group(1).strip()
        esper_name = match.group(2).strip()
        print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (from_name, from_discrim, from_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = readResonance(None, from_id, unit_name, esper_name)
        return '<@{0}>: {1}/{2} has resonance {3}'.format(from_id, pretty_unit_name, pretty_esper_name, resonance)

    match = RES_LIST_SELF_PATTERN.match(message.content);
    if match:
        target_name = match.group('target_name').strip()
        print('resonance list fetch from user %s#%s, for target %s' % (from_name, from_discrim, target_name))
        pretty_name, resonance_listing = readResonanceList(None, from_id, target_name)
        return '<@{0}>: resonance listing for {1}:\n{2}'.format(from_id, pretty_name, resonance_listing)

    match = RES_FETCH_OTHER_PATTERN.match(message.content);
    if match:
        target_user_name = match.group(1).strip()
        unit_name = match.group(2).strip()
        esper_name = match.group(3).strip()
        print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (from_name, from_discrim, target_user_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = readResonance(target_user_name, unit_name, esper_name)
        return '<@{0}>: for user {1}, {2}/{3} has resonance {4}'.format(from_id, target_user_name, pretty_unit_name, pretty_esper_name, resonance)

    match = RES_SET_PATTERN.match(message.content);
    if match:
        unit_name = match.group('unit').strip()
        esper_name = match.group('esper').strip()
        resonance_numeric_string = match.group('resonance_level').strip()
        priority = None
        if match.group('priority'): priority = match.group('priority').strip()
        comment = None
        if match.group('comment'): comment = match.group('comment').strip()
        print('resonance set from user %s#%s, for unit %s, for esper %s, to resonance %s, with priority %s, comment %s' % (from_name, from_discrim, unit_name, esper_name, resonance_numeric_string, priority, comment))
        old_resonance, new_resonance, pretty_unit_name, pretty_esper_name = setResonance(from_id, unit_name, esper_name, resonance_numeric_string, priority, comment)
        return '<@{0}>: {1}/{2} resonance has been set to {3} (was: {4})'.format(from_id, pretty_unit_name, pretty_esper_name, new_resonance, old_resonance)

    # Hidden utility command to look up the snowflake ID of your own user. This isn't secret or insecure,
    # but it's also not common, so it isn't listed in help.
    if message.content.startswith('!whoami'):
        return '<@{0}>: Your snowflake ID is {0}'.format(from_id, from_id)

    # Hidden utility command to look up the snowflake ID of a member. This isn't secret or insecure,
    # but it's also not common, so it isn't listed in help.
    match = WHOIS_PATTERN.match(message.content);
    if match:
        target_member_name = match.group(1).strip()
        members = message.guild.members
        for member in members:
            if (member.name == target_member_name):
                return '<@{0}>: the snowflake ID for {1} is {2}'.format(from_id, target_member_name, member.id)
        return '<@{0}>: no such member {1}'.format(from_id, target_member_name)

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
        left_or_right_of = admin_add_esper_match.group('left_or_right_of').strip()
        column = admin_add_esper_match.group('column').strip()
        print('esper add (sandbox mode={6}) from user {0}#{1}, for esper {2}, url {3}, position {4}, column {5}'.format(from_name, from_discrim, esper_name, esper_url, left_or_right_of, column, sandbox))
        addEsperColumn(from_id, esper_name, esper_url, left_or_right_of, column, sandbox)
        return '<@{0}>: Added esper {1}!'.format(from_id, esper_name)

    if message.content.startswith('!resonance'):
        return '<@{0}>: Invalid !resonance command. Use !help for more information.'.format(from_id)

    if message.content.startswith('!help'):
        return HELP.format(ESPER_RESONANCE_SPREADSHEET_ID)

if __name__ == "__main__":
    readConfig()
    discord_client = discord.Client()
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    # logger.setLevel(logging.DEBUG)
    # handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)

def getDiscordClient():
    return discord_client

@discord_client.event
async def on_ready():
    print('Bot logged in: {0.user}'.format(discord_client))

@discord_client.event
async def on_message(message):
    responseText = None
    try:
        responseText = getDiscordSafeResponse(message)
    except DiscordSafeException as safeException:
        responseText = safeException.message
    if responseText:
        fullTextToSend = maybeSplitMessageNicely(responseText)
        for chunk in fullTextToSend:
            await message.channel.send(chunk)

if __name__ == "__main__":
    discord_client.run(DISCORD_BOT_TOKEN)
