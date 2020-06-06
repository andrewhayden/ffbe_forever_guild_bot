from __future__ import print_function
import discord
import pickle
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

# The token of the Discord bot, needed to log into Discord.
DISCORD_BOT_TOKEN = None

# -----------------------------------------------------------------------------
# Command Regexes & Help
# -----------------------------------------------------------------------------
HELP = '''```FFBEForever Guild Bot Help
!resonance unit-name/esper-name                                get **your own** resonance for the named unit and esper.
!resonance-lookup discord-username unit-name/esper-name        get **someone else's** resonance for the named unit and esper.

Unit and esper names need not be full, but the first match will be returned. For example you don't have to type out
"Sterne Leonis" and "Tetra Sylphid": you can just shorthand it as "stern/tetra", or even "st/te".
```'''

# !res get [unit]/[esper]
RES_FETCH_SELF_PATTERN = re.compile("^!resonance (.+)/(.+)$")

# !res get [user] [unit]/[esper]
RES_FETCH_OTHER_PATTERN = re.compile("^!resonance-lookup (\S+) (.+)/(.+)$")

class DiscordSafeException(Exception):
    """An exception whose error text is safe to show in Discord.
    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message


# Reads the configuration file and bootstraps the application. Call this first.
def readConfig():
    global ESPER_RESONANCE_SPREADSHEET_ID
    global DISCORD_BOT_TOKEN
    with open(CONFIG_FILE_PATH) as config_file:
        data = json.load(config_file)
        ESPER_RESONANCE_SPREADSHEET_ID = data['esper_resonance_spreadsheet_id']
        print('spreadsheet id: %s' % (ESPER_RESONANCE_SPREADSHEET_ID))
        DISCORD_BOT_TOKEN = data['discord_bot_token']
        if DISCORD_BOT_TOKEN: print('discord bot token: [redacted, but read successfully]')


# Convert an integer value to "A1 Notation", i.e. the column name in a spreadsheet. Max value 26*26.
def toA1(intValue):
    if (intValue > 26*26): raise Exception("number too large")
    if (intValue <= 26): return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[intValue - 1]
    bigPart = intValue // 26
    remainder = intValue - (bigPart * 26)
    return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[bigPart - 1] + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[intValue - 1]

# Normalize a name, lowercasing it and replacing spaces with hyphens.
def normalizeName(fancy_name):
    return fancy_name.strip().lower().replace(" ", "-")

# Open the spreadsheet and return a tuple of the service object and the spreadsheet.
def openResonanceSpreadsheet():
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
    sheet = service.spreadsheets()
    return (service, sheet)

# Return the column (A1 notation value) and fancy-printed name of the esper for the given user's esper.
# If the esper can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.
def findEsperColumn(sheet, user_name, esper_name):
    # Read the esper names row. Esper names are on row 2.
    range_name = user_name + '!2:2'
    esper_name_rows = None
    esper_name = normalizeName(esper_name)
    try:
        values = sheet.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
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
def findUnitRow(sheet, user_name, unit_name):
    # Unit names are on column B.
    range_name = user_name + '!B:B'
    unit_name_rows = None
    unit_name = normalizeName(unit_name)
    try:
        values = sheet.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
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


# Read and return the esper resonance, pretty unit name, and pretty esper name for the given (unit, esper) tuple, for the given user.
def readResonance(user_name, unit_name, esper_name):
    service, sheet = openResonanceSpreadsheet()
    esper_column_A1, pretty_esper_name = findEsperColumn(sheet, user_name, esper_name)
    unit_row, pretty_unit_name = findUnitRow(sheet, user_name, unit_name)

    # We have the location. Get the value!
    range_name = user_name + '!' + esper_column_A1 + str(unit_row) + ':' + esper_column_A1 + str(unit_row)
    result = sheet.values().get(spreadsheetId=ESPER_RESONANCE_SPREADSHEET_ID, range=range_name).execute()
    final_rows = result.get('values', [])

    if not final_rows:
        raise DiscordSafeException('{0} is not tracking any resonance for esper {1} on unit {2}'.format(user_name, pretty_esper_name, pretty_unit_name))

    for row in final_rows:
        for value in final_rows:
            return value[0], pretty_unit_name, pretty_esper_name

# Generate a safe response for a message from discord, or None if no response is needed.
def getDiscordSafeResponse(message):
    if message.author == discord_client.user:
        return

    if not message.content:
        return

    if not message.content.startswith('!'):
        return

    match = RES_FETCH_SELF_PATTERN.match(message.content);
    if match:
        target_user_name = message.author.display_name
        from_id = message.author.id
        unit_name = match.group(1).strip()
        esper_name = match.group(2).strip()
        print('resonance fetch from user %s, for user %s, for unit %s, or esper %s' % (target_user_name, target_user_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = readResonance(target_user_name, unit_name, esper_name)
        return '<@{0}>: ${1}/${2} has resonance {3}'.format(from_id, pretty_unit_name, pretty_esper_name, resonance)

    match = RES_FETCH_OTHER_PATTERN.match(message.content);
    if match:
        from_name = message.author.display_name
        from_id = message.author.id
        target_user_name = match.group(1).strip()
        unit_name = match.group(2).strip()
        esper_name = match.group(3).strip()
        print('resonance fetch from user %s, for user %s, for unit %s, for esper %s' % (from_name, target_user_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = readResonance(target_user_name, unit_name, esper_name)
        return '<@{0}>: for user {1}, {2}/{3} has resonance {4}'.format(from_id, target_user_name, pretty_unit_name, pretty_esper_name, resonance)

    if message.content.startswith('!help'):
        return HELP

if __name__ == "__main__":
    readConfig()
    discord_client = discord.Client()

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
        await message.channel.send(responseText)

if __name__ == "__main__":
    discord_client.run(DISCORD_BOT_TOKEN)
