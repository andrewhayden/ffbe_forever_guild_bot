"""Constants used by the WOTV Bot"""
import re

class WotvBotConstants:
    """Constants used by the WOTV Bot"""
    HELP = '''
    To add your high score to the leaderboard, attach a screenshot and use the following command:
    !leaderboard-set high-score #####
    (where ##### is your numerical score; e.g. 12345)

    Command help is at: <https://github.com/andrewhayden/ffbe_forever_guild_bot/blob/master/COMMAND_HELP.md>
    Admin help is at: <https://github.com/andrewhayden/ffbe_forever_guild_bot/blob/master/ADMIN_COMMAND_HELP.md>
    Your guild's Esper resonance data is at: <https://docs.google.com/spreadsheets/d/{0}>
    Your guild's Vision Card data is at: <https://docs.google.com/spreadsheets/d/{1}>
    Your guild's Leaderboard is at: <https://docs.google.com/spreadsheets/d/{2}>
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

    # Pattern for rolling dice like in D&D, e.g. "!roll 3d6#
    ROLLDICE_PATTERN = re.compile(r'^!roll (?P<dice_spec>.+)?$')

    # Patterns to ask for a prediction
    PREDICTION_PATTERN_1 = re.compile(r'^!predict ?(?P<query>.+)?$')
    PREDICTION_PATTERN_2 = re.compile(r'^!astrologize ?(?P<query>.+)?$')
    PREDICTION_PATTERN_3 = re.compile(r'^!divine ?(?P<query>.+)?$')
    PREDICTION_PATTERN_4 = re.compile(r'^!foretell ?(?P<query>.+)?$')

    # Pattern to save a Leaderboard value to your account, optionally with a proof URL.
    LEADERBOARD_SET_PATTERN = re.compile(
        r'^!leader(?:board)?-set (?P<category>[^\s]+)\s+(?P<value>[^\s]+)(\s+(?P<proof_url>.+)?)?$')

    # Pattern to save a Vision Card to your account, extracting text from an attached screenshot.
    VISION_CARD_SET_PATTERN = re.compile(r'^!vc-set$')

    # Pattern to debug problems with vision card setting
    VISION_CARD_DEBUG_PATTERN = re.compile(r'^!vc-debug$')

    # Pattern to retieve one of your own vision card's stats.
    VISION_CARD_FETCH_BY_NAME_PATTERN = re.compile(r'^!vc (?P<target_name>.+)$')

    # Pattern to retieve one of your own vision card's stats.
    VISION_CARD_ABILITY_SEARCH = re.compile(r'^!vc-ability (?P<search_text>.+)$')

    # Pattern to retieve a list of skills by name, with optional refinement criteria on separate additional lines.
    FIND_SKILLS_BY_NAME_PATTERN = re.compile(r'^!skills-by-name (?P<search_text>.+)$')

    # Pattern to retieve a list of skills by description, with optional refinement criteria on separate additional lines.
    FIND_SKILLS_BY_DESCRIPTION_PATTERN = re.compile(r'^!skills-by-desc(?:ription)? (?P<search_text>.+)$')

    # Pattern to retieve a list of units, with a rich search syntax and optional criteria.
    # See detailed help for more information.
    RICH_UNIT_SEARCH_PATTERN = re.compile(r'^!unit-search (?P<search_type>[^\s]+)\s*(?P<search_text>.+)?$')

    # Patterns for requesting the weekly drop rate schedule
    DOUBLE_DROP_RATES_SCHEDULE_PATTERN_1 = re.compile(r'^!schedule$')

    # Pattern for requesting the current double drop rate room
    DOUBLE_DROP_RATES_SCHEDULE_PATTERN_2 = re.compile(r'^!mats$')

    # Pattern for setting up daily reminders. Supported daily reminders are specified in the list.
    DAILY_REMINDERS = re.compile(r'^!daily-reminders(?P<reminder_list> .+)?$')

    # Pattern to get a reminder when it's time to spawn the Whimsy shop again.
    WHIMSY_REMINDER_PATTERN = re.compile(r'^!whimsy(?P<command> .+)?$')

    # (Hidden) Pattern for getting your own user ID out of Discord
    WHOIS_PATTERN = re.compile(r'^!whois (?P<server_handle>.+)$')

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

    # (Admin only) Pattern for adding a Unit row.
    ADMIN_ADD_VC_PATTERN = re.compile(
        r'^!admin-add-vc (?P<name>[^\|].+)\|(?P<url>[^\|]+)\|(?P<above_or_below>.+)\|(?P<row1Based>.+)$')

    # (Admin only) Pattern to add a new user.
    ADMIN_ADD_USER_PATTERN = re.compile(
        r'^!admin-add-user (?P<snowflake_id>[^\|].+)\|(?P<nickname>[^\|]+)\|(?P<user_type>.+)$')

    # List of all ignore patterns, to iterate over.
    ALL_IGNORE_PATTERNS = [
        # Ignore any lines that start with a "!" followed by any non-letter character, since these are definitely not bot commands.
        # This prevents people's various exclamations like "!!!!!" from being acknolwedged by the bot.
        re.compile(r'^![^a-zA-Z]'),
        # Similarly, ignore the raw "!" message. Separate from the pattern above for regex sanity.
        re.compile(r'^!$')]
