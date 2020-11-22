"""Integration tests for the FFBEForever Guild Bot"""
import asyncio
import json
import logging
import time
import types

from admin_utils import AdminUtils
from esper_resonance_manager import EsperResonanceManager
from wotv_bot import WotvBot, WotvBotConfig
from worksheet_utils import WorksheetUtils
from wotv_bot_common import ExposableException

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

    # A test unit
    TEST_UNIT1_NAME = 'TestUnit1'
    TEST_UNIT1_URL = 'http://www.example.com/unit1'

    # Another test unit
    TEST_UNIT2_NAME = 'TestUnit2'
    TEST_UNIT2_URL = 'http://www.example.com/unit2'

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

    async def testCommand_WhoAmI(self): # pylint: disable=missing-function-docstring
        wotv_bot = WotvBot(self.wotv_bot_config)
        message_text = '!whoami'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Your snowflake ID is ' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID
        self.assertEqual(expected_text, response_text)
        assert reaction is None

    async def testCommand_AdminAddEsper_AsAdmin(self): # pylint: disable=missing-function-docstring
        self.resetAdmin()
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
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_ESPER1_NAME +'"', 2)
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
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_ESPER2_NAME +'"', 2)
        self.assertEqual('D', column_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_ESPER2_NAME, cell_value)

        # Test that first esper is present and was pushed right.
        (column_string, cell_value) = WorksheetUtils.fuzzyFindColumn(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_ESPER1_NAME +'"', 2)
        self.assertEqual('E', column_string)
        self.assertEqual(WotvBotIntegrationTests.TEST_ESPER1_NAME, cell_value)

    async def testCommand_AdminAddUnit_AsAdmin(self): # pylint: disable=missing-function-docstring
        self.resetAdmin()
        self.resetEsperResonance()
        wotv_bot = WotvBot(self.wotv_bot_config)
        # Add one unit to a blank sheet
        message_text = '!admin-add-unit ' + self.TEST_UNIT1_NAME + '|' + self.TEST_UNIT1_URL + '|below|4'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID + '>: Added unit ' + WotvBotIntegrationTests.TEST_UNIT1_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (row_string, cell_value) = WorksheetUtils.fuzzyFindRow(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_UNIT1_NAME +'"', 'B')
        self.assertEqual(5, row_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_UNIT1_NAME, cell_value)

        # Add another unit and make sure it pushes the previously-added one down.
        message_text = '!admin-add-unit ' + self.TEST_UNIT2_NAME + '|' + self.TEST_UNIT2_URL + '|above|5'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID + '>: Added unit ' + WotvBotIntegrationTests.TEST_UNIT2_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (row_string, cell_value) = WorksheetUtils.fuzzyFindRow(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_UNIT2_NAME +'"', 'B')
        self.assertEqual(5, row_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_UNIT2_NAME, cell_value)

        # Test that first unit is present and was pushed down.
        (row_string, cell_value) = WorksheetUtils.fuzzyFindRow(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_UNIT1_NAME +'"', 'B')
        self.assertEqual(6, row_string)
        self.assertEqual(WotvBotIntegrationTests.TEST_UNIT1_NAME, cell_value)

    async def testAdminUtils_AddUser(self):
        """Tests adding a new user to the Admin spreadsheet."""
        self.resetAdmin()
        AdminUtils.addUser(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, 'NewUserNonAdmin', '999', False)
        assert AdminUtils.isAdmin(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, '999') is False
        AdminUtils.addUser(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, 'NewUserAdmin', '666', True)
        assert AdminUtils.isAdmin(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, '666') is True

    async def testResonanceManager_AddUser(self):
        """Tests adding a new user to the Esper resonance spreadsheet."""
        self.resetEsperResonance()
        esper_resonance_manager = EsperResonanceManager(
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.wotv_bot_config.sandbox_esper_resonance_spreadsheet_id,
            self.wotv_bot_config.access_control_spreadsheet_id,
            self.wotv_bot_config.spreadsheet_app)
        # Find the single sheet that exists in the fresh resonance spreadsheet and try to set the first cell to 'test_string'
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        home_sheet_id = spreadsheet['sheets'][0]['properties']['sheetId']
        request = WorksheetUtils.generateRequestToSetCellText(home_sheet_id, 1, 'A', 'test_string')
        requestBody = {
            'requests': [request]
        }
        self.wotv_bot_config.spreadsheet_app.batchUpdate(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id, body=requestBody).execute()
        # Now add the user, expecting that a new sheet is created and that the new sheet has the 'test_string' value in the first cell.
        esper_resonance_manager.addUser('Foo') # Base case, should get added after Home (last sheet)
        esper_resonance_manager.addUser('Boo') # Should get added before Foo
        esper_resonance_manager.addUser('Coo') # Should get added after Boo
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        assert spreadsheet['sheets'][1]['properties']['title'] == 'Boo'
        assert spreadsheet['sheets'][2]['properties']['title'] == 'Coo'
        assert spreadsheet['sheets'][3]['properties']['title'] == 'Foo'
        result = self.wotv_bot_config.spreadsheet_app.values().get(
            spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id, range='Foo!A1:A1').execute()
        final_rows = result.get('values', [])
        self.assertEqual('test_string', final_rows[0][0])

    async def testCommand_AdminAddUser_AsAdmin(self):
        """Test adding a user via a bot command, which adds the user to both the admin spreadsheet and the esper resonance tracker"""
        self.resetAdmin()
        self.resetEsperResonance()
        wotv_bot = WotvBot(self.wotv_bot_config)
        # First a normal user
        normal_user_snowflake = '6745675477457'
        normal_user_nickname = 'NikNom'
        message_text = '!admin-add-user ' + normal_user_snowflake + '|' + normal_user_nickname + '|normal'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID + '>: Added user ' + normal_user_nickname + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        assert spreadsheet['sheets'][1]['properties']['title'] == normal_user_nickname
        assert not AdminUtils.isAdmin(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, normal_user_snowflake)
        # Now an admin user
        admin_user_snowflake = '111111111111'
        admin_user_nickname = 'OpAdmin' # After NikNom lexicographically
        message_text = '!admin-add-user ' + admin_user_snowflake + '|' + admin_user_nickname + '|admin'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID + '>: Added user ' + admin_user_nickname + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        assert spreadsheet['sheets'][2]['properties']['title'] == admin_user_nickname
        assert AdminUtils.isAdmin(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, admin_user_snowflake)

    async def testCommand_AdminAddUser_AsNonAdmin(self):
        """Test adding a user via a bot command as a non-admin user, which should fail"""
        self.resetAdmin()
        self.resetEsperResonance()
        wotv_bot = WotvBot(self.wotv_bot_config)
        admin_user_snowflake = '4444444444'
        admin_user_nickname = 'SneakyPete'
        message_text = '!admin-add-user ' + admin_user_snowflake + '|' + admin_user_nickname + '|admin'
        try:
            await wotv_bot.handleMessage(self.makeMessage(message_text))
            assert False, "able to add a user as a non-admin user!"
        except ExposableException:
            pass
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        assert len(spreadsheet['sheets']) == 1 # Should not be a second tab in the resonance spreadsheet, user should not have been added.
        assert not AdminUtils.isAdmin(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, admin_user_snowflake)

    @staticmethod
    def cooldown():
        """Wait for Google Sheets API to cool down (max request rate is 100 requests per 100 seconds), with a nice countdown timer printed."""
        for i in range (30, 1, -1):
            print('>>> Google API cooldown pause (30s): ' + str(i) + '...', end='\r', flush=True)
            time.sleep(1)

    async def runAllTests(self):
        """Run all tests in the integration test suite."""
        # Core tests
        print('>>> Test: testAdminUtils_AddUser')
        await self.testAdminUtils_AddUser()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testResonanceManager_AddUser')
        await self.testResonanceManager_AddUser()
        WotvBotIntegrationTests.cooldown()

        # Bot tests using simulated Discord messages. Highest-level integration tests.
        print('>>> Test: testCommand_WhoAmI')
        await self.testCommand_WhoAmI() # Doesn't call remote APIs, no cooldown required.

        print('>>> Test: testCommand_AdminAddEsper_AsAdmin')
        await self.testCommand_AdminAddEsper_AsAdmin()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testCommand_AdminAddUnit_AsAdmin')
        await self.testCommand_AdminAddUnit_AsAdmin()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testCommand_AdminAddUser_AsAdmin')
        await self.testCommand_AdminAddUser_AsAdmin()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testCommand_AdminAddUser_AsNonAdmin')
        await self.testCommand_AdminAddUser_AsNonAdmin()
        print('All integration tests passed!')

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
