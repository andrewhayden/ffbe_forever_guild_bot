"""Tools for searching and filtering within the data files."""
import re
import shlex
from dataclasses import dataclass

from common_search_utils import CommonSearchUtils
from data_files import DataFiles
from data_file_core_classes import WotvUnit, WotvBoardSkill, WotvSkill, WotvJob
from wotv_bot_common import ExposableException

@dataclass
class Refinement:
    """One refinement."""
    is_not: bool = False # True if this is a "not" refinement
    search_type: str = None
    search_text: str = None

@dataclass
class UnitSearchResult:
    """A unit search result containing (at least) a unit. Intended to be extended for more specific types of search results."""
    unit: WotvUnit = None

@dataclass
class UnitSkillSearchResult(UnitSearchResult):
    """A unit skill search result containing a fully qualified result: the unit, the ability board criteria gating the skill, and the skill itself.

    The search result field is_master_ability is set to true if the result was a hit on a Master Ability instead of a Board Skill. In this case,
    the board_skill field will be set to None and the skill is a Master Ability.
    """
    is_master_ability: bool = False
    board_skill: WotvBoardSkill = None
    skill: WotvSkill = None

@dataclass
class UnitJobSearchResult(UnitSearchResult):
    """A unit job search result containing a unit and a job."""
    job: WotvJob = None

