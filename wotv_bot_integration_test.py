"""Integration tests for the FFBEForever Guild Bot"""
# pylint: disable=too-many-lines
# pylint: disable=line-too-long
from __future__ import annotations
import asyncio
import json
import logging
import os
import queue
import sys
import time
import types
import threading
from typing import Dict

from admin_utils import AdminUtils
from data_files import DataFiles
from data_file_search_utils import DataFileSearchUtils
from esper_resonance_manager import EsperResonanceManager
from reminders import Reminders
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

    # Fake channel
    TEST_CHANNEL_ID = '123456789'

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

    # For testing data dump functionality
    MOCK_DATA_DUMP_ROOT_PATH = 'integ_test_res/mock_data_dump'

    # Temporary storage of reminders during testing of standalone reminders system.
    STANDALONE_TEST_REMINDERS_PATH = 'integ_test_res/standalone_test_reminders.sql'

    # Temporary storage of reminders during bot testing.
    BOT_TEST_REMINDERS_PATH = 'integ_test_res/bot_test_reminders.sql'

    """An instance of the bot, configured to manage specific spreadsheets and using Discord and Google credentials."""
    def __init__(self, wotv_bot_config: WotvBotConfig):
        self.wotv_bot_config = wotv_bot_config
        self.__BOT_REMINDER_CALLBACKS : Dict[str, threading.Semaphore] = {}

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
            wotv_bot_config.data_files = DataFiles.parseDataDump(data['data_dump_root_path'])
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
        fake_channel = types.SimpleNamespace()
        fake_channel.id = WotvBotIntegrationTests.TEST_CHANNEL_ID
        result.get_channel = lambda: fake_channel
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

    async def testCommand_Help(self): # pylint: disable=missing-function-docstring
        wotv_bot = WotvBot(self.wotv_bot_config)
        message_text = '!help'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text))
        assert response_text is not None
        assert reaction is None

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
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
        # And an exact-match unit search...
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage('!res "Little Leela"'))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: resonance listing for Little Leela:'
        expected_text += '\nChocobo: High Priority: 3/10\nRed Chocobo: 10/10'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        self.cooldown(15)
        # And then a fuzzy match esper search...
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage('!res choco r'))
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: resonance listing for Red Chocobo:'
        expected_text += '\nLittle Leela: 10/10\nLittle Leela (Halloween): Medium Priority: 2/10'
        self.assertEqual(expected_text, response_text)
        assert reaction is None
        self.cooldown(15)
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
        self.cooldown(15)
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
        self.cooldown(15)
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

    async def testCommand_VcAbility(self):
        """Test reading a previously-written vision card via ability search"""
        self.resetAllSheets()
        await self.addNormalUserToAll()
        self.cooldown(15)
        wotv_bot = WotvBot(self.wotv_bot_config)
        wotv_bot.INTEG_TEST_LOCAL_FILESYSTEM_READ_FOR_VISION_CARD = True
        # Set up a vision card and OCR it
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-vc Beguiling Witch|http://www.example.com|below|2'))
        message = self.makeMessage(message_text='!vc-set', attachment_url='integ_test_res/vision_card_test_image_01.png') # Beguiling Witch
        await wotv_bot.handleMessage(message)
        self.cooldown(15)
        await wotv_bot.handleMessage(self.makeAdminMessage('!admin-add-vc Secret Orders|http://www.example.com|below|3'))
        message = self.makeMessage(message_text='!vc-set', attachment_url='integ_test_res/vision_card_test_image_02.png') # Secret Orders
        await wotv_bot.handleMessage(message)
        # Match against Beguiling Witch only
        expected_text = ''
        expected_text += '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Vision Cards:\n'
        expected_text += '  Beguiling Witch\n'
        expected_text += '    Party Ability: Casting Time Reduced 30\n'
        expected_text += '    Bestowed Effect: Reaper Killer Up 25\n'
        expected_text += '    Bestowed Effect: DEF Down 5\n'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!vc-ability reap kill'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        self.cooldown(15)
        # Match against Secret Orders only
        expected_text = ''
        expected_text += '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Vision Cards:\n'
        expected_text += '  Secret Orders\n'
        expected_text += '    Party Ability: Slash Attack Up 20\n'
        expected_text += '    Bestowed Effect: AGI Up 10%\n'
        expected_text += '    Bestowed Effect: SPR Down 5\n'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!vc-ability Slash'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        self.cooldown(15)
        # Match against both cards...
        expected_text = ''
        expected_text += '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Vision Cards:\n'
        expected_text += '  Beguiling Witch\n'
        expected_text += '    Party Ability: Casting Time Reduced 30\n'
        expected_text += '    Bestowed Effect: Reaper Killer Up 25\n'
        expected_text += '    Bestowed Effect: DEF Down 5\n'
        expected_text += '  Secret Orders\n'
        expected_text += '    Party Ability: Slash Attack Up 20\n'
        expected_text += '    Bestowed Effect: AGI Up 10%\n'
        expected_text += '    Bestowed Effect: SPR Down 5\n'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!vc-ability down'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        self.cooldown(15)
        # Match nothing.
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: No vision cards matched the ability search.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!vc-ability Qwyjibo'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

    async def testDataFiles_ParseDataDump(self): # async for convenience of standalone test runner, which expects a coroutine
        """Test the basic functionality of the data dump parser"""
        data_files = DataFiles.parseDataDump(WotvBotIntegrationTests.MOCK_DATA_DUMP_ROOT_PATH + '/')
        # Integration tests only have Mont with two skills (master ability and Killer Blade), and his 3 jobs.
        data_files.sanityCheckCounts(min_unit_count=1, min_skill_count=2, min_job_count=3)
        data_files.sanityCheckMont()

    async def testDataFileSearchUtils_findUnitWithSkillName(self): # async for convenience of standalone test runner, which expects a coroutine
        """Test searching for a unit with a skill name"""
        data_files = DataFiles.parseDataDump(WotvBotIntegrationTests.MOCK_DATA_DUMP_ROOT_PATH + '/')
        # Test exact match with a Board Skill
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, '"Killer Bl"')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Killer Blade'
        assert matches[0].board_skill.unlocked_by_job.name == 'Lord'
        assert matches[0].board_skill.unlocked_by_job_level == 7

        # Test exact match with a Master Ability
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, '"Master A"')
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Master Ability'
        assert matches[0].is_master_ability is True
        assert matches[0].board_skill is None
        assert matches[1].unit.name == 'Engelbert'
        assert matches[1].skill.name == 'Master Ability'
        assert matches[1].is_master_ability is True
        assert matches[0].is_limit_burst is False
        assert matches[1].board_skill is None

        # Test exact match with a Limit Burst
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, '"Destiny\'s Cr"')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Destiny\'s Cross'
        assert matches[0].is_master_ability is False
        assert matches[0].is_limit_burst is True
        assert matches[0].board_skill is None

        # Test fuzzy match with a Board Skill
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, 'LAD ler')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'

        # Test fuzzy match with a Master Ability
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, 'MaStEr')
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[1].unit.name == 'Engelbert'

        # Test fuzzy match with a Limit Burst
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, 'Destiny')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'

        # Test using an explicitly-passed list (as if a filtered list of units had been provided)
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, 'MaStEr')
        matches = matches[1:2] # Just Engelbert
        matches = DataFileSearchUtils.findUnitWithSkillName(data_files, 'MaStEr', matches)
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        assert matches[0].skill.name == 'Master Ability'
        assert matches[0].is_master_ability is True
        assert matches[0].board_skill is None

    async def testDataFileSearchUtils_findUnitWithSkillDescription(self): # async for convenience of standalone test runner, which expects a coroutine
        """Test searching for a unit with a skill description"""
        data_files = DataFiles.parseDataDump(WotvBotIntegrationTests.MOCK_DATA_DUMP_ROOT_PATH + '/')
        # Test exact match with a Board Skill
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, '"to target & bestows"')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Killer Blade'
        assert matches[0].is_master_ability is False
        assert matches[0].board_skill.unlocked_by_job.name == 'Lord'
        assert matches[0].board_skill.unlocked_by_job_level == 7

        # Test exact match with Master Ability skill
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, '"+15, Jump +1"')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Master Ability'
        assert matches[0].is_master_ability is True
        assert matches[0].board_skill is None

        # Test exact match with Limit Burst skill
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, '"Deals Dmg (L) to targets within range."')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Destiny\'s Cross'
        assert matches[0].is_master_ability is False
        assert matches[0].is_limit_burst is True
        assert matches[0].board_skill is None

        # Test fuzzy match with a Board Skill
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, 'AN EAT')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Killer Blade'
        assert matches[0].is_master_ability is False
        assert matches[0].board_skill.unlocked_by_job.name == 'Lord'
        assert matches[0].board_skill.unlocked_by_job_level == 7

        # Test fuzzy match with Master Ability skill
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, 'JuMp')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Master Ability'
        assert matches[0].is_master_ability is True
        assert matches[0].board_skill is None

        # Test fuzzy match with Limit Burst skill
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, 'targets within range.')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].skill.name == 'Destiny\'s Cross'
        assert matches[0].is_master_ability is False
        assert matches[0].is_limit_burst is True
        assert matches[0].board_skill is None

        # Test using an explicitly-passed list (as if a filtered list of units had been provided)
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, '+15') # Master ability
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[1].unit.name == 'Engelbert'
        matches = matches[1:2] # Just Engelbert
        matches = DataFileSearchUtils.findUnitWithSkillDescription(data_files, '+15', matches) # Master ability
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        assert matches[0].skill.name == 'Master Ability'
        assert matches[0].is_master_ability is True
        assert matches[0].board_skill is None

    async def testDataFileSearchUtils_findUnitWithJobName(self): # async for convenience of standalone test runner, which expects a coroutine
        """Test searching for a unit with a specific job name"""
        data_files = DataFiles.parseDataDump(WotvBotIntegrationTests.MOCK_DATA_DUMP_ROOT_PATH + '/')
        # Test exact match
        matches = DataFileSearchUtils.findUnitWithJobName(data_files, '"Paladin"')
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].job.name == 'Paladin'
        assert matches[1].unit.name == 'Engelbert'
        assert matches[1].job.name == 'Paladin'
        matches = DataFileSearchUtils.findUnitWithJobName(data_files, '"Lord"')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].job.name == 'Lord'

        # Test fuzzy match
        matches = DataFileSearchUtils.findUnitWithJobName(data_files, 'ladin')
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].job.name == 'Paladin'
        assert matches[1].unit.name == 'Engelbert'
        assert matches[1].job.name == 'Paladin'
        matches = DataFileSearchUtils.findUnitWithJobName(data_files, 'onk')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        assert matches[0].job.name == 'Monk'

        # Test using an explicitly-passed list (as if a filtered list of units had been provided)
        matches = DataFileSearchUtils.findUnitWithJobName(data_files, 'ladin')
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[1].unit.name == 'Engelbert'
        matches = matches[1:2] # Just Engelbert
        matches = DataFileSearchUtils.findUnitWithJobName(data_files, 'ladin', matches)
        assert len(matches) == 1
        assert matches[0].job.name == 'Paladin'

    async def testDataFileSearchUtils_findUnitWithRarity(self): # async for convenience of standalone test runner, which expects a coroutine
        """Test searching for a unit with a specific rarity"""
        data_files = DataFiles.parseDataDump(WotvBotIntegrationTests.MOCK_DATA_DUMP_ROOT_PATH + '/')
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, 'mr')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, 'ur')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        # Test de-quoting exact-match string (no-op functionality since fuzzy-match is not supported, but should not cause problems)
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, '"ur"')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        # Test junk rarity
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, 'xx')
        assert not matches
        # Test that exact match is required: 'r' should not match 'mr' and 'sr' in this case because no fuzzy match is supported
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, 'r')
        assert not matches

        # Test using an explicitly-passed list (as if a filtered list of units had been provided)
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, 'mr')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, 'ur', matches)
        assert not matches # should not find Engelbert, because he is no longer in the list

    async def testDataFileSearchUtils_findUnitWithElement(self): # async for convenience of standalone test runner, which expects a coroutine
        """Test searching for a unit with a specific element"""
        data_files = DataFiles.parseDataDump(WotvBotIntegrationTests.MOCK_DATA_DUMP_ROOT_PATH + '/')
        matches = DataFileSearchUtils.findUnitWithElement(data_files, 'eaRth')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        matches = DataFileSearchUtils.findUnitWithElement(data_files, 'LigHt')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        # Test de-quoting exact-match string (no-op functionality since fuzzy-match is not supported, but should not cause problems)
        matches = DataFileSearchUtils.findUnitWithElement(data_files, '"light"')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        # Test junk element
        matches = DataFileSearchUtils.findUnitWithElement(data_files, 'xx')
        assert not matches

        # Test using an explicitly-passed list (as if a filtered list of units had been provided)
        matches = DataFileSearchUtils.findUnitWithElement(data_files, 'earth')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        matches = DataFileSearchUtils.findUnitWithRarity(data_files, 'light', matches)
        assert not matches # should not find Engelbert, because he is no longer in the list

    async def testDataFileSearchUtils_RichUnitSearch(self): # async for convenience of standalone test runner, which expects a coroutine
        """Test searching for a unit with rich syntax"""
        data_files = DataFiles.parseDataDump(WotvBotIntegrationTests.MOCK_DATA_DUMP_ROOT_PATH + '/')
        # Base case: No refinements. Also test that search type result is appropriate for "job" base search.
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin')
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[1].unit.name == 'Engelbert'
        assert matches[0].job.name == 'Paladin'
        assert matches[1].job.name == 'Paladin'

        # Test that search type result is appropriate for "skill" base search.
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'skill-name', 'Killer Blade')
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert not matches[0].is_master_ability
        assert matches[0].board_skill.skill_id is not None

        # Base case: No refinements, search ALL units. Should just be unit search results, no skill or job data.
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'all', None)
        assert len(matches) == 2
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[1].unit.name == 'Engelbert'
        assert not hasattr(matches[0], 'job')
        assert not hasattr(matches[0], 'is_master_ability')
        assert not hasattr(matches[1], 'job')
        assert not hasattr(matches[1], 'is_master_ability')

        # Refine to only units with light (Engelbert)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['element light'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        assert matches[0].job.name == 'Paladin'
        # Refine to only units without light (Mont)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['not element light'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].job.name == 'Paladin'
        # Refine to only units with skill name "Killer Blade" (Mont)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['skill-name Killer Blade'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].job.name == 'Paladin'
        # Refine to only units without skill name "Killer Blade" (Engelbert)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['not skill-name Killer Blade'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        assert matches[0].job.name == 'Paladin'
        # Refine to only units with skill description "Man Eater" (Mont)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['skill-desc "Man eat"'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].job.name == 'Paladin'
        # Refine to only units without skill description "Man Eater" (Engelbert)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['not skill-desc eaTer'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        assert matches[0].job.name == 'Paladin'
        # Refine to only units with rarity MR (Mont)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['rarity MR'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Mont Leonis'
        assert matches[0].job.name == 'Paladin'
        # Refine to only units without rarity MR (Engelbert)
        matches = DataFileSearchUtils.richUnitSearch(data_files, 'job', 'paladin', ['not rarity MR'])
        assert len(matches) == 1
        assert matches[0].unit.name == 'Engelbert'
        assert matches[0].job.name == 'Paladin'

    async def testCommand_WhimsyShop(self):
        """Test creating and managing whimsy shop reminders via the bot."""
        wotv_bot = WotvBot(self.wotv_bot_config)
        # Speed up the reminder times so they come faster.
        wotv_bot.whimsy_shop_nrg_reminder_delay_ms = 100
        wotv_bot.whimsy_shop_spawn_reminder_delay_ms = 200
        self.cleanupBotReminders()
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Your reminder has been set.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!whimsy'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Now expect the NRG reminder first
        expected_text = '<@{0}>: This is your requested whimsy shop reminder: NRG spent will now start counting towards the next Whimsy Shop.'.format(WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID)
        assert WotvBotIntegrationTests.readFromTestChannel() == expected_text
        # And the spawn reminder second
        expected_text = '<@{0}>: This is your requested whimsy shop reminder: The Whimsy Shop is ready to spawn again.'.format(WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID)
        assert WotvBotIntegrationTests.readFromTestChannel() == expected_text

    async def testCommand_SkillsByName(self):
        """Test searching for skills by name."""
        wotv_bot = WotvBot(self.wotv_bot_config)

        # Test fuzzy match for Killer Blade
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Skill "Killer Blade" learned by Mont Leonis (MR rarity, Earth element) with job Lord at job level 7: Deals Dmg (L) to target & bestows Man Eater.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name Blade'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test exact match for Killer Blade
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name "Killer Bla"'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test fuzzy match for master ability
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Master ability for Engelbert (UR rarity, Light element): DEF +15\n'
        expected_text += 'Master ability for Mont Leonis (MR rarity, Earth element): DEF +15, Jump +1'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name Master'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test exact match for master ability
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name "ster Ability"'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test fuzzy match for Limit Burst
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Limit burst (Enduring Fortitude) for Engelbert (UR rarity, Light element): Deals Dmg (L) to target & raises Dmg according to amount of own HP lost.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name enduring'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test exact match for Limit Burst
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name "g Fortitu"'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test exact match for nonexistent skill
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: No skills matched the search.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name "Nonexistent Skill"'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test fuzzy match for nonexistent skill
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name qwyjibo'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test refinements: Not earth
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Master ability for Engelbert (UR rarity, Light element): DEF +15'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name Master\n  not element earth'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

        # Test refinements: earth
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Master ability for Mont Leonis (MR rarity, Earth element): DEF +15, Jump +1'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-name Master\n eLeMent earTh'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

    async def testCommand_SkillsByDescription(self):
        """Test searching for skills by description."""
        wotv_bot = WotvBot(self.wotv_bot_config)
        # Test fuzzy match for Killer Blade
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Skill "Killer Blade" learned by Mont Leonis (MR rarity, Earth element) with job Lord at job level 7: Deals Dmg (L) to target & bestows Man Eater.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-description eater'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test exact match for Killer Blade
        (response_text, reaction) = await wotv_bot.handleMessage(
            self.makeMessage(message_text='!skills-by-description "Deals Dmg (L) to target & bestows Man Eater."'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test fuzzy match for master ability
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Master ability for Engelbert (UR rarity, Light element): DEF +15\n'
        expected_text += 'Master ability for Mont Leonis (MR rarity, Earth element): DEF +15, Jump +1'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-description DEF +'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test exact match for master ability
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-desc "+15"'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test exact match for nonexistent skill
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: No skills matched the search.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-description "Nonexistent skill description"'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test fuzzy match for nonexistent skill
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-desc qwyjibo'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test refinements: Not earth
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Skill "Sentinel" learned by Engelbert (UR rarity, Light element) with job Paladin at job level 3: Significantly raises own DEF/SPR for 1 turn & significantly lowers Evasion Rate for 1 turn.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-desc Evasion Rate\n  not element earth'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test refinements: earth
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Matching Skills:\n'
        expected_text += 'Skill "Sentinel" learned by Mont Leonis (MR rarity, Earth element) with job Paladin at job level 5: Significantly raises own DEF/SPR for 1 turn & significantly lowers Evasion Rate for 1 turn.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!skills-by-desc Evasion Rate\n\n\n eLeMent earTh\n\n'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

    async def testCommand_UnitSearch(self):
        """Test searching for units in various rich ways."""
        wotv_bot = WotvBot(self.wotv_bot_config)
        # Test skill-name fuzzy match for Killer Blade
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Skill "Killer Blade" learned by Mont Leonis (MR rarity, Earth element) with job Lord at job level 7: Deals Dmg (L) to target & bestows Man Eater.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-search skill-name Killer Bla'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test skill-description fuzzy match for master ability
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Master ability for Engelbert (UR rarity, Light element): DEF +15\n'
        expected_text += 'Master ability for Mont Leonis (MR rarity, Earth element): DEF +15, Jump +1'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-search skill-desc DEF +'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test skill-description with refinement: Not earth
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Skill "Sentinel" learned by Engelbert (UR rarity, Light element) with job Paladin at job level 3: Significantly raises own DEF/SPR for 1 turn & significantly lowers Evasion Rate for 1 turn.'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-search skill-desc Evasion Rate\n  not element earth'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test job with refinement: earth and mr rarity
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Job "Paladin" learned by Mont Leonis (MR rarity, Earth element)'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-seARch job Paladin\n  element earth\nrarity mr'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test job only
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Job "Paladin" learned by Engelbert (UR rarity, Light element)\n'
        expected_text += 'Job "Paladin" learned by Mont Leonis (MR rarity, Earth element)'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-seARch job Paladin'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test plain unit search with refinement: earth and mr rarity
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Mont Leonis (MR rarity, Earth element)'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!Unit-search all\n  element earth\nrarity mr'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test UR rarity unit search with refinement: light
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Engelbert (UR rarity, Light element)'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-search rarIty UR\n  element light'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test UR rarity unit search only
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Engelbert (UR rarity, Light element)'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-seaRch rarity UR'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None
        # Test Earth element unit search only
        expected_text = '<@' + WotvBotIntegrationTests.TEST_USER_SNOWFLAKE_ID + '>: Results:\n'
        expected_text += 'Mont Leonis (MR rarity, Earth element)'
        (response_text, reaction) = await wotv_bot.handleMessage(self.makeMessage(message_text='!unit-search eleMent eaRTH'))
        WotvBotIntegrationTests.assertEqual(expected_text, response_text)
        assert reaction is None

    __STANDALONE_REMINDER_CALLBACKS : Dict[str, asyncio.Semaphore] = {}

    def cleanupBotReminders(self):
        """Delete the testing reminders SQL database for bot integration testing and restart the reminders system."""
        # Callbacks trigger semaphore release. Tests can then await the semaphores to continue forward.
        self.wotv_bot_config.reminders.stop()
        self.__BOT_REMINDER_CALLBACKS = {}
        self.__BOT_REMINDER_CALLBACKS['whimsy-nrg'] = threading.Semaphore(1)
        self.__BOT_REMINDER_CALLBACKS['whimsy-spawn'] = threading.Semaphore(1)
        if os.path.exists(WotvBotIntegrationTests.BOT_TEST_REMINDERS_PATH):
            os.remove(WotvBotIntegrationTests.BOT_TEST_REMINDERS_PATH)
        self.wotv_bot_config.reminders = Reminders(WotvBotIntegrationTests.BOT_TEST_REMINDERS_PATH)
        self.wotv_bot_config.reminders.start()

    @staticmethod
    def cleanupStandaloneReminders():
        """Delete the testing reminders SQL database for standalone reminders testing."""
        # Callbacks trigger semaphore release. Tests can then await the semaphores to continue forward.
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS : Dict[str, threading.Semaphore] = {}
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-nrg'] = threading.Semaphore(1)
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-spawn'] = threading.Semaphore(1)
        if os.path.exists(WotvBotIntegrationTests.STANDALONE_TEST_REMINDERS_PATH):
            os.remove(WotvBotIntegrationTests.STANDALONE_TEST_REMINDERS_PATH)

    @staticmethod
    def standaloneWhimsyNrgReminderCallback(param1):
        """Helper function for test execution."""
        print('callback function for whimsy nrg reminder was triggered with param ' + str(param1))
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS[param1].release()

    @staticmethod
    def standaloneWhimsySpawnReminderCallback(param1):
        """Helper function for test execution."""
        print('callback function for whimsy spawn reminder was triggered with param ' + str(param1))
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS[param1].release()

    async def testStandaloneReminders_WhimsyShop(self):
        """Test creating and managing whimsy shop reminders."""
        # First a fast test that ensures callbacks are executed as expected and parameters are passed.
        WotvBotIntegrationTests.cleanupStandaloneReminders()
        reminders = Reminders(WotvBotIntegrationTests.STANDALONE_TEST_REMINDERS_PATH)
        reminders.start()
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-nrg'].acquire()
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-spawn'].acquire()
        reminders.addWhimsyReminder('foo',
            WotvBotIntegrationTests.standaloneWhimsyNrgReminderCallback, {'whimsy-nrg'},
            WotvBotIntegrationTests.standaloneWhimsySpawnReminderCallback, {'whimsy-spawn'},
            nrg_time_ms_override=1000,
            spawn_time_ms_override=2000)
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-nrg'].acquire()
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-spawn'].acquire()
        scheduled_reminders = reminders.getWhimsyReminders('foo')
        assert scheduled_reminders['nrg'] is None
        assert scheduled_reminders['spawn'] is None

        # Now add longer-time (30m, 60m) reminders and test that they are retrievable
        reminders.addWhimsyReminder('bar',
            WotvBotIntegrationTests.standaloneWhimsyNrgReminderCallback, {'whimsy-nrg'},
            WotvBotIntegrationTests.standaloneWhimsySpawnReminderCallback, {'whimsy-spawn'})
        scheduled_reminders = reminders.getWhimsyReminders('bar')
        assert scheduled_reminders['nrg'] is not None
        assert scheduled_reminders['spawn'] is not None

        # Halt the reminders system.
        reminders.stop()

    async def testStandaloneReminders_WorksAcrossBotRestart(self):
        """Tests that shutting down the reminders subsystem and bringing it back up will not cancel reminders."""
        WotvBotIntegrationTests.cleanupStandaloneReminders()
        reminders = Reminders(WotvBotIntegrationTests.STANDALONE_TEST_REMINDERS_PATH)
        reminders.start()
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-nrg'].acquire()
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-spawn'].acquire()
        print('scheduling reminders and halting the reminders service prematurely')
        # Schedule for 5s from now, then stop the reminders system.
        reminders.addWhimsyReminder('foo',
            WotvBotIntegrationTests.standaloneWhimsyNrgReminderCallback, {'whimsy-nrg'},
            WotvBotIntegrationTests.standaloneWhimsySpawnReminderCallback, {'whimsy-spawn'},
            nrg_time_ms_override=5000,
            spawn_time_ms_override=5100)
        reminders.stop()
        time.sleep(1)
        print('restarting reminders system and waiting for tasks that were scheduled previously')
        reminders = Reminders(WotvBotIntegrationTests.STANDALONE_TEST_REMINDERS_PATH)
        reminders.start()
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-nrg'].acquire()
        WotvBotIntegrationTests.__STANDALONE_REMINDER_CALLBACKS['whimsy-spawn'].acquire()

        # Halt the reminders system.
        reminders.stop()

    @staticmethod
    def cooldown(time_secs: int=30):
        """Wait for Google Sheets API to cool down (max request rate is 100 requests per 100 seconds), with a nice countdown timer printed."""
        for i in range (time_secs, 0, -1):
            print('>>> Google API cooldown pause (' + str(time_secs) + 's): ' + str(i) + '...', end='\r', flush=True)
            time.sleep(1)
        print('\n>>> Google API cooldown pause completed, moving on.')

    async def runDataFileTests(self):
        """Run only the data file tests. These are all local-execution only."""
        print('>>> Test: testDataFiles_ParseDataDump')
        await self.testDataFiles_ParseDataDump()
        print('>>> Test: testDataFileSearchUtils_findUnitWithSkillName')
        await self.testDataFileSearchUtils_findUnitWithSkillName()
        print('>>> Test: testDataFileSearchUtils_findUnitWithSkillDescription')
        await self.testDataFileSearchUtils_findUnitWithSkillDescription()
        print('>>> Test: testCommand_SkillsByName')
        await self.testCommand_SkillsByName()
        print('>>> Test: testCommand_SkillsByDescription')
        await self.testCommand_SkillsByDescription()
        print('>>> Test: testDataFileSearchUtils_findUnitWithJobName')
        await self.testDataFileSearchUtils_findUnitWithJobName()
        print('>>> Test: testDataFileSearchUtils_findUnitWithRarity')
        await self.testDataFileSearchUtils_findUnitWithRarity()
        print('>>> Test: testDataFileSearchUtils_findUnitWithElement')
        await self.testDataFileSearchUtils_findUnitWithElement()
        print('>>> Test: testDataFileSearchUtils_RichUnitSearch')
        await self.testDataFileSearchUtils_RichUnitSearch()

    async def runRemindersTests(self):
        """Run only the reminders tests. These are all local-execution only."""
        print('>>> Test: testStandaloneReminders_WhimsyShop')
        await self.testStandaloneReminders_WhimsyShop()
        print('>>> Test: testStandaloneReminders_WorksAcrossBotRestart (takes a little while)')
        await self.testStandaloneReminders_WorksAcrossBotRestart()
        print('>>> Test: testBotReminders_WhimsyShop')
        await self.testCommand_WhimsyShop()

    async def runLocalTests(self):
        """Run only tests that do not require any network access. AKA fast tests :)"""
        await self.runDataFileTests()
        await self.runRemindersTests()
        print('>>> Test: testCommand_Help')
        await self.testCommand_Help()
        print('>>> Test: testVisionCardOcrUtils_ExtractVisionCardFromScreenshot')
        await self.testVisionCardOcrUtils_ExtractVisionCardFromScreenshot()
        print('>>> Test: testCommand_WhoAmI')
        await self.testCommand_WhoAmI() # Doesn't call remote APIs, no cooldown required.

    async def runAllTests(self):
        """Run all tests in the integration test suite."""
        await self.runLocalTests()
        await self.runNetworkEnabledTests()

    async def runNetworkEnabledTests(self):
        """Run tests that require network access."""
        print('>>> Test: testAdminUtils_AddUser')
        await self.testAdminUtils_AddUser()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testResonanceManager_AddUser')
        await self.testResonanceManager_AddUser()
        WotvBotIntegrationTests.cooldown()

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
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testCommand_ResSet')
        await self.testCommand_ResSet()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testCommand_Res')
        await self.testCommand_Res()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testCommand_VcSet')
        await self.testCommand_VcSet()
        WotvBotIntegrationTests.cooldown()

        print('>>> Test: testCommand_VcAbility')
        await self.testCommand_VcAbility()

    # For testing channel message stuff, primarily reminders.
    __TEST_CHANNEL_MESSAGE_QUEUE: queue.Queue = queue.Queue()

    @staticmethod
    def sendToTestChannel(content: str):
        """Mock version of discord channel.send"""
        WotvBotIntegrationTests.__TEST_CHANNEL_MESSAGE_QUEUE.put(content)

    @staticmethod
    def readFromTestChannel() -> str:
        """Read the next message from the __TEST_CHANNEL_MESSAGE_QUEUE"""
        return str(WotvBotIntegrationTests.__TEST_CHANNEL_MESSAGE_QUEUE.get())

    @staticmethod
    def clearTestChannel():
        """Wipe the existing test message queue."""
        WotvBotIntegrationTests.__TEST_CHANNEL_MESSAGE_QUEUE = queue.Queue()

if __name__ == "__main__":
    if os.path.exists(WotvBotIntegrationTests.BOT_TEST_REMINDERS_PATH):
        os.remove(WotvBotIntegrationTests.BOT_TEST_REMINDERS_PATH)
    if os.path.exists(WotvBotIntegrationTests.STANDALONE_TEST_REMINDERS_PATH):
        os.remove(WotvBotIntegrationTests.STANDALONE_TEST_REMINDERS_PATH)
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
    _config.reminders = Reminders(WotvBotIntegrationTests.BOT_TEST_REMINDERS_PATH)
    _config.reminders.start()
    # Set up fake handlers for static callbacks for reminders...
    fake_channel = types.SimpleNamespace()
    fake_channel.id = WotvBotIntegrationTests.TEST_CHANNEL_ID
    fake_channel.send = lambda content : WotvBotIntegrationTests.sendToTestChannel(content)
    _config.discord_client.get_channel = lambda channel_id: fake_channel

    # And off we go!
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
