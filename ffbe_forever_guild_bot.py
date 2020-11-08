"""A bot for managing War of the Visions guild information via Discord."""
from __future__ import print_function
from __future__ import annotations
import json
import logging
import pickle
import os.path

import discord

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from wotv_bot_common import ExposableException
from wotv_bot import WotvBotConfig, WotvBot

# Where the main config file for the bot lives.
CONFIG_FILE_PATH = 'bot_config.json'

# Where the token is pickled to, after approving the bot for access to the Google account where the data is to be maintained.
GOOGLE_TOKEN_PICKLE_PATH = 'google_token.pickle'

# The path to the credentials for the bot, downloaded from the Google Developers Console.
GOOGLE_CREDENTIALS_PATH = 'google_credentials.json'

# Scopes required for the bot to maintain data
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Maximum length of a Discord message. Messages longer than this need to be split up.
# The actual limit is 2000 characters but there seems to be some formatting inflation that takes place.
DISCORD_MESSAGE_LENGTH_LIMIT = 1000

class GlobalConfig:
    """Config object for the entire application."""
    def __init__(self, wotv_bot_config: WotvBotConfig, discord_bot_token: str):
        self.wotv_bot_config = wotv_bot_config
        self.discord_bot_token = discord_bot_token

def readConfig() -> GlobalConfig:
    """Reads the configuration file and returns a configuration object containing all the important information within."""
    wotv_bot_config = WotvBotConfig()
    discord_bot_token = None
    with open(CONFIG_FILE_PATH) as config_file:
        data = json.load(config_file)
        wotv_bot_config.access_control_spreadsheet_id = data['access_control_spreadsheet_id']
        wotv_bot_config.esper_resonance_spreadsheet_id = data['esper_resonance_spreadsheet_id']
        wotv_bot_config.sandbox_esper_resonance_spreadsheet_id = data['sandbox_esper_resonance_spreadsheet_id']
        discord_bot_token = data['discord_bot_token']
    return GlobalConfig(wotv_bot_config, discord_bot_token)

def getSpreadsheetsAppClient():
    """Creates, connects and returns an active Google Sheeps application connection."""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(GOOGLE_TOKEN_PICKLE_PATH):
        with open(GOOGLE_TOKEN_PICKLE_PATH, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('google_credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(GOOGLE_TOKEN_PICKLE_PATH, 'wb') as token:
            pickle.dump(creds, token)
    service = build('sheets', 'v4', credentials=creds)
    spreadsheetApp = service.spreadsheets() # pylint: disable=no-member
    return spreadsheetApp

def toDiscordMessages(message_text):
    """Returns a list of messages, all under DISCORD_MESSAGE_LENGTH_LIMIT in size.

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
            raise ExposableException('response too long')
        if (len(buffer) + len(line)) < DISCORD_MESSAGE_LENGTH_LIMIT:
            buffer += line
        else:
            result.append(buffer)
            buffer = line
    if len(buffer) > 0:
        result.append(buffer)
    return result

if __name__ == "__main__":
    discord_client = discord.Client()
    global_config = readConfig()
    global_config.wotv_bot_config.discord_client = discord_client
    global_config.wotv_bot_config.spreadsheet_app = getSpreadsheetsAppClient()
    wotv_bot = WotvBot(global_config.wotv_bot_config)
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    # logger.setLevel(logging.DEBUG)
    # handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)

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
        responseText, reaction = await wotv_bot.handleMessage(message)
    except ExposableException as safeException:
        responseText = safeException.message
    if responseText:
        allMessagesToSend = toDiscordMessages(responseText)
        for oneMessageToSend in allMessagesToSend:
            await message.channel.send(oneMessageToSend)
    if reaction:
        await message.add_reaction(reaction)

# Finally, the start method.
if __name__ == "__main__":
    discord_client.run(global_config.discord_bot_token)
