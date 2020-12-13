"""The runtime heart of the WOTV Bot."""
from __future__ import annotations
from dataclasses import dataclass
import io
from re import Match

import discord

from admin_utils import AdminUtils
from data_files import DataFiles
from data_file_search_utils import DataFileSearchUtils, UnitSkillSearchResult
from wotv_bot_constants import WotvBotConstants
from vision_card_ocr_utils import VisionCardOcrUtils
from esper_resonance_manager import EsperResonanceManager
from vision_card_manager import VisionCardManager
from wotv_bot_common import ExposableException

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
    spreadsheet_app: the Google spreadsheets Resource obtained from calling the spreadsheets() method on a Service Resource.
    discord_client: the Discord client
    data_files: the WotV data dump.
    """
    access_control_spreadsheet_id: str = None
    esper_resonance_spreadsheet_id: str = None
    sandbox_esper_resonance_spreadsheet_id: str = None
    vision_card_spreadsheet_id: str = None
    spreadsheet_app = None
    discord_client = None
    data_files: DataFiles = None

@dataclass
class CommandContextInfo:
    """Context information for the command that is being executed."""
    from_name: str = None # Convenience
    from_id: str = None # Convenience
    from_discrim: str = None # Convenience
    original_message: str = None # For unusual use cases
    esper_resonance_manager: EsperResonanceManager = None
    vision_card_manager: VisionCardManager = None
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

    def withMatch(self, the_match: Match) -> CommandContextInfo:
        """Assign the specified match and return a reference to this object."""
        self.command_match = the_match
        return self

class WotvBot:
    """An instance of the bot, configured to manage specific spreadsheets and using Discord and Google credentials."""
    def __init__(self, wotv_bot_config: WotvBotConfig):
        self.wotv_bot_config = wotv_bot_config
        # Set this to true in an integration test to allow a local filesystem path to be used in a Discord
        # message as the source of the image to be processed by OCR for Vision Card text extraction. For
        # obvious security reasons, this is false by default.
        self.INTEG_TEST_LOCAL_FILESYSTEM_READ_FOR_VISION_CARD = False

    async def handleMessage(self, message):
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
            responseText = WotvBotConstants.HELP.format(self.wotv_bot_config.esper_resonance_spreadsheet_id, self.wotv_bot_config.vision_card_spreadsheet_id)
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

    def prettyPrintUnitSkillSearchResult(self, result: UnitSkillSearchResult):
        """Print a useful, human-readable description of the skill match including the unit name, the skill name, and how the skill is unlocked."""
        if result.is_master_ability:
            return 'Master ability for ' + result.unit.name + ': ' + result.skill.description
        text = 'Skill "' + result.skill.name + '" learned by ' + result.unit.name
        text += ' with job ' + result.board_skill.unlocked_by_job.name + ' at job level ' + str(result.board_skill.unlocked_by_job_level)
        text += ': ' + result.skill.description
        return text

    async def handleFindSkillsByName(self, context: CommandContextInfo) -> (str, str):
        """Handle !skills-by-name command"""
        search_text = context.command_match.group('search_text').strip()
        print('skills-by-name search from user %s#%s, for text %s' % (context.from_name, context.from_discrim, search_text))
        results = DataFileSearchUtils.findUnitWithSkillName(self.wotv_bot_config.data_files, search_text)
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
            responseText += self.prettyPrintUnitSkillSearchResult(result) + '\n'
        if truncated:
            responseText += 'Results truncated because there were too many.'
        return (responseText.strip(), None)

    async def handleFindSkillsByDescription(self, context: CommandContextInfo) -> (str, str):
        """Handle !skills-by-desc command"""
        search_text = context.command_match.group('search_text').strip()
        print('skills-by-description search from user %s#%s, for text %s' % (context.from_name, context.from_discrim, search_text))
        results = DataFileSearchUtils.findUnitWithSkillDescription(self.wotv_bot_config.data_files, search_text)
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
            responseText += self.prettyPrintUnitSkillSearchResult(result) + '\n'
        if truncated:
            responseText += 'Results truncated because there were too many.'
        return (responseText.strip(), None)
