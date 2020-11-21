"""Integration tests for the FFBEForever Guild Bot"""
import asyncio
import json
import logging
import types

from admin_utils import AdminUtils
from wotv_bot import WotvBot, WotvBotConfig
from worksheet_utils import WorksheetUtils

class WotvBotIntegrationTests:
    """Integration tests for the FFBEForever Guild Bot"""

    # Where the main config file for the bot lives.
    CONFIG_FILE_PATH = 'integration_test_config.json'

    # Name of the default tab in the Esper Resonance spreadsheet, from which all other tabs are cloned.
    RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME = 'Home'

    # The bot's own display name, snowflake ID, and discriminator
    BOT_DISPLAY_NAME = 'IntegTestBot'
    BOT_SNOWFLAKE_ID = '123456789'
    BOT_DISCRIMINATOR = '#1234'

    # Data for a normal (non-admin) integration test user
    TEST_USER_DISPLAY_NAME = 'IntegTestUser'
    TEST_USER_SNOWFLAKE_ID = '987654321'
    TEST_USER_DISCRIMINATOR = '#4321'

    # Data for an admin integration test user
    TEST_ADMIN_USER_DISPLAY_NAME = 'IntegTestAdminUser'
    TEST_ADMIN_USER_SNOWFLAKE_ID = '314159'
    TEST_ADMIN_USER_DISCRIMINATOR = '#314'

    # A test esper
    TEST_ESPER1_NAME = 'TestEsper1'
    TEST_ESPER1_URL = 'http://www.example.com'

    # Another test esper
    TEST_ESPER2_NAME = 'TestEsper2'
    TEST_ESPER2_URL = 'http://www.example.com/2'

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
            WotvBotIntegrationTests.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME)

    def resetAdmin(self):
        """Reset the administrative spreadsheet with a blank sheet."""
        WotvBotIntegrationTests.resetSpreadsheet(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            AdminUtils.USERS_TAB_NAME)
        admin_spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.access_control_spreadsheet_id).execute()
        sheet_id = None
        for sheet in admin_spreadsheet['sheets']:
            sheet_title = sheet['properties']['title']
            if sheet_title == AdminUtils.USERS_TAB_NAME:
                sheet_id = sheet['properties']['sheetId']
                break
        if sheet_id is None:
            raise Exception('Internal error: cannot find user sheet in admin spreadsheet')

        all_requests = []
        # Header row
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 1, 'A', 'ID'))
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 1, 'B', 'Nickname'))
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 1, 'C', 'Admin?'))
        # Regular user
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 2, 'A', self.TEST_USER_SNOWFLAKE_ID))
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 2, 'B', self.TEST_USER_DISPLAY_NAME))
        # Admin user
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 3, 'A', self.TEST_ADMIN_USER_SNOWFLAKE_ID))
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 3, 'B', self.TEST_ADMIN_USER_DISPLAY_NAME))
        all_requests.append(WorksheetUtils.generateRequestToSetCellText(sheet_id, 3, 'C', 'Admin'))
        requestBody = {
            'requests': [all_requests]
        }
        self.wotv_bot_config.spreadsheet_app.batchUpdate(spreadsheetId=self.wotv_bot_config.access_control_spreadsheet_id, body=requestBody).execute()

    def makeMessage(self, message_text: str):
        """Construct a mock message object to send to the bot."""
        result = types.SimpleNamespace()
        result.author = types.SimpleNamespace()
        result.author.display_name = WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME
        result.author.id = WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID
        result.author.discriminator = WotvBotIntegrationTests.TEST_USER_DISCRIMINATOR
        result.content = message_text
        return result

    def makeAdminMessage(self, message_text: str):
        """Construct a mock message object to send to the bot."""
        result = types.SimpleNamespace()
        result.author = types.SimpleNamespace()
        result.author.display_name = WotvBotIntegrationTests.TEST_ADMIN_USER_DISPLAY_NAME
        result.author.id = WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID
        result.author.discriminator = WotvBotIntegrationTests.TEST_ADMIN_USER_DISCRIMINATOR
        result.content = message_text
        return result

    @staticmethod
    def assertEqual(expected, actual):
        """Assert that the two values are equal or fail with a helpful message"""
        assert actual == expected, 'expected "' + str(expected) + '", got "' + str(actual) + '"'

    async def testWhoAmI(self): # pylint: disable=missing-function-docstring
        wotv_bot = WotvBot(self.wotv_bot_config)
        message_text = '!whoami'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Your snowflake ID is ' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID
        self.assertEqual(expected_text, response_text)
        assert reaction is None

    async def testAdminAddEsper_AsAdmin(self): # pylint: disable=missing-function-docstring
        self.resetEsperResonance()
        wotv_bot = WotvBot(self.wotv_bot_config)
        # Add one esper to a blank sheet
        message_text = '!admin-add-esper ' + self.TEST_ESPER1_NAME + '|' + self.TEST_ESPER1_URL + '|right-of|C'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID + '>: Added esper ' + WotvBotIntegrationTests.TEST_ESPER1_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (column_string, cell_value) = WorksheetUtils.fuzzyFindColumn(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME, '"' + WotvBotIntegrationTests.TEST_ESPER1_NAME +'"', 2)
        self.assertEqual('D', column_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_ESPER1_NAME, cell_value)

        # Add another esper and make sure it pushes the previously-added one to the right.
        message_text = '!admin-add-esper ' + self.TEST_ESPER2_NAME + '|' + self.TEST_ESPER2_URL + '|left-of|D'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID + '>: Added esper ' + WotvBotIntegrationTests.TEST_ESPER2_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (column_string, cell_value) = WorksheetUtils.fuzzyFindColumn(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME, '"' + WotvBotIntegrationTests.TEST_ESPER2_NAME +'"', 2)
        self.assertEqual('D', column_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_ESPER2_NAME, cell_value)

        # Test that first esper is present and was pushed right.
        (column_string, cell_value) = WorksheetUtils.fuzzyFindColumn(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME, '"' + WotvBotIntegrationTests.TEST_ESPER1_NAME +'"', 2)
        self.assertEqual('E', column_string)
        self.assertEqual(WotvBotIntegrationTests.TEST_ESPER1_NAME, cell_value)

        # Now ensure that the original esper is still there and still
    async def runAllTests(self):
        """Run all tests in the integration test suite."""
        self.resetEsperResonance()
        self.resetAdmin()
        await self.testWhoAmI()
        await self.testAdminAddEsper_AsAdmin()
        print('Tests passed!')

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
