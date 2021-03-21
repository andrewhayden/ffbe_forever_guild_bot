"""A bot for managing War of the Visions guild information via Discord."""
from __future__ import print_function
from __future__ import annotations
import json
import logging
import discord

from data_files import DataFiles
from reminders import Reminders
from wotv_bot_common import ExposableException
from wotv_bot import WotvBotConfig, WotvBot
from worksheet_utils import WorksheetUtils

# Where the main config file for the bot lives.
CONFIG_FILE_PATH = 'bot_config.json'

# Where to persist reminders
REMINDERS_DB_PATH = '.reminders.sql'

# Maximum length of a Discord message. Messages longer than this need to be split up.
# The actual limit is 2000 characters but there seems to be some formatting inflation that takes place.
DISCORD_MESSAGE_LENGTH_LIMIT = 1000

class GlobalConfig:
    """Config object for the entire application."""
    def __init__(self, wotv_bot_config: WotvBotConfig, discord_bot_token: str):
        self.wotv_bot_config = wotv_bot_config
        self.discord_bot_token = discord_bot_token

def readConfig(file_path) -> GlobalConfig:
    """Reads the configuration file and returns a configuration object containing all the important information within."""
    wotv_bot_config = WotvBotConfig()
    discord_bot_token = None
    with open(file_path) as config_file:
        data = json.load(config_file)
        wotv_bot_config.access_control_spreadsheet_id = data['access_control_spreadsheet_id']
        wotv_bot_config.esper_resonance_spreadsheet_id = data['esper_resonance_spreadsheet_id']
        wotv_bot_config.vision_card_spreadsheet_id = data['vision_card_spreadsheet_id']
        wotv_bot_config.sandbox_esper_resonance_spreadsheet_id = data['sandbox_esper_resonance_spreadsheet_id']
        wotv_bot_config.data_files = DataFiles.parseDataDump(data['data_dump_root_path'])
        discord_bot_token = data['discord_bot_token']
    return GlobalConfig(wotv_bot_config, discord_bot_token)

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
    global_config = readConfig(CONFIG_FILE_PATH)
    global_config.wotv_bot_config.discord_client = discord_client
    global_config.wotv_bot_config.reminders = Reminders(REMINDERS_DB_PATH)
    global_config.wotv_bot_config.spreadsheet_app = WorksheetUtils.getSpreadsheetsAppClient()
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
    global_config.wotv_bot_config.reminders.start(discord_client.loop)

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
