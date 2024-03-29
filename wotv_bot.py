"""The runtime heart of the WOTV Bot."""
from __future__ import annotations
from dataclasses import dataclass
from gc import unfreeze
import io
from re import Match
from typing import List

import discord

from admin_utils import AdminUtils
from data_files import DataFiles
from data_file_search_utils import DataFileSearchUtils, UnitSkillSearchResult, UnitJobSearchResult, UnitSearchResult
from data_file_core_classes import WotvUnit
from esper_resonance_manager import EsperResonanceManager
from leaderboard_manager import LeaderboardManager
from predictions import Predictions
from reminders import Reminders
from rolling import DiceSpec, Rolling
from vision_card_ocr_utils import VisionCardOcrUtils
from vision_card_manager import VisionCardManager
from weekly_event_schedule import WeeklyEventSchedule
from wotv_bot_common import ExposableException
from wotv_bot_constants import WotvBotConstants

class DiscordSafeException(ExposableException):
    """An exception whose error text is safe to show in Discord."""
    def __init__(self, message):
        super(DiscordSafeException, self).__init__(message)
        self.message = message

@dataclass
class WotvBotConfig:
    """Configuration for a single instance of the bot. All fields are required to be set.

    access_control_spreadsheet_id: the ID of the spreadsheet where access controls are kept
    esper_resonance_spreadsheet_id: the ID of the spreadsheet where esper resonance is tracked
    sandbox_esper_resonance_spreadsheet_id: the ID of the sandbox alternative to the real esper_resonance_spreadsheet_id
    vision_card_spreadsheet_id: the ID of the spreadsheet where vision cards are tracked
    leaderboard_spreadsheet_id: the ID of the spreadsheet where leaderboards are tracked
    spreadsheet_app: the Google spreadsheets Resource obtained from calling the spreadsheets() method on a Service Resource.
    discord_client: the Discord client
    data_files: the WotV data dump.
    reminders: the reminders subsystem.
    """
    access_control_spreadsheet_id: str = None
    esper_resonance_spreadsheet_id: str = None
    sandbox_esper_resonance_spreadsheet_id: str = None
    vision_card_spreadsheet_id: str = None
    leaderboard_spreadsheet_id: str = None
    spreadsheet_app = None
    discord_client: discord.Client = None
    data_files: DataFiles = None
    reminders: Reminders = None

@dataclass
class CommandContextInfo:
    """Context information for the command that is being executed."""
    from_name: str = None # Convenience
    from_id: str = None # Convenience
    from_discrim: str = None # Convenience
    original_message: discord.Message = None # For unusual use cases
    esper_resonance_manager: EsperResonanceManager = None
    vision_card_manager: VisionCardManager = None
    leaderboard_manager: LeaderboardManager = None
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
        """Assign the specified esper resonance manager and return a reference to this object."""
        self.esper_resonance_manager = esper_resonance_manager
        return self

    def withVisionCardManager(self, vision_card_manager: VisionCardManager) -> CommandContextInfo:
        """Assign the specified vision card manager and return a reference to this object."""
        self.vision_card_manager = vision_card_manager
        return self

    def withLeaderboardManager(self, leaderboard_manager: LeaderboardManager) -> CommandContextInfo:
        """Assign the specified leaderboard manager and return a reference to this object."""
        self.leaderboard_manager = leaderboard_manager
        return self

    def withMatch(self, the_match: Match) -> CommandContextInfo:
        """Assign the specified match and return a reference to this object."""
        self.command_match = the_match
        return self

