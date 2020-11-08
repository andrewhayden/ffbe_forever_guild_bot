"""A bot for managing War of the Visions guild information via Discord."""
from __future__ import print_function
from __future__ import annotations
from dataclasses import dataclass
import io
import logging
import pickle
# pylint: disable=unused-import
import pprint  # for pretty-printing JSON during debugging, etc
import json
import os.path
import re
from re import Match

import discord

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from PIL import Image

from worksheet_utils import WorksheetUtils
from vision_card_common import VisionCard
from vision_card_ocr_utils import VisionCardOcrUtils
from esper_resonance_manager import EsperResonanceManager
from wotv_bot_common import ExposableException

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

# The token of the Discord bot, needed to log into Discord.
DISCORD_BOT_TOKEN = None

# Maximum length of a Discord message. Messages longer than this need to be split up.
# The actual limit is 2000 characters but there seems to be some formatting inflation that takes place.
DISCORD_MESSAGE_LENGTH_LIMIT = 1000

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

`!xocr-debug`
> EXPERIMENTAL (might break!): Like !xocr, but the bot will attempt to send back to you the intermediate images it constructed while processing text. Warning: may eat a lot of your bandwidth.

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
EXPERIMENTAL_VISION_CARD_OCR_DEBUG_PATTERN = re.compile(r'^!xocr-debug$')

# (Hidden) Pattern for getting your own user ID out of Discord
WHOIS_PATTERN = re.compile(r'^!whois (?P<server_handle>.+)$')

