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

    # Pick some values near the current maxima as of 2020-12-05, assuming these will only ever increase
    MIN_UNIT_COUNT = 85 # Only include playable units, in case the other stuff gets moved off elsewhere (seems likely, eventually)
    MIN_SKILL_COUNT = 2000
    MIN_JOB_COUNT = 230

    def __init__(self, units_by_id: Dict[str, WotvUnit], skills_by_id: Dict[str, WotvSkill], jobs_by_id: Dict[str, WotvJob]):
        self.units_by_id = units_by_id
        self.skills_by_id = skills_by_id
        self.jobs_by_id = jobs_by_id

    @staticmethod
    def parseDataDump(data_dump_root_path: str):
        """Parse the data dump and return an instance of the DataFile class that can be used to access them.

        Note that this method will block until all files are read and processed, which may take considerable time.
        """
        json_ability_boards = None
        json_job_names = None
        json_skill_descriptions = None
        json_skill_names = None
        json_unit_data = None
        json_unit_names = None

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
        # Build from the leaf nodes back towards the roots, that is, from the things that are fully defined (such as a skill)
        # upwards towards the things that use them (board skills, ability boards, units).

        # Start with the raw set of all skills in the game (including unit skills, enemy skills, etc)
        result_skills_by_id: Dict[str, WotvSkill] = {}
        temp_all_skill_descriptions_by_id = {}
        for json_entry in json_skill_descriptions['infos']:
            temp_all_skill_descriptions_by_id[json_entry['key']] = json_entry['value']
        for json_entry in json_skill_names['infos']: # Array of JSON objects representing skills.
            parsed = WotvSkill()
            parsed.unique_id = json_entry['key']
            parsed.name = json_entry['value']
            parsed.description = temp_all_skill_descriptions_by_id[parsed.unique_id]
            result_skills_by_id[parsed.unique_id] = parsed
        print('Discovered ' + str(len(result_skills_by_id)) + ' skills.')

        # Build up the list of jobs.
        result_jobs_by_id: Dict[str, WotvJob] = {}
        for json_entry in json_job_names['infos']:
            temp_job = WotvJob()
            temp_job.unique_id = json_entry['key']
            temp_job.name = json_entry['value']
            result_jobs_by_id[temp_job.unique_id] = temp_job
        print('Discovered ' + str(len(result_jobs_by_id)) + ' jobs.')

        # Fetch all the units in the game, so that we know the jobs to use in the ability board later.
        # Start by inferring all units from the list of names.
        result_all_units_by_id: Dict[str, WotvUnit] = {}
        for json_entry in json_unit_names['infos']:
            temp_unit = WotvUnit()
            temp_unit.unique_id = json_entry['key']
            temp_unit.name = json_entry['value']
            result_all_units_by_id[temp_unit.unique_id] = temp_unit
        print('Discovered ' + str(len(result_all_units_by_id)) + ' units (includes enemies, traps, etc).')

        # Fill in all remaining unit details except the ability board, because it needs the job order
        # to identify which job unlocks which skill (the ability board jobs list their unlock criteria
        # as a 1-based integer offset into the job list, along with the job's level).
        for json_entry in  json_unit_data['items']:
            temp_unit = result_all_units_by_id[json_entry['iname']]
            if 'jobsets' in json_entry:
                for jobset_id in json_entry['jobsets']:
                    temp_unit.job_list.append(result_jobs_by_id[jobset_id])
            if 'mstskl' in json_entry:
                for skill_id in json_entry['mstskl']: # Master abilities
                    temp_unit.master_abilities.append(result_skills_by_id[skill_id])
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
                temp_unit.is_playable = True
                board_count += 1
                for panel_entry in json_entry['panels']:
                    skill_count += 1
                    temp_board_skill = WotvBoardSkill()
                    temp_board_skill.skill_id = panel_entry['value']
                    job_index = panel_entry['get_job'] # 1-based index into the job list for the unit
                    temp_board_skill.unlocked_by_job_key = temp_unit.job_list[job_index - 1]
                    if 'need_level' in panel_entry:
                        temp_board_skill.unlocked_by_job_level = panel_entry['need_level']
                    temp_board.all_skills[temp_board_skill.skill_id] = temp_board_skill
        print('Discovered and bound ' + str(board_count) + ' ability boards for playable units, containing a total of ' + str(skill_count) + ' skills.')
        return DataFiles(result_all_units_by_id, result_skills_by_id, result_jobs_by_id)

    def sanityCheckCounts(self, min_unit_count: int = MIN_UNIT_COUNT, min_skill_count: int = MIN_SKILL_COUNT, min_job_count: int = MIN_JOB_COUNT):
        """Check that the counts of units, skills, and jobs (etc) in the data dump are sane."""
        # Pick some values near the current maxima as of 2020-12-05, assuming these will only ever increase
        num_units = len(self.units_by_id)
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
        mont = self.units_by_id['UN_LW_P_MONT']
        if mont is None:
            raise Exception('Cannot find Mont (UN_LW_P_MONT)!')
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

    @staticmethod
    def invokeStandalone(data_dump_root_path: str):
        """Check the basic integrity of the data dump."""
        result = DataFiles.parseDataDump(data_dump_root_path + '/')
        result.sanityCheckCounts()
        result.sanityCheckMont()
        print('Data dump appears to be intact and parsing appears to be sane.')

if __name__ == "__main__":
    DataFiles.invokeStandalone(sys.argv[1])