class WotvBot:
    """An instance of the bot, configured to manage specific spreadsheets and using Discord and Google credentials."""

    # The static instance of the bot, not for general consumption.
    __staticInstance: WotvBot = None

    def __init__(self, wotv_bot_config: WotvBotConfig):
        self.wotv_bot_config = wotv_bot_config
        # Set this to true in an integration test to allow a local filesystem path to be used in a Discord
        # message as the source of the image to be processed by OCR for Vision Card text extraction. For
        # obvious security reasons, this is false by default.
        self.INTEG_TEST_LOCAL_FILESYSTEM_READ_FOR_VISION_CARD = False
        # Set the static instance of the bot to this instance.
        WotvBot.__staticInstance = self
        self.whimsy_shop_nrg_reminder_delay_ms: int = 30*60*1000 # 30 minutes
        self.whimsy_shop_spawn_reminder_delay_ms: int = 60*60*1000 # 60 minutes
        self.predictions = Predictions('predictions.txt')
        self.predictions.refreshPredictions()
        self.last_status = None # Last status set

    @staticmethod
    def getStaticInstance():
        """Returns an unsafe static reference to the "current" bot, if there is one. In reality this is just the most recently-created bot.

        Use with extreme caution. This is primarily intended for internal use cases where a static method is required, such as the callback
        for a "apscheduler"-module task such as a reminder that is being invoked asynchronously and potentially across different instances of
        the bot process where the specific instance of the bot is irrelevant.
        """
        return WotvBot.__staticInstance

    async def handleMessage(self, message: discord.Message):
        """Process the request and produce a response."""
        # Bail out early if anything looks insane.
        if message.author == self.wotv_bot_config.discord_client.user:
            return (None, None)
        if not message.content:
            return (None, None)
        if not message.content.startswith('!'):
            return (None, None)
        for ignore_pattern in WotvBotConstants.ALL_IGNORE_PATTERNS:
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

        # TODO: Hold these references longer after cleaning up the rest of the code, in an application context.
        esper_resonance_manager = EsperResonanceManager(
            self.wotv_bot_config.esper_resonance_spreadsheet_id,
            self.wotv_bot_config.sandbox_esper_resonance_spreadsheet_id,
            self.wotv_bot_config.access_control_spreadsheet_id,
            self.wotv_bot_config.spreadsheet_app)
        vision_card_manager = VisionCardManager(
            self.wotv_bot_config.vision_card_spreadsheet_id,
            self.wotv_bot_config.access_control_spreadsheet_id,
            self.wotv_bot_config.spreadsheet_app)
        leaderboard_manager = LeaderboardManager(
            self.wotv_bot_config.leaderboard_spreadsheet_id,
            self.wotv_bot_config.access_control_spreadsheet_id,
            self.wotv_bot_config.spreadsheet_app)

        # To support multi-line commands, we only match the command itself against the first line.
        first_line_lower = message.content.splitlines()[0].lower()

        match = WotvBotConstants.RES_FETCH_SELF_PATTERN.match(first_line_lower)
        if match:
            return self.handleTargetedResonanceLookupForSelf(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

        match = WotvBotConstants.RES_LIST_SELF_PATTERN.match(first_line_lower)
        if match:
            return self.handleGeneralResonanceLookupForSelf(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

        match = WotvBotConstants.RES_FETCH_OTHER_PATTERN.match(first_line_lower)
        if match:
            return self.handleTargetedResonanceLookupForOtherUser(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

        match = WotvBotConstants.RES_SET_PATTERN.match(first_line_lower)
        if match:
            return self.handleResonanceSet(context.shallowCopy().withMatch(match).withEsperResonanceManager(esper_resonance_manager))

        match = WotvBotConstants.LEADERBOARD_SET_PATTERN.match(first_line_lower)
        if match:
            return self.handleLeaderboardSet(context.shallowCopy().withMatch(match).withLeaderboardManager(leaderboard_manager))

        if WotvBotConstants.VISION_CARD_SET_PATTERN.match(first_line_lower):
            return await self.handleVisionCardSet(context.shallowCopy().withVisionCardManager(vision_card_manager))

        match = WotvBotConstants.VISION_CARD_FETCH_BY_NAME_PATTERN.match(first_line_lower)
        if match:
            return await self.handleVisionCardFetchByName(context.shallowCopy().withMatch(match).withVisionCardManager(vision_card_manager))

        match = WotvBotConstants.VISION_CARD_ABILITY_SEARCH.match(first_line_lower)
        if match:
            return await self.handleVisionCardAbilitySearch(context.shallowCopy().withMatch(match).withVisionCardManager(vision_card_manager))

        if WotvBotConstants.VISION_CARD_DEBUG_PATTERN.match(first_line_lower):
            return await self.handleVisionCardDebug(context.shallowCopy().withVisionCardManager(vision_card_manager))

        match = WotvBotConstants.FIND_SKILLS_BY_NAME_PATTERN.match(first_line_lower)
        if match:
            return await self.handleFindSkillsByName(context.shallowCopy().withMatch(match))

        match = WotvBotConstants.FIND_SKILLS_BY_DESCRIPTION_PATTERN.match(first_line_lower)
        if match:
            return await self.handleFindSkillsByDescription(context.shallowCopy().withMatch(match))

        match = WotvBotConstants.RICH_UNIT_SEARCH_PATTERN.match(first_line_lower)
        if match:
            return await self.handleRichUnitSearch(context.shallowCopy().withMatch(match))

        match = WotvBotConstants.WHIMSY_REMINDER_PATTERN.match(first_line_lower)
        if match:
            return await self.handleWhimsyReminder(context.shallowCopy().withMatch(match))

        match = WotvBotConstants.ROLLDICE_PATTERN.match(first_line_lower)
        if match:
            return await self.handleRoll(context.shallowCopy().withMatch(match))

        # Predictions
        match = WotvBotConstants.PREDICTION_PATTERN_1.match(first_line_lower)
        if match:
            return await self.handlePrediction(context.shallowCopy().withMatch(match))
        match = WotvBotConstants.PREDICTION_PATTERN_2.match(first_line_lower)
        if match:
            return await self.handlePrediction(context.shallowCopy().withMatch(match))
        match = WotvBotConstants.PREDICTION_PATTERN_3.match(first_line_lower)
        if match:
            return await self.handlePrediction(context.shallowCopy().withMatch(match))
        match = WotvBotConstants.PREDICTION_PATTERN_4.match(first_line_lower)
        if match:
            return await self.handlePrediction(context.shallowCopy().withMatch(match))

        match = WotvBotConstants.DOUBLE_DROP_RATES_SCHEDULE_PATTERN_1.match(first_line_lower)
        if match:
            return await self.handleSchedule(context.shallowCopy().withMatch(match))

        match = WotvBotConstants.DOUBLE_DROP_RATES_SCHEDULE_PATTERN_2.match(first_line_lower)
        if match:
            return await self.handleMats(context.shallowCopy().withMatch(match))

        match = WotvBotConstants.DAILY_REMINDERS.match(first_line_lower)
        if match:
            return await self.handleDailyReminders(context.shallowCopy().withMatch(match))

        # Hidden utility command to look up the snowflake ID of your own user. This isn't secret or insecure, but it's also not common, so it isn't listed.
        if first_line_lower.startswith('!whoami'):
            return self.handleWhoAmI(context)

        # Hidden utility command to look up the snowflake ID of a member. This isn't secret or insecure, but it's also not common, so it isn't listed.
        match = WotvBotConstants.WHOIS_PATTERN.match(first_line_lower)
        if match:
            return await self.handleWhoIs(context.shallowCopy().withMatch(match))

        if WotvBotConstants.ADMIN_ADD_ESPER_PATTERN.match(first_line_lower) or WotvBotConstants.SANDBOX_ADMIN_ADD_ESPER_PATTERN.match(message.content):
            return self.handleAdminAddEsper(context.shallowCopy().withEsperResonanceManager(esper_resonance_manager))

        if WotvBotConstants.ADMIN_ADD_UNIT_PATTERN.match(first_line_lower) or WotvBotConstants.SANDBOX_ADMIN_ADD_UNIT_PATTERN.match(message.content):
            return self.handleAdminAddUnit(context.shallowCopy().withEsperResonanceManager(esper_resonance_manager))

        if WotvBotConstants.ADMIN_ADD_VC_PATTERN.match(first_line_lower):
            return self.handleAdminAddVisionCard(context.shallowCopy().withVisionCardManager(vision_card_manager))

        if WotvBotConstants.ADMIN_ADD_USER_PATTERN.match(first_line_lower):
            return self.handleAdminAddUser(context.shallowCopy().withEsperResonanceManager(esper_resonance_manager).withVisionCardManager(vision_card_manager))

        if first_line_lower.startswith('!resonance'):
            responseText = '<@{0}>: Invalid !resonance command. Use !help for more information.'.format(from_id)
            return (responseText, None)

        if first_line_lower.startswith('!help'):
            responseText = WotvBotConstants.HELP.format(self.wotv_bot_config.esper_resonance_spreadsheet_id, self.wotv_bot_config.vision_card_spreadsheet_id, self.wotv_bot_config.leaderboard_spreadsheet_id)
            return (responseText, None)

        return ('<@{0}>: Invalid or unknown command. Use !help to see all supported commands and !admin-help to see special admin commands. '\
                'Please do this via a direct message to the bot, to avoid spamming the channel.'.format(from_id), None)

    def handleTargetedResonanceLookupForSelf(self, context: CommandContextInfo) -> (str, str):
        """Handle !res command for self-lookup of a specific (unit, esper) tuple."""
        unit_name = context.command_match.group(1).strip()
        esper_name = context.command_match.group(2).strip()
        print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (
            context.from_name, context.from_discrim, context.from_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = context.esper_resonance_manager.readResonance(None, context.from_id, unit_name, esper_name)
        responseText = '<@{0}>: {1}/{2} has resonance {3}'.format(context.from_id, pretty_unit_name, pretty_esper_name, resonance)
        return (responseText, None)

    def handleTargetedResonanceLookupForOtherUser(self, context: CommandContextInfo) -> (str, str):
        """Handle !res command for lookup of a specific (unit, esper) tuple for a different user."""
        target_user_name = context.command_match.group(1).strip()
        unit_name = context.command_match.group(2).strip()
        esper_name = context.command_match.group(3).strip()
        print('resonance fetch from user %s#%s, for user %s, for unit %s, for esper %s' % (
            context.from_name, context.from_discrim, target_user_name, unit_name, esper_name))
        resonance, pretty_unit_name, pretty_esper_name = context.esper_resonance_manager.readResonance(target_user_name, None, unit_name, esper_name)
        responseText = '<@{0}>: for user {1}, {2}/{3} has resonance {4}'.format(
            context.from_id, target_user_name, pretty_unit_name, pretty_esper_name, resonance)
        return (responseText, None)

    def handleGeneralResonanceLookupForSelf(self, context: CommandContextInfo) -> (str, str):
        """Handle !res command for self-lookup of all resonance for a given unit or esper."""
        target_name = context.command_match.group('target_name').strip()
        print('resonance list fetch from user %s#%s, for target %s' % (context.from_name, context.from_discrim, target_name))
        pretty_name, resonance_listing = context.esper_resonance_manager.readResonanceList(None, context.from_id, target_name)
        responseText = '<@{0}>: resonance listing for {1}:\n{2}'.format(context.from_id, pretty_name, resonance_listing)
        return (responseText, None)

    def handleResonanceSet(self, context: CommandContextInfo) -> (str, str):
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

    def handleLeaderboardSet(self, context: CommandContextInfo) -> (str, str):
        """Handle !leaderboard-set command to record score for a category, with an optional proof URL."""
        category_fuzzy = context.command_match.group('category').strip()
        value = context.command_match.group('value').strip()
        proof_url = None
        if context.command_match.group('proof_url'):
            original_match = WotvBotConstants.LEADERBOARD_SET_PATTERN.match(context.original_message.content) # Fetch original-case URL if it is present
            proof_url = original_match.group('proof_url')
        elif context.original_message.attachments and len(context.original_message.attachments) == 1:
            proof_url = context.original_message.attachments[0].url
        print('leaderboard set from user %s#%s, for category %s, value %s, proof_url %s' % (
            context.from_name, context.from_discrim, category_fuzzy, value, proof_url))
        old_value, category_name = context.leaderboard_manager.setCurrentRankedValue(user_id=context.from_id, ranked_column_name=category_fuzzy, value=value, proof_url=proof_url)
        responseText = '<@{0}>: score for category {1} has been set to {2} (was: {3})'.format(context.from_id, category_name, value, old_value)
        reaction = '\U00002705'  # CLDR: check mark button
        return (responseText, reaction)

    def handleWhoAmI(self, context: CommandContextInfo) -> (str, str):
        """Handle !whoami command to fetch your own snowflake ID."""
        responseText = '<@{id}>: Your snowflake ID is {id}'.format(id=context.from_id)
        return (responseText, None)

    async def handleWhoIs(self, context: CommandContextInfo) -> (str, str):
        """Handle !whois command to fetch the snowflake ID for a given user."""
        original_match = WotvBotConstants.WHOIS_PATTERN.match(context.original_message.content) # Fetch original-case name
        target_member_name = original_match.group('server_handle').strip()
        # As of December 2020, possibly earlier, the following line no longer works:
        # members = context.original_message.guild.members
        # Instead have to fetch the list from the server, and enable the "SERVER MEMBERS INTENT" permission in the bot admin page on Discord.
        members = await context.original_message.guild.fetch_members(limit=1000).flatten()
        for member in members:
            if member.name == target_member_name:
                responseText = '<@{0}>: the snowflake ID for {1} is {2}'.format(context.from_id, target_member_name, member.id)
                return (responseText, None)
        responseText = '<@{0}>: no such member {1}'.format(context.from_id, target_member_name)
        return (responseText, None)

    def handleAdminAddEsper(self, context: CommandContextInfo) -> (str, str):
        """Handle !admin-add-esper and !sandbox-admin-add-esper commands to add a new esper to the resonance tracker."""
        sandbox = True
        match = WotvBotConstants.ADMIN_ADD_ESPER_PATTERN.match(context.original_message.content)
        if match:
            sandbox = False
        else:
            match = WotvBotConstants.SANDBOX_ADMIN_ADD_ESPER_PATTERN.match(context.original_message.content)
        esper_name = match.group('name').strip()
        esper_url = match.group('url').strip()
        left_or_right_of = match.group('left_or_right_of').strip()
        column = match.group('column').strip()
        print('esper add (sandbox mode={6}) from user {0}#{1}, for esper {2}, url {3}, position {4}, column {5}'.format(
            context.from_name, context.from_discrim, esper_name, esper_url, left_or_right_of, column, sandbox))
        context.esper_resonance_manager.addEsperColumn(context.from_id, esper_name, esper_url, left_or_right_of, column, sandbox)
        responseText = '<@{0}>: Added esper {1}!'.format(context.from_id, esper_name)
        return (responseText, None)

    def handleAdminAddUnit(self, context: CommandContextInfo) -> (str, str):
        """Handle !admin-add-unit and !sandbox-admin-add-unit commands to add a new unit to the resonance tracker."""
        sandbox = True
        match = WotvBotConstants.ADMIN_ADD_UNIT_PATTERN.match(context.original_message.content)
        if match:
            sandbox = False
        else:
            match = WotvBotConstants.SANDBOX_ADMIN_ADD_UNIT_PATTERN.match(context.original_message.content)
        unit_name = match.group('name').strip()
        unit_url = match.group('url').strip()
        above_or_below = match.group('above_or_below').strip()
        row1Based = match.group('row1Based').strip()
        print('unit add (sandbox mode={6}) from user {0}#{1}, for unit {2}, url {3}, position {4}, row {5}'.format(
            context.from_name, context.from_discrim, unit_name, unit_url, above_or_below, row1Based, sandbox))
        context.esper_resonance_manager.addUnitRow(context.from_id, unit_name, unit_url, above_or_below, row1Based, sandbox)
        responseText = '<@{0}>: Added unit {1}!'.format(context.from_id, unit_name)
        return (responseText, None)

    def handleAdminAddVisionCard(self, context: CommandContextInfo) -> (str, str):
        """Handle !admin-add-vc command to add a new vision card."""
        match = WotvBotConstants.ADMIN_ADD_VC_PATTERN.match(context.original_message.content)
        card_name = match.group('name').strip()
        card_url = match.group('url').strip()
        above_or_below = match.group('above_or_below').strip()
        row1Based = match.group('row1Based').strip()
        print('vc add from user {0}#{1}, for card {2}, url {3}, position {4}, row {5}'.format(
            context.from_name, context.from_discrim, card_name, card_url, above_or_below, row1Based))
        context.vision_card_manager.addVisionCardRow(context.from_id, card_name, card_url, above_or_below, row1Based)
        responseText = '<@{0}>: Added card {1}!'.format(context.from_id, card_name)
        return (responseText, None)

    def handleAdminAddUser(self, context: CommandContextInfo) -> (str, str):
        """Handle !admin-add-user command to add a new unit to the resonance tracker and the administrative spreadsheet."""
        if not AdminUtils.isAdmin(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, context.from_id):
            raise ExposableException('You do not have permission to add a user.')
        match = WotvBotConstants.ADMIN_ADD_USER_PATTERN.match(context.original_message.content)
        snowflake_id = match.group('snowflake_id').strip()
        nickname = match.group('nickname').strip()
        user_type = match.group('user_type').strip().lower()
        is_admin = False
        if user_type == 'admin':
            is_admin = True
        print('user add from user {0}#{1}, for snowflake_id {2}, nickname {3}, is_admin {4}'.format(
            context.from_name, context.from_discrim, snowflake_id, nickname, is_admin))
        AdminUtils.addUser(self.wotv_bot_config.spreadsheet_app, self.wotv_bot_config.access_control_spreadsheet_id, nickname, snowflake_id, is_admin)
        context.esper_resonance_manager.addUser(nickname)
        context.vision_card_manager.addUser(nickname)
        responseText = '<@{0}>: Added user {1}!'.format(context.from_id, nickname)
        return (responseText, None)

    async def handleVisionCardDebug(self, context: CommandContextInfo) -> (str, str):
        """Handle !xocr and !xocr-debug commands to perform OCR on a Vision Card."""
        return await self.handleVisionCardSet(context, is_debug=True)

    async def handleVisionCardSet(self, context: CommandContextInfo, is_debug: bool = False) -> (str, str):
        """Handle !vc-set"""
        # Try to extract text from a vision card screenshot that is sent as an attachment to this message.
        url = context.original_message.attachments[0].url
        print('Vision Card OCR request from user %s#%s, for url %s' % (context.from_name, context.from_discrim, url))
        screenshot = None
        if self.INTEG_TEST_LOCAL_FILESYSTEM_READ_FOR_VISION_CARD:
            screenshot = VisionCardOcrUtils.loadScreenshotFromFilesystem(url)
        else:
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
            # Print errors to the console, but do not return them as we cannot guarantee that there is no sensitive
            # information in here, such as possible library exceptions, i/o exceptions, etceteras.
            if vision_card.error_messages is not None and len(vision_card.error_messages) > 0:
                print('errors found during vision card conversion: ' + str(vision_card.error_messages))
        reaction = None
        if vision_card.successfully_extracted is True:
            responseText = '<@{0}>: {1}'.format(context.from_id, vision_card.prettyPrint())
            if not is_debug:
                context.vision_card_manager.setVisionCard(context.from_id, vision_card)
            reaction = '\U00002705'  # CLDR: check mark button
        else:
            responseText = '<@{0}>: Vision card extraction has failed. You may try again with !vc-debug for a clue about what has gone wrong'.format(
                context.from_id)
        return (responseText, reaction)

    async def handleVisionCardFetchByName(self, context: CommandContextInfo) -> (str, str):
        """Handle !vc command for self-lookup of a given vision card by name"""
        target_name = context.command_match.group('target_name').strip()
        print('vision card fetch from user %s#%s, for target %s' % (context.from_name, context.from_discrim, target_name))
        vision_card = context.vision_card_manager.readVisionCardByName(None, context.from_id, target_name)
        responseText = '<@{0}>: Vision Card:\n{1}'.format(context.from_id, str(vision_card.prettyPrint()))
        return (responseText, None)

    async def handleVisionCardAbilitySearch(self, context: CommandContextInfo) -> (str, str):
        """Handle !vc-ability command for self-lookup of a given vision card by party/bestowed ability fuzzy-match"""
        search_text = context.command_match.group('search_text').strip()
        print('vision card ability search from user %s#%s, for text %s' % (context.from_name, context.from_discrim, search_text))
        vision_cards = context.vision_card_manager.searchVisionCardsByAbility(None, context.from_id, search_text)
        if len(vision_cards) == 0:
            responseText = '<@{0}>: No vision cards matched the ability search.'.format(context.from_id)
            return (responseText, None)
        responseText = '<@{0}>: Matching Vision Cards:\n'.format(context.from_id)
        for vision_card in vision_cards:
            responseText += '  ' + vision_card.Name + '\n'
            responseText += '    Party Ability: ' + vision_card.PartyAbility + '\n'
            for bestowed_effect in vision_card.BestowedEffects:
                responseText += '    Bestowed Effect: ' + bestowed_effect + '\n'
        return (responseText, None)

    @staticmethod
    def rarityAndElementParenthetical(unit: WotvUnit) -> str:
        """Generate a parenthetical string with the unit's rarity and element(s)"""
        text = '(' + str(unit.rarity) + ' rarity, '
        if not unit.elements:
            return text + 'no element)'
        text += unit.elements[0]
        if len(unit.elements) > 1:
            for element in unit.elements[1:]:
                text += '/' + str(element)
        text += ' element'
        if len(unit.elements) > 1:
            text += 's'
        return text + ')'

    def prettyPrintUnitSkillSearchResult(self, result: UnitSkillSearchResult):
        """Print a useful, human-readable description of the skill match including the unit name, element, rarity, the skill name,
           and how the skill is unlocked."""
        if result.is_master_ability:
            return 'Master ability for ' + result.unit.name + ' ' + WotvBot.rarityAndElementParenthetical(result.unit) + ': ' + result.skill.description
        if result.is_limit_burst:
            return 'Limit burst (' + result.skill.name + ') for ' + result.unit.name + ' ' + WotvBot.rarityAndElementParenthetical(result.unit) + ': ' + result.skill.description
        text = 'Skill "' + result.skill.name + '" learned by ' + result.unit.name
        text += ' ' + WotvBot.rarityAndElementParenthetical(result.unit)
        text += ' with job ' + result.board_skill.unlocked_by_job.name + ' at job level ' + str(result.board_skill.unlocked_by_job_level)
        text += ': ' + result.skill.description
        return text

    def prettyPrintUnitJobSearchResult(self, result: UnitJobSearchResult):
        """Print a useful, human-readable description of the job match including the unit name, element, rarity, and job name."""
        text = 'Job "' + result.job.name + '" learned by ' + result.unit.name
        text += ' ' + WotvBot.rarityAndElementParenthetical(result.unit)
        return text

    def prettyPrintUnitSearchResult(self, result: UnitSearchResult):
        """Print a useful, human-readable description of any search result, as appropriate to the type."""
        if hasattr(result, 'is_master_ability'):
            return self.prettyPrintUnitSkillSearchResult(result)
        elif hasattr(result, 'job'):
            return self.prettyPrintUnitJobSearchResult(result)
        else:
            return result.unit.name + ' ' + WotvBot.rarityAndElementParenthetical(result.unit)

    @staticmethod
    def getExtraCommandLines(context: CommandContextInfo):
        """Extract all extra non-empty lines from a command and return them as a list."""
        lines = context.original_message.content.splitlines()
        extra_lines = []
        if len(lines) > 1:
            for line in lines[1:]:
                line = line.strip()
                if line:
                    extra_lines.append(line)
        return extra_lines

    # Deprecated - Use rich unit search instead, e.g. "!unit-search skill-name <search_text>"
    async def handleFindSkillsByName(self, context: CommandContextInfo) -> (str, str):
        """Handle !skills-by-name command"""
        search_text = context.command_match.group('search_text').strip()
        print('skills-by-name search from user %s#%s, for text %s' % (context.from_name, context.from_discrim, search_text))
        refinements = WotvBot.getExtraCommandLines(context)
        if len(refinements) > 0:
            print('  refinements: ' + str(refinements))
        results = DataFileSearchUtils.richUnitSearch(self.wotv_bot_config.data_files, 'skill-name', search_text, refinements)
        if len(results) == 0:
            responseText = '<@{0}>: No skills matched the search.'.format(context.from_id)
            return (responseText, None)
        responseText = '<@{0}>: Matching Skills:\n'.format(context.from_id)
        results = sorted(results, key=lambda one_result : one_result.unit.name)
        truncated = False
        if len(results) > 25:
            results = results[:25]
            truncated = True
        for result in results:
            responseText += self.prettyPrintUnitSearchResult(result) + '\n'
        if truncated:
            responseText += 'Results truncated because there were too many.'
        return (responseText.strip(), None)

    # Deprecated - Use rich unit search instead, e.g. "!unit-search skill-desc <search_text>"
    async def handleFindSkillsByDescription(self, context: CommandContextInfo) -> (str, str):
        """Handle !skills-by-desc command"""
        search_text = context.command_match.group('search_text').strip()
        print('skills-by-description search from user %s#%s, for text %s' % (context.from_name, context.from_discrim, search_text))
        refinements = WotvBot.getExtraCommandLines(context)
        if len(refinements) > 0:
            print('  refinements: ' + str(refinements))
        results = DataFileSearchUtils.richUnitSearch(self.wotv_bot_config.data_files, 'skill-desc', search_text, refinements)
        if len(results) == 0:
            responseText = '<@{0}>: No skills matched the search.'.format(context.from_id)
            return (responseText, None)
        responseText = '<@{0}>: Matching Skills:\n'.format(context.from_id)
        results = sorted(results, key=lambda one_result : one_result.unit.name)
        truncated = False
        if len(results) > 25:
            results = results[:25]
            truncated = True
        for result in results:
            responseText += self.prettyPrintUnitSearchResult(result) + '\n'
        if truncated:
            responseText += 'Results truncated because there were too many.'
        return (responseText.strip(), None)

    async def handleRichUnitSearch(self, context: CommandContextInfo) -> (str, str):
        """Handle !unit-search command"""
        search_type = context.command_match.group('search_type').strip()
        search_text = None
        if search_type != 'all':
            search_text = context.command_match.group('search_text').strip()
        print('unit search from user %s#%s, type %s, text %s' % (context.from_name, context.from_discrim, search_type, search_text))
        refinements = WotvBot.getExtraCommandLines(context)
        if len(refinements) > 0:
            print('  refinements: ' + str(refinements))
        results = DataFileSearchUtils.richUnitSearch(self.wotv_bot_config.data_files, search_type, search_text, refinements)
        if len(results) == 0:
            responseText = '<@{0}>: No units matched the search.'.format(context.from_id)
            return (responseText, None)
        responseText = '<@{0}>: Results:\n'.format(context.from_id)
        results = sorted(results, key=lambda one_result : one_result.unit.name)
        truncated = False
        if len(results) > 25:
            results = results[:25]
            truncated = True
        for result in results:
            responseText += self.prettyPrintUnitSearchResult(result) + '\n'
        if truncated:
            responseText += 'Results truncated because there were too many.'
        return (responseText.strip(), None)

    @staticmethod
    async def whimsyShopNrgReminderCallback(target_channel_id: str, from_id: str):
        """Handles a reminder callback for a whimsy shop nrg reminder."""
        discord_client: discord.Client = WotvBot.getStaticInstance().wotv_bot_config.discord_client
        text_channel: discord.TextChannel = discord_client.get_channel(target_channel_id)
        #discord_client.loop.create_task(text_channel.send(content = '<@{0}>: This is your requested whimsy shop reminder: NRG spent will now start counting towards the next Whimsy Shop.'.format(from_id)))
        await text_channel.send(content = '<@{0}>: This is your requested whimsy shop reminder: NRG spent will now start counting towards the next Whimsy Shop.'.format(from_id))

    @staticmethod
    async def whimsyShopSpawnReminderCallback(target_channel_id: str, from_id: str):
        """Handles a reminder callback for a whimsy shop spawn reminder."""
        discord_client: discord.Client = WotvBot.getStaticInstance().wotv_bot_config.discord_client
        text_channel: discord.TextChannel = discord_client.get_channel(target_channel_id)
        #discord_client.loop.create_task(text_channel.send(content = '<@{0}>: This is your requested whimsy shop reminder: The Whimsy Shop is ready to spawn again.'.format(from_id)))
        await text_channel.send(content = '<@{0}>: This is your requested whimsy shop reminder: The Whimsy Shop is ready to spawn again.'.format(from_id))

    async def handleWhimsyReminder(self, context: CommandContextInfo) -> (str, str):
        """Handle !whimsy command for a whimsy reminder"""
        reminders = self.wotv_bot_config.reminders # Shorthand
        owner_id = str(context.from_id) # Shorthand
        command = '<none>'
        if context.command_match.group('command'):
            command = context.command_match.group('command').strip()
        print('Whimsy reminder request from user %s#%s, command %s' % (context.from_name, context.from_discrim, command))
        responseText = '<@{0}>: Unknown/unsupported !whimsy command. Use !help for for more information.'.format(context.from_id)
        # Default behavior - be smart. If the user has got a reminder set, don't overwrite it unless they pass set-reminder as the command.
        # If they do not have a reminder set, go ahead and set it now.
        append_overwrite_reminder_message = False # Whether or not to add some reminder text to the message
        if command == '<none>':
            # Check if an existing reminder is set. If so prompt to overwrite...
            if reminders.hasPendingWhimsyNrgReminder(owner_id) or reminders.hasPendingWhimsySpawnReminder(owner_id):
                command = 'when'
                append_overwrite_reminder_message = True # Remind the user how to overwrite the current timer.
            else:
                command = 'set-reminder' # Assume the user wants to set a reminder.
        if command == 'set-reminder':
            append_existing_canceled_message = reminders.hasPendingWhimsyNrgReminder(owner_id) or reminders.hasPendingWhimsySpawnReminder(owner_id)
            nrg_callback: callable = WotvBot.whimsyShopNrgReminderCallback
            nrg_params = [context.original_message.channel.id, owner_id]
            spawn_callback: callable = WotvBot.whimsyShopSpawnReminderCallback
            spawn_params = nrg_params
            reminders.addWhimsyReminder(context.from_name, owner_id, nrg_callback, nrg_params, spawn_callback, spawn_params,
            self.whimsy_shop_nrg_reminder_delay_ms, self.whimsy_shop_spawn_reminder_delay_ms)
            responseText = '<@{0}>: Your reminder has been set.'.format(context.from_id)
            if append_existing_canceled_message:
                responseText += ' Your previous outstanding reminder has been discarded.'
        elif command == 'when':
            if reminders.hasPendingWhimsyNrgReminder(owner_id):
                time_left_minutes = int(reminders.timeTillWhimsyNrgReminder(owner_id) / 60)
                responseText = '<@{0}>: NRG spent will start counting towards the next Whimsy Shop in about {1} minutes.'.format(owner_id, str(time_left_minutes))
                if append_overwrite_reminder_message:
                    responseText += ' To force the timer to reset to 60 minutes *immediately*, use the command "!whimsy set-reminder".'
            elif reminders.hasPendingWhimsySpawnReminder(owner_id):
                time_left_minutes = int(reminders.timeTillWhimsySpawnReminder(owner_id) / 60)
                responseText = '<@{0}>: The Whimsy Shop will be ready to spawn again in about {1} minutes.'.format(owner_id, str(time_left_minutes))
                if append_overwrite_reminder_message:
                    responseText += ' To force the timer to reset to 60 minutes *immediately*, use the command "!whimsy set-reminder".'
            else:
                responseText = '<@{0}>: You do not currently have a whimsy reminder set.'.format(context.from_id)
        elif command == 'cancel':
            reminders.cancelWhimsyReminders(owner_id)
            responseText = '<@{0}>: Any and all outstanding whimsy reminders have been canceled.'.format(context.from_id)
        return (responseText, None)

    async def handleRoll(self, context: CommandContextInfo) -> (str, str):
        """Handle !roll command to simulate a dice roll."""
        spec: DiceSpec = DiceSpec.parse(context.command_match.group('dice_spec'))
        print('Dice roll request from user %s#%s, spec %s' % (context.from_name, context.from_discrim, str(spec)))
        if spec.num_dice > 50:
            responseText = '<@{0}>: Too many dice in !roll command (max 50). Use !help for for more information.'.format(context.from_id)
        else:
            results: List[int] = Rolling.rollDice(spec)
            total = 0
            for one_roll in results:
                total += one_roll
            responseText = '<@{0}>: Rolled a total of {1}. Dice values were: {2}'.format(context.from_id, str(total), str(results))
        return (responseText.strip(), None)

    async def handlePrediction(self, context: CommandContextInfo) -> (str, str):
        """Handle !predict/astrologize/divine/foretell (etc) command to make a funny prediction."""
        query = context.command_match.group('query')
        print('Prediction request from user %s#%s, query %s' % (context.from_name, context.from_discrim, str(query)))
        responseText = '<@{0}>: {1}'.format(context.from_id, self.predictions.predict(query))
        return (responseText.strip(), None)

    async def handleSchedule(self, context: CommandContextInfo) -> (str, str):
        """Handle a request for the weekly schedule."""
        print('Schedule request from user %s#%s' % (context.from_name, context.from_discrim))
        responseText = '<@{0}>:\n{1}'.format(context.from_id, WeeklyEventSchedule.getDoubleDropRateSchedule('** >> ', ' << **'))
        return (responseText.strip(), None)

    async def handleMats(self, context: CommandContextInfo) -> (str, str):
        """Handle a request for the current double-drop rate room."""
        print('Mats request from user %s#%s' % (context.from_name, context.from_discrim))
        responseText = '<@{0}>:\n'.format(context.from_id)
        responseText += 'Today: ' + WeeklyEventSchedule.getTodaysDoubleDropRateEvents() + '\n'
        responseText += 'Tomorrow: ' + WeeklyEventSchedule.getTomorrowsDoubleDropRateEvents() + '\n'
        responseText += 'For the full schedule, use !schedule.'
        return (responseText.strip(), None)

    async def createOrResetPeriodicStatusUpdateCallback(self):
        """Create or reset the status update callback for the entire bot."""
        self.wotv_bot_config.reminders.createOrResetPeriodicStatusUpdateCallback(WotvBot.periodicStatusUpdateCallback)

    @staticmethod
    async def periodicStatusUpdateCallback():
        """Handles a callback for a periodic status update."""
        bot: WotvBot = WotvBot.getStaticInstance()
        discord_client: discord.Client = bot.wotv_bot_config.discord_client
        new_status = WeeklyEventSchedule.getTodaysDoubleDropRateEvents()
        if bot.last_status is None or bot.last_status != new_status:
            print('Updating bot status to: ' + new_status)
            # Apparently bots cannot use a custom status so gotta stick with a regular one like "Playing" (Game)
            await discord_client.change_presence(activity=discord.Game(name=new_status))
            bot.last_status = new_status

    @staticmethod
    async def dailyReminderCallback(target_channel_id: str, from_id: str, requested_reminders: List[str]):
        """Handles a reminder callback for daily reminders."""
        discord_client: discord.Client = WotvBot.getStaticInstance().wotv_bot_config.discord_client
        text_channel: discord.TextChannel = discord_client.get_channel(target_channel_id)
        reminder_text =  '<@{0}>: This is your requested daily reminder. Cancel daily reminders with "!daily-reminders none" or use "!help".'.format(from_id)
        if 'mats' in requested_reminders:
            reminder_text += '\n  Today\'s daily double rate drops are: ' + WeeklyEventSchedule.getTodaysDoubleDropRateEvents()
        await text_channel.send(content = reminder_text)

    async def handleDailyReminders(self, context: CommandContextInfo) -> (str, str):
        """Handle !daily-reminders command for various daily reminders, such as double-drop-rates"""
        reminders = self.wotv_bot_config.reminders # Shorthand
        owner_id = str(context.from_id) # Shorthand
        reminder_list_str = '<default>'
        if context.command_match.group('reminder_list'):
            reminder_list_str = context.command_match.group('reminder_list').strip()
        print('Daily reminders request from user %s#%s, reminder list %s' % (context.from_name, context.from_discrim, reminder_list_str))
        responseText = '<@{0}>: Unknown/unsupported !daily-reminders command. Use !help for for more information.'.format(context.from_id)
        requested_reminders: List[str] = reminder_list_str.split(',')
        configured_reminders_message = '<@{0}>: Your daily reminders have been configured:'.format(context.from_id)

        # Default behavior - be smart. If the user has got a reminder set, don't overwrite it unless they pass "none" as the list.
        if reminder_list_str == '<default>':
            if reminders.hasDailyReminder(owner_id):
                responseText = '<@{0}>: You have daily reminders configured. To clear them, use "!daily-reminders none".'.format(context.from_id)
            else:
                responseText = '<@{0}>: You do not currently have daily reminders configured. Use !help for more information.'.format(context.from_id)
        elif reminder_list_str == 'none':
            reminders.cancelDailyReminder(owner_id)
            responseText = '<@{0}>: Your daily reminders have been canceled.'.format(context.from_id)
        else:
            added_reminders = []
            if 'mats' in requested_reminders: 
                configured_reminders_message += '\n  daily double-drop rate reminder ("mats")'
                added_reminders.append('mats')
            callback: callable = WotvBot.dailyReminderCallback
            callback_params = [context.original_message.channel.id, owner_id, added_reminders]
            reminders.addDailyReminder(context.from_name, owner_id, callback, callback_params)
            responseText = configured_reminders_message
        return (responseText, None)
