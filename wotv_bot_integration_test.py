"""Integration tests for the FFBEForever Guild Bot"""
from __future__ import annotations
import asyncio
import json
import logging
import sys
import time
import types

from admin_utils import AdminUtils
from esper_resonance_manager import EsperResonanceManager
from vision_card_ocr_utils import VisionCardOcrUtils
from wotv_bot import WotvBot, WotvBotConfig
from worksheet_utils import WorksheetUtils
from wotv_bot_common import ExposableException

class WotvBotIntegrationTests:
    """Integration tests for the FFBEForever Guild Bot"""

    # Where the main config file for the bot lives.
    CONFIG_FILE_PATH = 'integration_test_config.json'

    # Name of the default tab in the Esper Resonance spreadsheet, from which all other tabs are cloned.
    ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME = 'Home'

    # Name of the default tab in the Vision Card spreadsheet, from which all other tabs are cloned.
    VISION_CARD_SPREADSHEET_DEFAULT_TAB_NAME = 'Home'

    # The bot's own display name, snowflake ID, and discriminator
    BOT_DISPLAY_NAME = 'IntegTestBot'
    BOT_SNOWFLAKE_ID = '123456789'
    BOT_DISCRIMINATOR = '#1234'

    # Data for the bootstrapped admin user. There has to be an admin user in order for the !admin-add-user commands to be successful.
    # This user doesn't have any associated sheets, it's just for making other things simpler.
    BOOTSTRAP_USER_DISPLAY_NAME = 'BoostrapAdmin'
    BOOTSTRAP_USER_SNOWFLAKE_ID = '1'
    BOOTSTRAP_USER_DISCRIMINATOR = '#1'

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
            wotv_bot_config.vision_card_spreadsheet_id = data['vision_card_spreadsheet_id']
            wotv_bot_config.sandbox_esper_resonance_spreadsheet_id = data['sandbox_esper_resonance_spreadsheet_id']
        return wotv_bot_config

    def resetEsperResonance(self):
        """Reset the esper resonance spreadsheet with a blank sheet."""
        WotvBotIntegrationTests.resetSpreadsheet(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            WotvBotIntegrationTests.ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME)

    def resetVisionCard(self):
        """Reset the vision card spreadsheet with a blank sheet."""
        WotvBotIntegrationTests.resetSpreadsheet(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.vision_card_spreadsheet_id,
            WotvBotIntegrationTests.VISION_CARD_SPREADSHEET_DEFAULT_TAB_NAME)

    def resetAllSheets(self):
        """Method to be called before anything that requires adding users."""
        self.resetEsperResonance()
        self.resetAdmin()
        self.resetVisionCard()

    def resetAdmin(self):
        """Reset the administrative spreadsheet with a blank sheet and add the bootstrap admin user."""
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

        all_requests = [WorksheetUtils.generateRequestToAppendRow(
            sheet_id, [self.BOOTSTRAP_USER_SNOWFLAKE_ID, self.BOOTSTRAP_USER_DISPLAY_NAME, 'Admin'])]
        requestBody = {
            'requests': [all_requests]
        }
        self.wotv_bot_config.spreadsheet_app.batchUpdate(spreadsheetId=self.wotv_bot_config.access_control_spreadsheet_id, body=requestBody).execute()

    def makeMessage(
            self,
            message_text: str,
            display_name: str=TEST_USER_DISPLAY_NAME,
            snowflake_id: str=TEST_USER_SNOWFLAKE_ID,
            discriminator: str=TEST_USER_DISCRIMINATOR,
            attachment_url: str=None):
        """Construct a mock message object to send to the bot. By default uses TEST_USER settings."""
        result = types.SimpleNamespace()
        result.author = types.SimpleNamespace()
        result.author.display_name = display_name
        result.author.id = snowflake_id
        result.author.discriminator = discriminator
        result.content = message_text
        if attachment_url is not None:
            attachment = types.SimpleNamespace()
            attachment.url = attachment_url
            result.attachments = [attachment]
        return result

    def makeAdminMessage(self, message_text: str):
        """Construct a mock message object to send to the bot, as the BOOTSTRAP_USER."""
        return self.makeMessage(
            message_text,
            WotvBotIntegrationTests.BOOTSTRAP_USER_DISPLAY_NAME,
            WotvBotIntegrationTests.BOOTSTRAP_USER_SNOWFLAKE_ID,
            WotvBotIntegrationTests.BOOTSTRAP_USER_DISCRIMINATOR)

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
        expected_text = '<@' + WotvBotIntegrationTests.BOOTSTRAP_USER_SNOWFLAKE_ID + '>: Added esper ' + WotvBotIntegrationTests.TEST_ESPER1_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (column_string, cell_value) = WorksheetUtils.fuzzyFindColumn(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_ESPER1_NAME +'"', 2)
        self.assertEqual('D', column_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_ESPER1_NAME, cell_value)

        # Add another esper and make sure it pushes the previously-added one to the right.
        message_text = '!admin-add-esper ' + self.TEST_ESPER2_NAME + '|' + self.TEST_ESPER2_URL + '|left-of|D'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.BOOTSTRAP_USER_SNOWFLAKE_ID + '>: Added esper ' + WotvBotIntegrationTests.TEST_ESPER2_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (column_string, cell_value) = WorksheetUtils.fuzzyFindColumn(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_ESPER2_NAME +'"', 2)
        self.assertEqual('D', column_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_ESPER2_NAME, cell_value)

        # Test that first esper is present and was pushed right.
        (column_string, cell_value) = WorksheetUtils.fuzzyFindColumn(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
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
        expected_text = '<@' + WotvBotIntegrationTests.BOOTSTRAP_USER_SNOWFLAKE_ID + '>: Added unit ' + WotvBotIntegrationTests.TEST_UNIT1_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (row_string, cell_value) = WorksheetUtils.fuzzyFindRow(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_UNIT1_NAME +'"', 'B')
        self.assertEqual(5, row_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_UNIT1_NAME, cell_value)

        # Add another unit and make sure it pushes the previously-added one down.
        message_text = '!admin-add-unit ' + self.TEST_UNIT2_NAME + '|' + self.TEST_UNIT2_URL + '|above|5'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.BOOTSTRAP_USER_SNOWFLAKE_ID + '>: Added unit ' + WotvBotIntegrationTests.TEST_UNIT2_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        (row_string, cell_value) = WorksheetUtils.fuzzyFindRow(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_UNIT2_NAME +'"', 'B')
        self.assertEqual(5, row_string)
        # TODO: Assert that the content is a hyperlink
        self.assertEqual(WotvBotIntegrationTests.TEST_UNIT2_NAME, cell_value)

        # Test that first unit is present and was pushed down.
        (row_string, cell_value) = WorksheetUtils.fuzzyFindRow(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.ESPER_RESONANCE_SPREADSHEET_DEFAULT_TAB_NAME,
            '"' + WotvBotIntegrationTests.TEST_UNIT1_NAME +'"', 'B')
        self.assertEqual(6, row_string)
        self.assertEqual(WotvBotIntegrationTests.TEST_UNIT1_NAME, cell_value)

    async def testAdminUtils_AddUser(self):
        """Tests adding a new user to the Admin spreadsheet."""
        self.resetAdmin()
        AdminUtils.addUser(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME,
            WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID, False)
        assert not AdminUtils.isAdmin(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID)
        AdminUtils.addUser(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            WotvBotIntegrationTests.TEST_ADMIN_USER_DISPLAY_NAME,
            WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID, True)
        assert AdminUtils.isAdmin(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID)

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
        self.resetAllSheets()
        wotv_bot = WotvBot(self.wotv_bot_config)
        # First a normal user
        message_text = '!admin-add-user ' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '|' + WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME + '|normal'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.BOOTSTRAP_USER_SNOWFLAKE_ID + '>: Added user ' + WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        assert spreadsheet['sheets'][1]['properties']['title'] == WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME
        assert not AdminUtils.isAdmin(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME)
        # Now an admin user
        message_text = '!admin-add-user ' + WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID
        message_text += '|' + WotvBotIntegrationTests.TEST_ADMIN_USER_DISPLAY_NAME + '|admin'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeAdminMessage(message_text))
        expected_text = '<@' + WotvBotIntegrationTests.BOOTSTRAP_USER_SNOWFLAKE_ID
        expected_text += '>: Added user ' + WotvBotIntegrationTests.TEST_ADMIN_USER_DISPLAY_NAME + '!'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        assert spreadsheet['sheets'][1]['properties']['title'] == WotvBotIntegrationTests.TEST_ADMIN_USER_DISPLAY_NAME
        assert spreadsheet['sheets'][2]['properties']['title'] == WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME
        assert AdminUtils.isAdmin(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            WotvBotIntegrationTests.TEST_ADMIN_USER_SNOWFLAKE_ID)

    async def testCommand_AdminAddUser_AsNonAdmin(self):
        """Test adding a user via a bot command as a non-admin user, which should fail"""
        self.resetAdmin()
        self.resetEsperResonance()
        AdminUtils.addUser(
            self.wotv_bot_config.spreadsheet_app,
            self.wotv_bot_config.access_control_spreadsheet_id,
            WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME,
            WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID, False)
        wotv_bot = WotvBot(self.wotv_bot_config)
        message_text = '!admin-add-user 777|SneakyPete|admin'
        try:
            await wotv_bot.handleMessage(self.makeMessage(message_text))
            assert False, "able to add a user as a non-admin user!"
        except ExposableException:
            pass
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.esper_resonance_spreadsheet_id).execute()
        assert len(spreadsheet['sheets']) == 1 # Should not be a second tab in the resonance spreadsheet, user should not have been added.
        assert not AdminUtils.isAdmin(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, '777')

    async def addNormalUserToAll(self):
        """Add the normal user to all sheets."""
        message_text = '!admin-add-user ' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID
        message_text += '|' + WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME + '|normal'
        wotv_bot = WotvBot(self.wotv_bot_config)
        await wotv_bot.handleMessage(self.makeAdminMessage(message_text))

    async def testCommand_ResSet(self):
        """Test various combinations of setting esper resonance."""
        self.resetAllSheets()
        await self.addNormalUserToAll()
        wotv_bot = WotvBot(self.wotv_bot_config)
        # First set up a unit and esper to set the resonance on.
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-unit ' + self.TEST_UNIT1_NAME + '|' + self.TEST_UNIT1_URL + '|below|2'))
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-esper ' + self.TEST_ESPER1_NAME + '|' + self.TEST_ESPER1_URL + '|right-of|B'))
        # Initial command to set resonance should result in default to low priority, with no previous resonance returned.
        message = self.makeMessage('!res-set ' + self.TEST_UNIT1_NAME + '/' + self.TEST_ESPER1_NAME + ' 7')
        (response_text, reaction) = await wotv_bot.handleMessage(message)
        expected_text = '<@{0}>: {1}/{2} resonance has been set to {3} (was: {4})'.format(
            WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID, self.TEST_UNIT1_NAME, self.TEST_ESPER1_NAME, 'Low Priority: 7/10', '(not set)')
        self.assertEqual(expected_text, response_text)
        assert reaction is not None
        self.cooldown(10)
        # Now set a medium priority, and expect to see low priority of 7 previously set.
        message = self.makeMessage('!res-set ' + self.TEST_UNIT1_NAME + '/' + self.TEST_ESPER1_NAME + ' 8/m')
        (response_text, reaction) = await wotv_bot.handleMessage(message)
        expected_text = '<@{0}>: {1}/{2} resonance has been set to {3} (was: {4})'.format(
            WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID, self.TEST_UNIT1_NAME, self.TEST_ESPER1_NAME, 'Medium Priority: 8/10', 'Low Priority: 7/10')
        self.assertEqual(expected_text, response_text)
        assert reaction is not None
        self.cooldown(10)
        # Now set a high priority, and expect to see medium priority of 8 previously set.
        message = self.makeMessage('!res-set ' + self.TEST_UNIT1_NAME + '/' + self.TEST_ESPER1_NAME + ' 9/h',)
        (response_text, reaction) = await wotv_bot.handleMessage(message)
        expected_text = '<@{0}>: {1}/{2} resonance has been set to {3} (was: {4})'.format(
            WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID, self.TEST_UNIT1_NAME, self.TEST_ESPER1_NAME, 'High Priority: 9/10', 'Medium Priority: 8/10')
        self.assertEqual(expected_text, response_text)
        assert reaction is not None
        self.cooldown(10)
        # Finally, set priority to 10.
        message = self.makeMessage('!res-set ' + self.TEST_UNIT1_NAME + '/' + self.TEST_ESPER1_NAME + ' 10')
        (response_text, reaction) = await wotv_bot.handleMessage(message)
        expected_text = '<@{0}>: {1}/{2} resonance has been set to {3} (was: {4})'.format(
            WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID, self.TEST_UNIT1_NAME, self.TEST_ESPER1_NAME, '10/10', 'High Priority: 9/10')
        self.assertEqual(expected_text, response_text)
        assert reaction is not None

    async def testCommand_Res(self):
        """Test various combinations of getting esper resonance."""
        self.resetAllSheets()
        await self.addNormalUserToAll()
        wotv_bot = WotvBot(self.wotv_bot_config)
        # First set up a unit and esper to set the resonance on.
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-unit Little Leela|' + self.TEST_UNIT1_URL + '|below|2'))
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-unit Little Leela (Halloween)|' + self.TEST_UNIT2_URL + '|below|3'))
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-esper Chocobo|' + self.TEST_ESPER1_URL + '|right-of|B'))
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-esper Red Chocobo|' + self.TEST_ESPER2_URL + '|right-of|C'))
        self.cooldown(15)
        # Set resonance on both units and both espers so we can force the most complex returns of multiple entries
        # Also use a real example so we can do some fuzzy match searches
        await wotv_bot.handleMessage(self.makeMessage('!res-set Little Leela (Halloween)/Chocobo 1'))
        await wotv_bot.handleMessage(self.makeMessage('!res-set Little Leela (Halloween)/Red Chocobo 2/m'))
        await wotv_bot.handleMessage(self.makeMessage('!res-set "Little Leela"/Chocobo 3/h'))
        await wotv_bot.handleMessage(self.makeMessage('!res-set "Little Leela"/Red Chocobo 10'))
        self.cooldown(15)
        # Now attempt a fuzzy match unit search...
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage('!res ween la'))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: resonance listing for Little Leela (Halloween):'
        expected_text += '\nChocobo: Low Priority: 1/10\nRed Chocobo: Medium Priority: 2/10'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        # And an exact-match unit search...
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage('!res "Little Leela"'))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: resonance listing for Little Leela:'
        expected_text += '\nChocobo: High Priority: 3/10\nRed Chocobo: 10/10'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        # And then a fuzzy match esper search...
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage('!res choco r'))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: resonance listing for Red Chocobo:'
        expected_text += '\nLittle Leela: 10/10\nLittle Leela (Halloween): Medium Priority: 2/10'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        # And an exact-match esper search...
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage('!res "Chocobo"'))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: resonance listing for Chocobo:'
        expected_text += '\nLittle Leela: High Priority: 3/10\nLittle Leela (Halloween): Low Priority: 1/10'
        self.assertEqual(expected_text, response_text)
        assert reaction is None

    async def testVisionCardOcrUtils_ExtractVisionCardFromScreenshot(self):
        """Attempt to extract a vision card's text from a screenshot"""
        image = VisionCardOcrUtils.loadScreenshotFromFilesystem('integ_test_res/vision_card_test_image_01.png')
        vision_card = VisionCardOcrUtils.extractVisionCardFromScreenshot(image, True)
        assert vision_card is not None
        WotvBotIntegrationTests.assertEqual('Beguiling Witch', vision_card.Name)
        WotvBotIntegrationTests.assertEqual(40, vision_card.Cost)
        WotvBotIntegrationTests.assertEqual(184, vision_card.HP)
        WotvBotIntegrationTests.assertEqual(None, vision_card.DEF)
        WotvBotIntegrationTests.assertEqual(None, vision_card.TP)
        WotvBotIntegrationTests.assertEqual(None, vision_card.SPR)
        WotvBotIntegrationTests.assertEqual(None, vision_card.AP)
        WotvBotIntegrationTests.assertEqual(None, vision_card.DEX)
        WotvBotIntegrationTests.assertEqual(80, vision_card.ATK)
        WotvBotIntegrationTests.assertEqual(None, vision_card.AGI)
        WotvBotIntegrationTests.assertEqual(98, vision_card.MAG)
        WotvBotIntegrationTests.assertEqual(None, vision_card.Luck)
        WotvBotIntegrationTests.assertEqual('Casting Time Reduced 30', vision_card.PartyAbility)
        WotvBotIntegrationTests.assertEqual(['Reaper Killer Up 25', 'DEF Down 5'], vision_card.BestowedEffects)

    async def testCommand_VcSet(self):
        """Test setting a vision card."""
        self.resetAllSheets()
        await self.addNormalUserToAll()
        wotv_bot = WotvBot(self.wotv_bot_config)
        wotv_bot.INTEG_TEST_LOCAL_FILESYSTEM_READ_FOR_VISION_CARD = True
        # Set up a vision card and OCR it
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-vc Beguiling Witch|http://www.example.com|below|2'))
        message = self.makeMessage(message_text='!vc-set', attachment_url='integ_test_res/vision_card_test_image_01.png')
        (response_text, reaction) = await wotv_bot.handleMessage(message)
        assert response_text is not None
        assert reaction is not None # On success, acknolwedges the write.
        # Verify row was written correctly independent of read code.
        spreadsheet = self.wotv_bot_config.spreadsheet_app.get(spreadsheetId=self.wotv_bot_config.vision_card_spreadsheet_id).execute()
        assert spreadsheet['sheets'][1]['properties']['title'] == WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME # Sanity check
        # Columns:
        # Name,Awakening,Level,Cost,HP,DEF,TP,SPR,AP,DEX,ATK,AGI,MAG,Luck,Party Ability,Bestowed Abilities
        # (B) ..........................................................................(Q)
        fetch_range = WotvBotIntegrationTests.TEST_USER_DISPLAY_NAME + '!B3:Q3'
        data_rows = self.wotv_bot_config.spreadsheet_app.values().get(
            spreadsheetId=self.wotv_bot_config.vision_card_spreadsheet_id, range=fetch_range).execute()
        data_row = data_rows.get('values', [])[0]
        WotvBotIntegrationTests.assertEqual('Beguiling Witch', data_row[0]) # Name
        # TODO: Check awakening and level when they are available
        WotvBotIntegrationTests.assertEqual('', data_row[1]) # Awakening
        WotvBotIntegrationTests.assertEqual('', data_row[2]) # Level
        WotvBotIntegrationTests.assertEqual('40', data_row[3]) # Cost
        WotvBotIntegrationTests.assertEqual('184', data_row[4]) # HP
        WotvBotIntegrationTests.assertEqual('', data_row[5]) # DEF
        WotvBotIntegrationTests.assertEqual('', data_row[6]) # TP
        WotvBotIntegrationTests.assertEqual('', data_row[7]) # SPR
        WotvBotIntegrationTests.assertEqual('', data_row[8]) # AP
        WotvBotIntegrationTests.assertEqual('', data_row[9]) # DEX
        WotvBotIntegrationTests.assertEqual('80', data_row[10]) # ATK
        WotvBotIntegrationTests.assertEqual('', data_row[11]) # AGI
        WotvBotIntegrationTests.assertEqual('98', data_row[12]) # MAG
        WotvBotIntegrationTests.assertEqual('', data_row[13]) # Luck
        WotvBotIntegrationTests.assertEqual('Casting Time Reduced 30', data_row[14]) # Party Ability
        WotvBotIntegrationTests.assertEqual('Reaper Killer Up 25\nDEF Down 5', data_row[15]) # Bestowed Effects

    async def testCommand_Vc(self):
        """Test reading a previously-written vision card"""
        self.resetAllSheets()
        await self.addNormalUserToAll()
        wotv_bot = WotvBot(self.wotv_bot_config)
        wotv_bot.INTEG_TEST_LOCAL_FILESYSTEM_READ_FOR_VISION_CARD = True
        # Set up a vision card and OCR it
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-vc Beguiling Witch|http://www.example.com|below|2'))
        message = self.makeMessage(message_text='!vc-set', attachment_url='integ_test_res/vision_card_test_image_01.png')
        await wotv_bot.handleMessage(message)
        # Now try to read it back
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!vc Beguil'))
        expected_text = ''
        expected_text += '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '987654321>: Vision Card:\n'
        expected_text += 'Beguiling Witch\n'
        expected_text += '  Cost: 40\n'
        expected_text += '  HP: 184\n'
        expected_text += '  DEF: None\n'
        expected_text += '  TP: None\n'
        expected_text += '  SPR: None\n'
        expected_text += '  AP: None\n'
        expected_text += '  DEX: None\n'
        expected_text += '  ATK: 80\n'
        expected_text += '  AGI: None\n'
        expected_text += '  MAG: 98\n'
        expected_text += '  Luck: None\n'
        expected_text += '  Party Ability: Casting Time Reduced 30\n'
        expected_text += '  Bestowed Effects:\n'
        expected_text += '    Reaper Killer Up 25\n'
        expected_text += '    DEF Down 5\n'
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

    @staticmethod
    def cooldown(time_secs: int=30):
        """Wait for Google Sheets API to cool down (max request rate is 100 requests per 100 seconds), with a nice countdown timer printed."""
        for i in range (time_secs, 0, -1):
            print('>>> Google API cooldown pause (' + str(time_secs) + 's): ' + str(i) + '...', end='\r', flush=True)
            time.sleep(1)
        print('\n>>> Google API cooldown pause completed, moving on.')

    async def runAllTests(self):
        """Run all tests in the integration test suite."""
        # Core tests
        print('>>> Test: testVisionCardOcrUtils_ExtractVisionCardFromScreenshot')
        await self.testVisionCardOcrUtils_ExtractVisionCardFromScreenshot()

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

        print('>>> Test: testCommand_ResSet')
        await self.testCommand_ResSet()

        print('>>> Test: testCommand_Res')
        await self.testCommand_Res()

        print('>>> Test: testCommand_VcSet')
        await self.testCommand_VcSet()

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
    if len(sys.argv) != 2:
        raise Exception('Run the script with either the argument "all" (without quotes) to run all tests, or the name of a specific test to run.')
    if sys.argv[1] == 'all':
        print('Running all integration tests.')
        loop.run_until_complete(suite.runAllTests())
        print('All integration tests passed!')
    else:
        method_to_invoke = getattr(suite, sys.argv[1])
        if method_to_invoke is None:
            raise Exception('No such method available to invoke: ' + sys.argv[1])
        print('Running specific integration test: ' + sys.argv[1])
        loop.run_until_complete(method_to_invoke())
        print(sys.argv[1] + ' passed!')
    loop.close()