ADMIN_HELP = '''
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

class DiscordSafeException(ExposableException):
    """An exception whose error text is safe to show in Discord.
    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        super(DiscordSafeException, self).__init__(message)
        self.message = message


def readConfig():
    """Reads the configuration file and bootstraps the application. Call this first."""
    # pylint: disable=global-statement
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


def maybeSplitMessageNicely(message_text):
    """Returns a list of message fragments, all under DISCORD_MESSAGE_LENGTH_LIMIT in size.

    If the given message is longer than DISCORD_MESSAGE_LENGTH_LIMIT, splits the message into as many
    chunks as necessary in order to stay under the limit for each message. Tries to respect newlines.
    If a line is too long, this method will fail.
    """
    if len(message_text) < DISCORD_MESSAGE_LENGTH_LIMIT:
        return [message_text]
    result = []
    buffer = ''
    lines = message_text.splitlines(keepends=True)
    for line in lines:
        if len(line) > DISCORD_MESSAGE_LENGTH_LIMIT:
            # There's a line with a single word too long to fit. Abort.
            raise DiscordSafeException('response too long')
        if (len(buffer) + len(line)) < DISCORD_MESSAGE_LENGTH_LIMIT:
            buffer += line
        else:
            result.append(buffer)
            buffer = line
    if len(buffer) > 0:
        result.append(buffer)
    return result


def openSpreadsheets():
    """Open the spreadsheet and return the the application interface object."""
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

@dataclass
class CommandContextInfo:
    """Context information for the command that is being executed."""
    from_name: str = None # Convenience
    from_id: str = None # Convenience
    from_discrim: str = None # Convenience
    original_message: str = None # For unusual use cases
    esper_resonance_manager: EsperResonanceManager = None
    command_match: Match = None

    def shallowCopy(self) -> CommandContextInfo:
        """Make a shallow copy of this object, containing only the from_name, from_id, from_discrim and original_message fields"""
        result = CommandContextInfo()
        result.from_name = self.from_name
        result.from_id = self.from_id
        result.from_name = self.from_name
        result.original_message = self.original_message
        return result

    def withEsperResonanceManager(self, esper_resonance_manager: EsperResonanceManager) -> CommandContextInfo:
        """Assign the specified esper resonance amnager and return a reference to this object."""
        self.esper_resonance_manager = esper_resonance_manager
        return self

    def withMatch(self, the_match: Match) -> CommandContextInfo:
        """Assign the specified match and return a reference to this object."""
        self.command_match = the_match
        return self

async def getDiscordSafeResponse(message):
    """Process the request and produce a response."""
    # Bail out early if anything looks insane.
    if message.author == discord_client.user:
        return (None, None)
    if not message.content:
        return (None, None)
    if not message.content.startswith('!'):
        return (None, None)
    for ignore_pattern in ALL_IGNORE_PATTERNS:
        if ignore_pattern.match(message.content):
            return (None, None)

    # Set up the context used in handling every possible command.
    # TODO: Clean up these fields that are not part of the CommandContextInfo object.
    from_name = message.author.display_name
    from_id = message.author.id
    from_discrim = message.author.discriminator
    context = CommandContextInfo()
    context.from_discrim = from_discrim
    context.from_id = from_id
    context.from_name = from_name
    context.original_message = message

    # TODO: Hold this reference longer after cleaning up the rest of the code, in an application context.
    esper_resonance_manager = EsperResonanceManager(
        ESPER_RESONANCE_SPREADSHEET_ID,
        SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID,
        ACCESS_CONTROL_SPREADSHEET_ID,
        openSpreadsheets())

    match = RES_FETCH_SELF_PATTERN.match(message.content.lower())
    if match:
        return handleTargetedResonanceLookupForSelf(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

    match = RES_LIST_SELF_PATTERN.match(message.content.lower())
    if match:
        return handleGeneralResonanceLookupForSelf(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

    match = RES_FETCH_OTHER_PATTERN.match(message.content.lower())
    if match:
        return handleTargetedResonanceLookupForOtherUser(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

    match = RES_SET_PATTERN.match(message.content.lower())
    if match:
        return handleResonanceSet(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

    # Hidden utility command to look up the snowflake ID of your own user. This isn't secret or insecure, but it's also not common, so it isn't listed in help.
    if message.content.lower().startswith('!whoami'):
        return handleWhoAmI(context)

    # Hidden utility command to look up the snowflake ID of a member. This isn't secret or insecure, but it's also not common, so it isn't listed in help.
    match = WHOIS_PATTERN.match(message.content.lower())
    if match:
        return handleWhoIs(context.shallowCopy().withMatch(match))

    if ADMIN_ADD_ESPER_PATTERN.match(message.content) or SANDBOX_ADMIN_ADD_ESPER_PATTERN.match(message.content):
        return handleAdminAddEsper(context.shallowCopy().withEsperResonanceManager(esper_resonance_manager))

    if ADMIN_ADD_UNIT_PATTERN.match(message.content) or SANDBOX_ADMIN_ADD_UNIT_PATTERN.match(message.content):
        return handleAdminAddUnit(context.shallowCopy().withEsperResonanceManager(esper_resonance_manager))

    if message.content.lower().startswith('!resonance'):
        responseText = '<@{0}>: Invalid !resonance command. Use !help for more information.'.format(from_id)
        return (responseText, None)

    if EXPERIMENTAL_VISION_CARD_OCR_PATTERN.match(message.content.lower()) or EXPERIMENTAL_VISION_CARD_OCR_DEBUG_PATTERN.match(message.content.lower()):
        return await handleVisionCardOcr(context.shallowCopy())

    if message.content.lower().startswith('!help'):
        responseText = HELP.format(ESPER_RESONANCE_SPREADSHEET_ID)
        return (responseText, None)

    if message.content.lower().startswith('!admin-help'):
        responseText = ADMIN_HELP.format(ESPER_RESONANCE_SPREADSHEET_ID, SANDBOX_ESPER_RESONANCE_SPREADSHEET_ID)
        return (responseText, None)

    return ('<@{0}>: Invalid or unknown command. Use !help to see all supported commands and !admin-help to see special admin commands. '\
            'Please do this via a direct message to the bot, to avoid spamming the channel.'.format(from_id), None)

def handleTargetedResonanceLookupForSelf(context: CommandContextInfo) -> (str, str):
    """Handle !res command for self-lookup of a specific (unit, esper) tuple."""
    unit_name = context.command_match.group(1).strip()
    esper_name = context.command_match.group(2).strip()
    print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (
        context.from_name, context.from_discrim, context.from_name, unit_name, esper_name))
    resonance, pretty_unit_name, pretty_esper_name = context.esper_resonance_manager.readResonance(None, context.from_id, unit_name, esper_name)
    responseText = '<@{0}>: {1}/{2} has resonance {3}'.format(context.from_id, pretty_unit_name, pretty_esper_name, resonance)
    return (responseText, None)

def handleTargetedResonanceLookupForOtherUser(context: CommandContextInfo) -> (str, str):
    """Handle !res command for lookup of a specific (unit, esper) tuple for a different user."""
    target_user_name = context.command_match.group(1).strip()
    unit_name = context.command_match.group(2).strip()
    esper_name = context.command_match.group(3).strip()
    print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (
        context.from_name, context.from_discrim, target_user_name, unit_name, esper_name))
    resonance, pretty_unit_name, pretty_esper_name = context.esper_resonance_manager.readResonance(target_user_name, None, unit_name, esper_name)
    responseText = '<@{0}>: for user {1}, {2}/{3} has resonance {4}'.format(context.from_id, target_user_name, pretty_unit_name, pretty_esper_name, resonance)
    return (responseText, None)

def handleGeneralResonanceLookupForSelf(context: CommandContextInfo) -> (str, str):
    """Handle !res command for self-lookup of all resonance for a given unit or esper."""
    target_name = context.command_match.group('target_name').strip()
    print('resonance list fetch from user %s#%s, for target %s' % (context.from_name, context.from_discrim, target_name))
    pretty_name, resonance_listing = context.esper_resonance_manager.readResonanceList(None, context.from_id, target_name)
    responseText = '<@{0}>: resonance listing for {1}:\n{2}'.format(context.from_id, pretty_name, resonance_listing)
    return (responseText, None)

def handleResonanceSet(context: CommandContextInfo) -> (str, str):
    """Handle !res-set command to set resonance for a specific unit and esper tuple."""
    unit_name = context.command_match.group('unit').strip()
    esper_name = context.command_match.group('esper').strip()
    resonance_numeric_string = context.command_match.group('resonance_level').strip()
    priority = None
    if context.command_match.group('priority'):
        priority = context.command_match.group('priority').strip()
    comment = None
    if context.command_match.group('comment'):
        comment = context.command_match.group('comment').strip()
    print('resonance set from user %s#%s, for unit %s, for esper %s, to resonance %s, with priority %s, comment %s' % (
        context.from_name, context.from_discrim, unit_name, esper_name, resonance_numeric_string, priority, comment))
    old_resonance, new_resonance, pretty_unit_name, pretty_esper_name = context.esper_resonance_manager.setResonance(
        context.from_id, unit_name, esper_name, resonance_numeric_string, priority, comment)
    responseText = '<@{0}>: {1}/{2} resonance has been set to {3} (was: {4})'.format(
        context.from_id, pretty_unit_name, pretty_esper_name, new_resonance, old_resonance)
    if (resonance_numeric_string and int(resonance_numeric_string) == 10):
        # reaction = '\U0001F4AA' # CLDR: flexed biceps
        reaction = '\U0001F3C6'  # CLDR: trophy
    else:
        reaction = '\U00002705'  # CLDR: check mark button
    return (responseText, reaction)

def handleWhoAmI(context: CommandContextInfo) -> (str, str):
    """Handle !whoami command to fetch your own snowflake ID."""
    responseText = '<@{id}>: Your snowflake ID is {id}'.format(id=context.from_id)
    return (responseText, None)

def handleWhoIs(context: CommandContextInfo) -> (str, str):
    """Handle !whois command to fetch the snowflake ID for a given user."""
    original_match = WHOIS_PATTERN.match(context.original_message.content) # Fetch original-case name
    target_member_name = original_match.group('server_handle').strip()
    members = context.original_message.guild.members
    for member in members:
        if member.name == target_member_name:
            responseText = '<@{0}>: the snowflake ID for {1} is {2}'.format(context.from_id, target_member_name, member.id)
            return (responseText, None)
    responseText = '<@{0}>: no such member {1}'.format(context.from_id, target_member_name)
    return (responseText, None)

def handleAdminAddEsper(context: CommandContextInfo) -> (str, str):
    """Handle !admin-add-esper and !sandbox-admin-add-esper commands to add a new esper to the resonance tracker."""
    sandbox = True
    match = ADMIN_ADD_ESPER_PATTERN.match(context.original_message.content)
    if match:
        sandbox = False
    else:
        match = SANDBOX_ADMIN_ADD_ESPER_PATTERN.match(context.original_message.content)
    esper_name = match.group('name').strip()
    esper_url = match.group('url').strip()
    left_or_right_of = match.group('left_or_right_of').strip()
    column = match.group('column').strip()
    print('esper add (sandbox mode={6}) from user {0}#{1}, for esper {2}, url {3}, position {4}, column {5}'.format(
        context.from_name, context.from_discrim, esper_name, esper_url, left_or_right_of, column, sandbox))
    context.esper_resonance_manager.addEsperColumn(context.from_id, esper_name, esper_url, left_or_right_of, column, sandbox)
    responseText = '<@{0}>: Added esper {1}!'.format(context.from_id, esper_name)
    return (responseText, None)

def handleAdminAddUnit(context: CommandContextInfo) -> (str, str):
    """Handle !admin-add-unit and !sandbox-admin-add-unit commands to add a new unit to the resonance tracker."""
    sandbox = True
    match = ADMIN_ADD_UNIT_PATTERN.match(context.original_message.content)
    if match:
        sandbox = False
    else:
        match = SANDBOX_ADMIN_ADD_UNIT_PATTERN.match(context.original_message.content)
    unit_name = match.group('name').strip()
    unit_url = match.group('url').strip()
    above_or_below = match.group('above_or_below').strip()
    row1Based = match.group('row1Based').strip()
    print('unit add (sandbox mode={6}) from user {0}#{1}, for unit {2}, url {3}, position {4}, row {5}'.format(
        context.from_name, context.from_discrim, unit_name, unit_url, above_or_below, row1Based, sandbox))
    context.esper_resonance_manager.addUnitRow(context.from_id, unit_name, unit_url, above_or_below, row1Based, sandbox)
    responseText = '<@{0}>: Added unit {1}!'.format(context.from_id, unit_name)
    return (responseText, None)

async def handleVisionCardOcr(context: CommandContextInfo) -> (str, str):
    """Handle !xocr and !xocr-debug commands to perform OCR on a Vision Card."""
    is_debug = False
    if EXPERIMENTAL_VISION_CARD_OCR_DEBUG_PATTERN.match(context.original_message.content.lower()):
        is_debug = True
    # Try to extract text from a vision card screenshot that is sent as an attachment to this message.
    url = context.original_message.attachments[0].url
    print('Vision Card OCR request from user %s#%s, for url %s' % (context.from_name, context.from_discrim, url))
    screenshot = VisionCardOcrUtils.downloadScreenshotFromUrl(url)
    vision_card = VisionCardOcrUtils.extractVisionCardFromScreenshot(screenshot, is_debug)
    if is_debug:
        combined_image = VisionCardOcrUtils.mergeDebugImages(vision_card)
        buffer = io.BytesIO()
        combined_image.save(buffer, format='PNG')
        buffer.seek(0)
        temp_file = discord.File(buffer, filename='Intermediate OCR Debug.png')
        await context.original_message.channel.send('Intermediate OCR Debug. Raw info text:\n```{0}```\nRaw stats text: ```{1}```'.format(
            vision_card.info_debug_raw_text,
            vision_card.stats_debug_raw_text), file=temp_file)
    if vision_card.successfully_extracted is True:
        responseText = '<@{0}>: {1}'.format(context.from_id, vision_card.prettyPrint())
    else:
        responseText = '<@{0}>: Vision card extraction has failed. You may try again with !xocr-debug for a clue about what has gone wrong'.format(
            context.from_id)
    return (responseText, None)

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
    """Return the main discord client object (a singleton)"""
    return discord_client


@discord_client.event
async def on_ready():
    """Hook automatically called by the discord client when login is complete."""
    print('Bot logged in: {0.user}'.format(discord_client))


@discord_client.event
async def on_message(message):
    """Hook automatically called by the discord client when a message is received."""
    responseText = None
    reaction = None
    try:
        responseText, reaction = await getDiscordSafeResponse(message)
    except ExposableException as safeException:
        responseText = safeException.message
    if responseText:
        fullTextToSend = maybeSplitMessageNicely(responseText)
        for chunk in fullTextToSend:
            await message.channel.send(chunk)
    if reaction:
        await message.add_reaction(reaction)

if __name__ == "__main__":
    discord_client.run(DISCORD_BOT_TOKEN)
