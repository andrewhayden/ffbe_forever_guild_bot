"""Tools for interacting with the WOTV data files.

Built specifically to handle files and formatting from https://github.com/shalzuth/wotv-ffbe-dump.
"""
from __future__ import annotations
import json
import sys

from typing import Dict

from data_file_core_classes import WotvUnit, WotvSkill, WotvJob, WotvAbilityBoard, WotvBoardSkill

class DataFiles:
    """Processes data files from a data dump."""
    PATH_TO_ABILITY_BOARDS = "data/UnitAbilityBoard.json"
    PATH_TO_JOB_NAMES = "en/JobName.json"
    PATH_TO_SKILL_DESCRIPTIONS = "en/SkillExpr.json"
    PATH_TO_SKILL_NAMES = "en/SkillName.json"
    PATH_TO_UNIT_DATA = "data/Unit.json"
    PATH_TO_UNIT_NAMES = "en/UnitName.json"

    # The fixups file contains extra fixups checked into source control in the bot project, not the data dump."""
    PATH_TO_FIXUPS = "fixups.json"

    # The elements, by their 0-based IDs.
    ELEMENT_NAME_BY_ID: Dict(int, str) = {
        0: 'None', # Non-element units do exist in the data as of 2020-12-05, such as Muraga Fennes.
        1: 'Fire',
        2: 'Ice',
        3: 'Wind',
        4: 'Earth', # In the game files this is called "soil"
        5: 'Lightning',
        6: 'Water',
        7: 'Light', # In the game files this is called "shine"
        8: 'Dark'
    }

    # Short-form names, by their 0-based IDs (N, R, SR, MR, UR).
    SHORT_RARITY_BY_ID: Dict(int, str) = {
        0: 'N',
        1: 'R',
        2: 'SR',
        3: 'MR',
        4: 'UR'
    }

    # Pick some values near the current maxima as of 2020-12-05, assuming these will only ever increase
    MIN_UNIT_COUNT = 85 # Only include playable units, in case the other stuff gets moved off elsewhere (seems likely, eventually)
    MIN_SKILL_COUNT = 2000
    MIN_JOB_COUNT = 230

    def __init__(self,
        all_units_by_id: Dict[str, WotvUnit],
        playable_units_by_id: Dict[str, WotvUnit],
        skills_by_id: Dict[str, WotvSkill],
        jobs_by_id: Dict[str, WotvJob]):
        self.all_units_by_id = all_units_by_id
        self.playable_units_by_id = playable_units_by_id
        self.skills_by_id = skills_by_id
        self.jobs_by_id = jobs_by_id

    @staticmethod
    def parseDataDump(data_dump_root_path: str):
        """Parse the data dump and return an instance of the DataFile class that can be used to access them.

        Note that this method will block until all files are read and processed, which may take considerable time.
        """
        if not data_dump_root_path.endswith('/'):
            data_dump_root_path += '/'

        json_ability_boards = None
        json_job_names = None
        json_skill_descriptions = None
        json_skill_names = None
        json_unit_data = None
        json_unit_names = None
        json_fixups = None

        with open(data_dump_root_path + DataFiles.PATH_TO_ABILITY_BOARDS) as input_file:
            json_ability_boards = json.load(input_file)
        with open(data_dump_root_path + DataFiles.PATH_TO_JOB_NAMES) as input_file:
            json_job_names = json.load(input_file)
        with open(data_dump_root_path + DataFiles.PATH_TO_SKILL_DESCRIPTIONS) as input_file:
            json_skill_descriptions = json.load(input_file)
        with open(data_dump_root_path + DataFiles.PATH_TO_SKILL_NAMES) as input_file:
            json_skill_names = json.load(input_file)
        with open(data_dump_root_path + DataFiles.PATH_TO_UNIT_DATA) as input_file:
            json_unit_data = json.load(input_file)
        with open(data_dump_root_path + DataFiles.PATH_TO_UNIT_NAMES) as input_file:
            json_unit_names = json.load(input_file)
        with open(DataFiles.PATH_TO_FIXUPS) as input_file:
            # Local to the bot's source directory, not the data dump
            json_fixups = json.load(input_file)

        # Build from the leaf nodes back towards the roots, that is, from the things that are fully defined (such as a skill)
        # upwards towards the things that use them (board skills, ability boards, units).

        # Start with the raw set of all skills in the game (including unit skills, enemy skills, etc)
        result_skills_by_id: Dict[str, WotvSkill] = {}
        temp_all_skill_descriptions_by_id = {}
        num_skill_description_fixups_applied = 0
        num_skill_name_fixups_applied = 0
        for json_entry in json_skill_descriptions['infos']:
            temp_all_skill_descriptions_by_id[json_entry['key']] = json_entry['value']
        for json_entry in json_fixups['skill_description_fixups']:
            key = json_entry['key']
            value = json_entry['value']
            if key in temp_all_skill_descriptions_by_id:
                print('WARNING: Fixup no longer required but still specified for skill description of skill ' + key + ' (' + value + ')')
            else:
                print('Fixup applied: skill ' + key + ' has description ' + value)
                num_skill_description_fixups_applied += 1
                temp_all_skill_descriptions_by_id[key] = value
        for json_entry in json_skill_names['infos']: # Array of JSON objects representing skills.
            parsed = WotvSkill()
            parsed.unique_id = json_entry['key']
            parsed.name = json_entry['value']
            parsed.description = temp_all_skill_descriptions_by_id[parsed.unique_id]
            result_skills_by_id[parsed.unique_id] = parsed
        for json_entry in json_fixups['skill_name_fixups']:
            parsed = WotvSkill()
            parsed.unique_id = json_entry['key']
            parsed.name = json_entry['value']
            parsed.description = temp_all_skill_descriptions_by_id[parsed.unique_id]
            if parsed.unique_id in result_skills_by_id:
                print('WARNING: Fixup no longer required but still specified for skill ' + parsed.unique_id + ' (' + parsed.name + ')')
            else:
                print('Fixup applied: skill ' + parsed.unique_id + ' has name ' + parsed.name)
                num_skill_name_fixups_applied += 1
                result_skills_by_id[parsed.unique_id] = parsed

        print('Discovered ' + str(len(result_skills_by_id)) + ' skills with ' + str(num_skill_description_fixups_applied)
            + ' description fixups and ' + str(num_skill_name_fixups_applied) + ' name fixes applied')

        # Build up the list of jobs.
        num_job_name_fixups_applied = 0
        result_jobs_by_id: Dict[str, WotvJob] = {}
        for json_entry in json_job_names['infos']:
            temp_job = WotvJob()
            temp_job.unique_id = json_entry['key']
            temp_job.name = json_entry['value']
            result_jobs_by_id[temp_job.unique_id] = temp_job
        for json_entry in json_fixups['job_name_fixups']:
            temp_job = WotvJob()
            temp_job.unique_id = json_entry['key']
            temp_job.name = json_entry['value']
            if temp_job.unique_id in result_jobs_by_id:
                print('WARNING: Fixup no longer required but still specified for job ' + temp_job.unique_id + ' (' + temp_job.name + ')')
            else:
                print('Fixup applied: job ' + temp_job.unique_id + ' has name ' + temp_job.name)
                num_job_name_fixups_applied += 1
                result_jobs_by_id[temp_job.unique_id] = temp_job
        print('Discovered ' + str(len(result_jobs_by_id)) + ' jobs with '
            + str(num_job_name_fixups_applied) + ' job name fixups.')

        # Fetch all the units in the game, so that we know the jobs to use in the ability board later.
        # Start by inferring all units from the list of names.
        num_unit_name_fixups_applied = 0
        result_all_units_by_id: Dict[str, WotvUnit] = {}
        for json_entry in json_unit_names['infos']:
            temp_unit = WotvUnit()
            temp_unit.unique_id = json_entry['key']
            temp_unit.name = json_entry['value']
            result_all_units_by_id[temp_unit.unique_id] = temp_unit
        for json_entry in json_fixups['unit_name_fixups']:
            temp_unit = WotvUnit()
            temp_unit.unique_id = json_entry['key']
            temp_unit.name = json_entry['value']
            if temp_unit.unique_id in result_all_units_by_id:
                print('WARNING: Fixup no longer required but still specified for unit ' + temp_unit.unique_id + ' (' + temp_unit.name + ')')
            else:
                print('Fixup applied: unit ' + temp_unit.unique_id + ' has name ' + temp_unit.name)
                num_unit_name_fixups_applied += 1
                result_all_units_by_id[temp_unit.unique_id] = temp_unit
        print('Discovered ' + str(len(result_all_units_by_id)) + ' units (includes enemies, espers, traps, etc) with '
            + str(num_unit_name_fixups_applied) + ' unit name fixups.')

        # Fill in all remaining unit details except the ability board, because it needs the job order
        # to identify which job unlocks which skill (the ability board jobs list their unlock criteria
        # as a 1-based integer offset into the job list, along with the job's level).
        for json_entry in  json_unit_data['items']:
            if json_entry['iname'] not in result_all_units_by_id:
                # Edge case with missing localization data. Lazy-create a unit with a placeholder name.
                temp_unit = WotvUnit()
                temp_unit.unique_id = json_entry['iname']
                temp_unit.name = '[Missing name, id=' + json_entry['iname'] + ']'
                result_all_units_by_id[json_entry['iname']] = temp_unit
            temp_unit = result_all_units_by_id[json_entry['iname']]
            if 'jobsets' in json_entry:
                for jobset_id in json_entry['jobsets']:
                    if jobset_id not in result_jobs_by_id:
                        # Edge case with missing localization data. Lazy-create a job with a placeholder hame.
                        temp_job = WotvJob()
                        temp_job.unique_id = jobset_id
                        temp_job.name = '[Missing job, id=' + jobset_id + ']'
                        result_jobs_by_id[temp_job.unique_id] = temp_job
                    temp_unit.job_list.append(result_jobs_by_id[jobset_id])
            if 'mstskl' in json_entry:
                for skill_id in json_entry['mstskl']: # Master abilities
                    if skill_id not in result_skills_by_id:
                        # Edge case with missing localization data. Lazy-create a skill with a placeholder name and description
                        temp_skill = WotvSkill()
                        temp_skill.unique_id = skill_id
                        temp_skill.name = 'Master Ability'
                        temp_skill.description = '[Missing master ability, id=' + skill_id + ']'
                        result_skills_by_id[temp_skill.unique_id] = temp_skill
                    temp_unit.master_abilities.append(result_skills_by_id[skill_id])
            if 'limit' in json_entry:
                if json_entry['limit'] not in result_skills_by_id:
                    # Edge case with missing localization data. Lazy-create a skill with a placeholder name and description
                    temp_skill = WotvSkill()
                    temp_skill.unique_id = json_entry['limit']
                    temp_skill.name = '[Missing limit burst, id=' + json_entry['limit'] + ']'
                    temp_skill.description = '[Missing limit burst, id=' + json_entry['limit'] + ']'
                    result_skills_by_id[temp_skill.unique_id] = temp_skill
                temp_unit.limit_burst_skill = result_skills_by_id[json_entry['limit']]
            if 'elem' in json_entry:
                for element_id in json_entry['elem']:
                    temp_unit.elements.append(DataFiles.ELEMENT_NAME_BY_ID[element_id])
            if 'rare' in json_entry:
                temp_unit.rarity = DataFiles.SHORT_RARITY_BY_ID[json_entry['rare']]
            if 'type' in json_entry and json_entry['type'] == 0:
                temp_unit.is_playable = True # Non-playable characters have type 7 or something like it.

        print('Bound jobs and skills for ' + str(len(result_all_units_by_id)) + ' units.')

        # Finally, build up the list of ability boards.
        # Also we flag playable units here, as only playable units have ability boards.
        board_count = 0
        skill_count = 0
        for json_entry in json_ability_boards['items']:
            if 'panels' in json_entry:
                temp_unit: WotvUnit = result_all_units_by_id[json_entry['iname']]
                temp_board = WotvAbilityBoard()
                temp_unit.ability_board = temp_board
                board_count += 1
                for panel_entry in json_entry['panels']:
                    if 'value' in panel_entry: # Not every panel has a value as of the FFX arrival, see for example panel 90 for Tidus
                        skill_count += 1
                        temp_board_skill = WotvBoardSkill()
                        temp_board_skill.skill_id = panel_entry['value']
                        job_index = panel_entry['get_job'] # 1-based index into the job list for the unit
                        temp_board_skill.unlocked_by_job = temp_unit.job_list[job_index - 1]
                        if 'need_level' in panel_entry:
                            temp_board_skill.unlocked_by_job_level = panel_entry['need_level']
                        temp_board.all_skills[temp_board_skill.skill_id] = temp_board_skill

        # Playable units all have ability boards with a skill count greater than 0. Filter accordingly.
        result_playable_units_by_id: Dict[str, WotvUnit] = {
            k:v for k, v in result_all_units_by_id.items() if v.is_playable and len(v.ability_board.all_skills) > 0
        }
        print('It looks like there are ' + str(len(result_playable_units_by_id)) + ' playable units: ')
        # Output a nicely formatted list of units so we can see what's in the dump.
        # Start by sorting by name and tracking the longest name so that we can align the output horizontally.
        playable_units_sorted_by_name = list()
        longest_name_length = 0
        longest_id_length = 0
        longest_limit_burst_name_length = 0
        for _, v in result_playable_units_by_id.items():
            playable_units_sorted_by_name.append(v)
            longest_name_length = max(longest_name_length, len(v.name))
            longest_id_length = max(longest_id_length, len(str(v.unique_id)))
            if v.limit_burst_skill:
                longest_limit_burst_name_length = max(longest_limit_burst_name_length, len(v.limit_burst_skill.name))
        playable_units_sorted_by_name = sorted(playable_units_sorted_by_name, key=lambda one_unit: one_unit.name)

        # Dump basic data for all playable units.
        for playable_unit in playable_units_sorted_by_name:
            buffer = ''
            buffer += playable_unit.name.rjust(longest_name_length) + ' [id '
            buffer += playable_unit.unique_id.rjust(longest_id_length) + ']: '
            buffer += 'Ability board: ' + ('Yes' if playable_unit.ability_board else 'No ') + ', '
            if playable_unit.limit_burst_skill:
                buffer += 'Limit Burst: ' + playable_unit.limit_burst_skill.name.rjust(longest_limit_burst_name_length) + ', '
            else:
                buffer += 'Limit Burst: ' + '(none)'.rjust(longest_limit_burst_name_length) + ', '
            buffer += 'Jobs: ' + str(len(playable_unit.job_list)) + ', '
            buffer += 'Unique Skills: ' + str(len(playable_unit.ability_board.all_skills))
            print(buffer)

        print('Discovered and bound ' + str(board_count) + ' ability boards for units, containing a total of ' + str(skill_count) + ' unique skills.')
        return DataFiles(result_all_units_by_id, result_playable_units_by_id, result_skills_by_id, result_jobs_by_id)

    def sanityCheckCounts(self, min_unit_count: int = MIN_UNIT_COUNT, min_skill_count: int = MIN_SKILL_COUNT, min_job_count: int = MIN_JOB_COUNT):
        """Check that the counts of units, skills, and jobs (etc) in the data dump are sane."""
        # Pick some values near the current maxima as of 2020-12-05, assuming these will only ever increase
        num_units = len(self.all_units_by_id)
        if num_units < min_unit_count: # Only include playable units, in case the other stuff gets moved off elsewhere (seems likely, eventually)
            raise Exception('Too few units in data dump for it to be sane: ' + str(num_units) + "<" + str(min_unit_count))
        num_skills = len(self.skills_by_id)
        if num_skills < min_skill_count:
            raise Exception('Too few skills in data dump for it to be sane: ' + str(num_skills) + '<' + str(min_skill_count))
        num_jobs = len(self.jobs_by_id)
        if num_jobs < min_job_count:
            raise Exception('Too few jobs in data dump for it to be sane: ' + str(num_jobs) + '<' + str(min_skill_count))

    def sanityCheckMont(self):
        """Check that Mont is present and that he has a sane set of jobs, Killer Blade, etc."""
        mont = self.all_units_by_id['UN_LW_P_MONT']
        if mont is None:
            raise Exception('Cannot find Mont (UN_LW_P_MONT) in all unts!')
        mont = self.playable_units_by_id['UN_LW_P_MONT']
        if mont is None:
            raise Exception('Cannot find Mont (UN_LW_P_MONT) in playable units!')
        print('Mont unit data is present.')
        if mont.name != 'Mont Leonis':
            raise Exception('Mont is not named Mont Leonis: ' + mont.name + '!')
        print('Mont has the correct name.')
        if len(mont.job_list) != 3:
            raise Exception('Mont does not have 3 jobs: count is ' + str(len(mont.job_list)))
        print('Mont has exactly 3 jobs.')
        if mont.job_list[0].name != 'Lord' or mont.job_list[1].name != 'Paladin' or mont.job_list[2].name != 'Knight':
            raise Exception('Mont has the wrong jobs: ' + str(mont.job_list))
        if 'SK_LW_WAR_M_4' not in self.skills_by_id:
            raise Exception('Killer Blade is missing from the skills list!')
        if 'SK_LW_WAR_M_4' not in mont.ability_board.all_skills:
            raise Exception('Mont is missing Killer Blade!')
        if not mont.hasElement('Earth'):
            raise Exception('Mont is not an Earth unit!')
        if not mont.rarity == 'MR':
            raise Exception('Mont is not an MR unit!')

    @staticmethod
    def invokeStandalone(data_dump_root_path: str):
        """Check the basic integrity of the data dump."""
        result = DataFiles.parseDataDump(data_dump_root_path + '/')
        result.sanityCheckCounts()
        result.sanityCheckMont()
        print('Data dump appears to be intact and parsing appears to be sane.')

if __name__ == "__main__":
    DataFiles.invokeStandalone(sys.argv[1])
