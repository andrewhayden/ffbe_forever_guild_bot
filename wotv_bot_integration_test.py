"""Integration tests for the FFBEForever Guild Bot"""
import asyncio
import json
import logging
import types

from wotv_bot import WotvBot, WotvBotConfig
from worksheet_utils import WorksheetUtils

class WotvBotIntegrationTests:
    """Integration tests for the FFBEForever Guild Bot"""

    # Where the main config file for the bot lives.
    CONFIG_FILE_PATH = 'integration_test_config.json'

    # The bot's own display name, snowflake ID, and discriminator
    BOT_DISPLAY_NAME = 'IntegTestBot'
    BOT_SNOWFLAKE_ID = '123456789'
    BOT_DISCRIMINATOR = '#1234'

    # Name of the integration test user - discord, sheets, etc.
    TEST_USER_DISPLAY_NAME = 'IntegTestUser'
    TEST_USER_SNOWFLAKE_ID = '987654321'
    TEST_USER_DISCRIMINATOR = '#4321'

    """An instance of the bot, configured to manage specific spreadsheets and using Discord and Google credentials."""
    def __init__(self, wotv_bot_config: WotvBotConfig):
        self.wotv_bot_config = wotv_bot_config

    @staticmethod
    def resetSpreadsheet(spreadsheet_app, spreadsheet_id, sheet_title: str = 'Sheet1'):
        """Delete all individual sheets from a given spreadsheet and create a baseline with a single, empty sheet.

        Basically this is equivalent to deleting the entire spreadsheet and creating a brand new, empty spreadsheet
        with a single sheet of empty cells. You can optionally specify the name of the new sheet to be created.

        :param spreadsheet_app: The application object for accessing Google Sheets
        :param spreadsheet: the spreadsheet to remove all sheets from
        :param sheet_title: the title to assign to the new sheet, defaults to 'Sheet1' if not set.
        """
        spreadsheet = spreadsheet_app.get(spreadsheetId=spreadsheet_id).execute()
        all_requests = []
        # Generate request to add the new sheet. This has to come first, so that we can delete all the other sheets
        # without raising an answer (there has to be at least one sheet in the spreadsheet at all times; adding the
        # new one first takes care of that).
        temp_sheet_title = 'temp_sheet_placeholder'
        all_requests.append({
            'addSheet': {
                'properties': {
                    'title': temp_sheet_title
                }
            }
        })
        # Generate requests to delete every sheet that already exists.
        for sheet in spreadsheet['sheets']:
            sheetId = sheet['properties']['sheetId']
            all_requests.append({
                'deleteSheet': {
                    'sheetId': sheetId,
                }
            })
        requestBody = {
            'requests': [all_requests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        spreadsheet_app.batchUpdate(spreadsheetId=spreadsheet_id, body=requestBody).execute()
        # Rename the temp sheet
        spreadsheet = spreadsheet_app.get(spreadsheetId=spreadsheet_id).execute()
        sheet = spreadsheet['sheets'][0]
        sheet_id = sheet['properties']['sheetId']
        all_requests = []
        all_requests.append({
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'title': sheet_title
                },
                'fields': 'title'
            }
        })
        requestBody = {
            'requests': [all_requests]
        }
        spreadsheet_app.batchUpdate(spreadsheetId=spreadsheet_id, body=requestBody).execute()

    @staticmethod
    def readConfig(file_path) -> WotvBotConfig:
        """Reads the configuration file and returns a configuration object containing all the important information within."""
        wotv_bot_config = WotvBotConfig()
        with open(file_path) as config_file:
            data = json.load(config_file)
            wotv_bot_config.access_control_spreadsheet_id = data['access_control_spreadsheet_id']
            wotv_bot_config.esper_resonance_spreadsheet_id = data['esper_resonance_spreadsheet_id']
            wotv_bot_config.sandbox_esper_resonance_spreadsheet_id = data['sandbox_esper_resonance_spreadsheet_id']
        return wotv_bot_config

    def resetEsperResonance(self):
        """Reset the esper resonance spreadsheet with a blank sheet."""
        WotvBotIntegrationTests.resetSpreadsheet(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME)

    def makeMessage(self, message_text: str):
        """Construct a mock message object to send to the bot."""
        result = types.SimpleNamespace()
        result.author = types.SimpleNamespace()
        result.author.display_name = WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME
        result.author.id = WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID
        result.author.discriminator = WotvBotIntegrationTests.TEST_USER_DISCRIMINATOR
        result.content = message_text
        return result

    async def runAllTests(self):
        """Run all tests in the integration test suite."""
        self.resetEsperResonance()
        wotv_bot = WotvBot(self.wotv_bot_config)

        # Test !whoami
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage('!whoami'))
        print(response_text)
        assert (response_text == '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID
            + '>: Your snowflake ID is ' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID)
        assert reaction is None


if __name__ == "__main__":
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    _config = WotvBotIntegrationTests.readConfig(WotvBotIntegrationTests.CONFIG_FILE_PATH)
    print('Integration test config loaded: ${0}'.format(_config))
    _config.discord_client = types.SimpleNamespace()
    _config.discord_client.user = types.SimpleNamespace()
    _config.discord_client.user.display_name = WotvBotIntegrationTests.BOT_DISPLAY_NAME
    _config.discord_client.user.id = WotvBotIntegrationTests.BOT_SNOWFLAKE_ID
    _config.discord_client.user.discriminator = WotvBotIntegrationTests.BOT_DISCRIMINATOR
    _config.spreadsheet_app = WorksheetUtils.getSpreadsheetsAppClient()
    suite = WotvBotIntegrationTests(_config)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(suite.runAllTests())
    loop.close()
