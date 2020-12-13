"""Tools for searching and filtering within the data files."""
from dataclasses import dataclass

from common_search_utils import CommonSearchUtils
from data_files import DataFiles
from data_file_core_classes import WotvUnit, WotvBoardSkill, WotvSkill

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

class DataFileSearchUtils:
    """Tools for searching and filtering within the data files."""
    @staticmethod
    def findUnitWithSkillName(data_files: DataFiles, search_text: str) -> [UnitSkillSearchResult]:
        """Find all units with a skill whose name matches the specified search text.

        If the search text is quoted, only units with names containing an exact match will be returned. Otherwise a fuzzy match is performed."""
        exact_match_only = search_text.startswith('"') and search_text.endswith('"')
        if exact_match_only:
            search_text = (search_text[1:-1])
        search_text = search_text.lower()

        results = []
        for unit in data_files.units_by_id.values():
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
    def findUnitWithSkillDescription(data_files: DataFiles, search_text: str) -> [UnitSkillSearchResult]:
        """Find all units with a skill whose description matches the specified search text.

        If the search text is quoted, only units with skill descriptions containing exact matches will be returned. Otherwise a fuzzy match is performed."""
        exact_match_only = search_text.startswith('"') and search_text.endswith('"')
        if exact_match_only:
            search_text = (search_text[1:-1])
        search_text = search_text.lower()

        results = []
        for unit in data_files.units_by_id.values():
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