class DataFileSearchUtils:
    """Tools for searching and filtering within the data files."""
    @staticmethod
    def findUnitWithSkillName(data_files: DataFiles, search_text: str,
        previous_results_to_filter: [UnitSearchResult] = None) -> [UnitSkillSearchResult]:
        """Find all units with a skill whose name matches the specified search text.

        If the search text is quoted, only units with names containing an exact match will be returned. Otherwise a fuzzy match is performed.
        If previous_results_to_filter is a list of UnitSearchResult objects, searches only within those results. Otherwise searches all units."""
        exact_match_only = search_text.startswith('"') and search_text.endswith('"')
        if exact_match_only:
            search_text = (search_text[1:-1])
        search_text = search_text.lower()

        results = []
        units_to_search = None
        if previous_results_to_filter is not None:
            units_to_search = [entry.unit for entry in previous_results_to_filter]
        else:
            units_to_search = data_files.playable_units_by_id.values()
        for unit in units_to_search:
            for ability_board_skill in unit.ability_board.all_skills.values():
                if ability_board_skill.skill_id in data_files.skills_by_id:
                    skill = data_files.skills_by_id[ability_board_skill.skill_id]
                    if (exact_match_only and search_text in skill.name.lower()) or (
                        (not exact_match_only) and CommonSearchUtils.fuzzyMatches(skill.name.lower(), search_text)):
                        one_result = UnitSkillSearchResult()
                        one_result.unit = unit
                        one_result.board_skill = ability_board_skill
                        one_result.skill = skill
                        results.append(one_result)
            for master_skill in unit.master_abilities:
                if master_skill.unique_id in data_files.skills_by_id:
                    skill = data_files.skills_by_id[master_skill.unique_id]
                    if (exact_match_only and search_text in skill.name.lower()) or (
                        (not exact_match_only) and CommonSearchUtils.fuzzyMatches(skill.name.lower(), search_text)):
                        one_result = UnitSkillSearchResult()
                        one_result.unit = unit
                        one_result.is_master_ability = True
                        one_result.skill = skill
                        results.append(one_result)
        return results

    @staticmethod
    def findUnitWithSkillDescription(data_files: DataFiles, search_text: str,
        previous_results_to_filter: [UnitSearchResult] = None) -> [UnitSkillSearchResult]:
        """Find all units with a skill whose description matches the specified search text.

        If the search text is quoted, only units with skill descriptions containing exact matches will be returned. Otherwise a fuzzy match is performed.
        If previous_results_to_filter is a list of UnitSearchResult objects, searches only within those results. Otherwise searches all units."""
        exact_match_only = search_text.startswith('"') and search_text.endswith('"')
        if exact_match_only:
            search_text = (search_text[1:-1])
        search_text = search_text.lower()

        results = []
        units_to_search = None
        if previous_results_to_filter is not None:
            units_to_search = [entry.unit for entry in previous_results_to_filter]
        else:
            units_to_search = data_files.playable_units_by_id.values()
        for unit in units_to_search:
            for ability_board_skill in unit.ability_board.all_skills.values():
                if ability_board_skill.skill_id in data_files.skills_by_id:
                    skill = data_files.skills_by_id[ability_board_skill.skill_id]
                    if (exact_match_only and search_text in skill.description.lower()) or (
                        (not exact_match_only) and CommonSearchUtils.fuzzyMatches(skill.description.lower(), search_text)):
                        one_result = UnitSkillSearchResult()
                        one_result.unit = unit
                        one_result.board_skill = ability_board_skill
                        one_result.skill = skill
                        results.append(one_result)
            for master_skill in unit.master_abilities:
                if master_skill.unique_id in data_files.skills_by_id:
                    skill = data_files.skills_by_id[master_skill.unique_id]
                    if (exact_match_only and search_text in skill.description.lower()) or (
                        (not exact_match_only) and CommonSearchUtils.fuzzyMatches(skill.description.lower(), search_text)):
                        one_result = UnitSkillSearchResult()
                        one_result.unit = unit
                        one_result.is_master_ability = True
                        one_result.skill = skill
                        results.append(one_result)
        return results

    @staticmethod
    def findUnitWithJobName(data_files: DataFiles, search_text: str,
        previous_results_to_filter: [UnitSearchResult] = None) -> [UnitJobSearchResult]:
        """Find all units with a job whose name matches the specified search text.

        If the search text is quoted, only units with job names containing an exact match will be returned. Otherwise a fuzzy match is performed.
        If previous_results_to_filter is a list of UnitSearchResult objects, searches only within those results. Otherwise searches all units."""
        exact_match_only = search_text.startswith('"') and search_text.endswith('"')
        if exact_match_only:
            search_text = (search_text[1:-1])
        search_text = search_text.lower()

        results = []
        units_to_search = None
        if previous_results_to_filter is not None:
            units_to_search = [entry.unit for entry in previous_results_to_filter]
        else:
            units_to_search = data_files.playable_units_by_id.values()
        for unit in units_to_search:
            for job in unit.job_list:
                if (exact_match_only and search_text in job.name.lower()) or (
                    (not exact_match_only) and CommonSearchUtils.fuzzyMatches(job.name.lower(), search_text)):
                    one_result = UnitJobSearchResult()
                    one_result.unit = unit
                    one_result.job = job
                    results.append(one_result)
        return results

    @staticmethod
    def findUnitWithRarity(data_files: DataFiles, rarity: str,
        previous_results_to_filter: [UnitSearchResult] = None) -> [UnitJobSearchResult]:
        """Find all units with the specified rarity, which must be one of UR, MR, SR, R, or N (case insensitive).

        If previous_results_to_filter is a list of UnitSearchResult objects, searches only within those results. Otherwise searches all units."""
        if rarity.startswith('"') and rarity.endswith('"'): # Strip, but ignore, any exact-match semantics
            rarity = (rarity[1:-1])
        rarity = rarity.lower()
        results = []
        units_to_search = None
        if previous_results_to_filter is not None:
            units_to_search = [entry.unit for entry in previous_results_to_filter]
        else:
            units_to_search = data_files.playable_units_by_id.values()
        for unit in units_to_search:
            if unit.rarity and unit.rarity.lower() == rarity:
                result = UnitSearchResult()
                result.unit = unit
                results.append(result)
        return results

    @staticmethod
    def findUnitWithElement(data_files: DataFiles, element: str,
        previous_results_to_filter: [UnitSearchResult] = None) -> [UnitJobSearchResult]:
        """Find all units with the specified element, which must be one of none, fire, ice, wind, earth, lightning, water, light or dark (case insensitive).

        For units that have multiple elements, the unit is considered matching if any of those elements is the specified element.
        If previous_results_to_filter is a list of UnitSearchResult objects, searches only within those results. Otherwise searches all units."""
        if element.startswith('"') and element.endswith('"'): # Strip, but ignore, any exact-match semantics
            element = (element[1:-1])
        element = element.lower()
        results = []
        units_to_search = None
        if previous_results_to_filter is not None:
            units_to_search = [entry.unit for entry in previous_results_to_filter]
        else:
            units_to_search = data_files.playable_units_by_id.values()
        for unit in units_to_search:
            for unit_element in unit.elements:
                if unit_element.lower() == element:
                    result = UnitSearchResult()
                    result.unit = unit
                    results.append(result)
        return results

    @staticmethod
    def __invokeTypedSearch(
        data_files: DataFiles,
        search_type: str = None,
        search_text: str = None,
        previous_results_to_filter: [UnitSearchResult] = None) -> [UnitSearchResult]:
        search_type = search_type.strip().lower()
        if search_type == 'all':
            results: [UnitSearchResult] = []
            for unit in data_files.playable_units_by_id.values():
                one_result = UnitSearchResult()
                one_result.unit = unit
                results.append(one_result)
            return results
        if search_type == 'skill-name':
            return DataFileSearchUtils.findUnitWithSkillName(data_files, search_text, previous_results_to_filter)
        if search_type == 'skill-desc' or search_type == 'skill-description':
            return DataFileSearchUtils.findUnitWithSkillDescription(data_files, search_text, previous_results_to_filter)
        if search_type == 'job' or search_type == 'job-name':
            return DataFileSearchUtils.findUnitWithJobName(data_files, search_text, previous_results_to_filter)
        if search_type == 'rarity':
            return DataFileSearchUtils.findUnitWithRarity(data_files, search_text, previous_results_to_filter)
        if search_type == 'element':
            return DataFileSearchUtils.findUnitWithElement(data_files, search_text, previous_results_to_filter)
        raise ExposableException('Unsupported rich unit search type or refinement: "' + search_type + '". For help using search, use !help')

    @staticmethod
    def __retainMatching(from_results: [UnitSearchResult], retain_matching_units: [UnitSearchResult]) -> [UnitSearchResult]:
        """From a specified collection from_results, retain only those that match the units in retain_matching_units."""
        retained_ids = set([one_result.unit.unique_id for one_result in retain_matching_units])
        return [one_result for one_result in from_results if one_result.unit.unique_id in retained_ids]

    @staticmethod
    def __retainNotMatching(from_results: [UnitSearchResult], retain_matching_units: [UnitSearchResult]) -> [UnitSearchResult]:
        """From a specified collection from_results, retain only those that DO NOT match the units in retain_matching_units."""
        retained_ids = set([one_result.unit.unique_id for one_result in retain_matching_units])
        return [one_result for one_result in from_results if one_result.unit.unique_id not in retained_ids]

    @staticmethod
    def __extractRefinement(line: str):
        # Convert the line into a series of string tokens. Quoted strings end up problematic, as other code in this project expects
        # them to be quoted with double quotes but shlex.quote uses single-quotes only. So after splitting, find any string that
        # still contains whitespace and double-quote it - because the user must have quoted it to begin with.
        tokens = shlex.split(line)
        re_quoted: [str] = []
        for token in tokens:
            if re.search(r"\s", token):
                token = '"' + token + '"'
            else:
                token = token.lower()
            re_quoted.append(token)
        tokens = re_quoted
        result = Refinement()
        if tokens[0] == 'not':
            result.is_not = True
            tokens = tokens[1:]
        result.search_type = tokens[0]
        if len(tokens) > 1:
            result.search_text = tokens[1]
        return result

    @staticmethod
    def richUnitSearch(
        data_files: DataFiles,
        search_type: str = None,
        search_text: str = None,
        refinements: [str] = None) -> [UnitSearchResult]:
        """Perform a rich search starting with a search of the specified type and text, and refining (restricting) results.

        Supported types are as follows:
        * all: start with all units (unrestricted search) and refine, returning a list of UnitSearchResult; search_text must not be None.
        * skill-name: search units by skill name, returning a list of UnitSkillSearchResult; search_text as in findUnitWithSkillName().
        * skill-desc[ription]: search units by skill description, returning a list of UnitSkillSearchResult; search_text as in findUnitWithSkillDescription().
        * job[-name]: search units by job name, returning a list of UnitJobSearchResult; search_text as in findUnitWithJobName().
        * rarity: search units by rarity, returning a list of UnitSearchResult; search_text as in findUnitWithRarity().
        * element: search units by element, returning a list of UnitSearchResult; search_text as in findUnitWithElement().

        Each refinement is expected to be a line of the form <refinement_type>[<whitespace><search_text>]. The refinement type may be preceded by
        the word "not" to invert the meaning, or "except" meaning to take everything except the result.
        * search_type = 'rarity', search_text='ur': bootstrap the search as a rarity search for only UR units.
        * refinements[0] = 'job-name paladin': retain only UR units who have the job paladin
        * refinements[1] = 'except element earth': retain only units that are not earth element
        * refinements[2] = 'not skill-name Killer Blade': retain only units that do not have a skill whose name matches "Killer Blade".
        """
        # Begin with the initial search.
        results = DataFileSearchUtils.__invokeTypedSearch(data_files, search_type, search_text, None)
        if refinements is None:
            return results

        for refinement_line in refinements:
            refinement_command = DataFileSearchUtils.__extractRefinement(refinement_line)
            refinement_results = DataFileSearchUtils.__invokeTypedSearch(data_files, refinement_command.search_type, refinement_command.search_text, results)
            if refinement_command.is_not:
                results = DataFileSearchUtils.__retainNotMatching(results, refinement_results)
            else:
                results = DataFileSearchUtils.__retainMatching(results, refinement_results)
        return results
