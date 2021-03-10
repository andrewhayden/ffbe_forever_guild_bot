"""Classes constructed from JSON data dumps."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class WotvJob:
    """Data for a Job"""
    unique_id: str = None   # Example: "JB_LW_WAR"
    name: str = None        # Example: "Lord"

@dataclass
class WotvSkill:
    """Data for a Skill.

    Skills are independent of characters and their ability boards. A character gains access to a skill via their ability board.
    The Ability Board is a collection of WotvBoardSkills that define the way that the unit gains access to the skill.

    There are many more skills in the game than the ones the characters themselves use. There are special skills for enemies
    and even for special things like traps and 'gimmicks'.
    """
    unique_id: str = None   # Example: "SK_LW_WAR_M_4"
    name: str = None        # Example: "Killer Blade"
    description: str = None # Example: "Deals Dmg (L) to target & bestows Man Eater."

@dataclass
class WotvBoardSkill:
    """A skill that is unlocked via the ability board."""
    skill_id: str = None                # Indirection to a WotvSkill.unique_id, example: "SK_LW_WAR_M_4"
    unlocked_by_job: WotvJob = None     # The WotvJob that unlocks the skill (see WotvJob)
    unlocked_by_job_level: int = None   # Example: 7

@dataclass
class WotvAbilityBoard:
    """A collection of all of the skills available to a character via the ability board.

    In the future may be expanded to handle EX awakenings. For now, it's just a dictionary of skill IDs and their unlock criteria.
    """
    all_skills: Dict[str, WotvBoardSkill] = field(default_factory=dict) # Example: ("SK_LW_WAR_M_4" = WotvBoardSkill)

@dataclass
class WotvUnit:
    """Data for a Unit"""
    is_playable: bool = False # True for playable characters, false for
    # Although as of 2020-12-05 there are no playable units with multiple elements, units can (and will) have multiple elements.
    elements: List[str] = field(default_factory=list) # Possible values are {"Fire", "Ice", "Wind", "Water", "Earth", "Light", "Dark", "Lightning", "None"}
    rarity: str = None # Example: "MR"
    unique_id: str = None # Example: "UN_LW_P_MONT"
    name: str = None # Example: "Mont Leonis"
    limit_burst_skill: WotvSkill = None # Example: (the WotvSkill object whose key is SK_LB_LW_MONT (in-game name "Destiny's Cross"))
    ability_board: WotvAbilityBoard = WotvAbilityBoard() # Example: ("SK_LW_WAR_M_4" = WotvSkill)
    master_abilities: List[WotvSkill] = field(default_factory=list) # Example: [(the WotvSkill object whose key is SK_MA_LW_MONT)]
    job_list: List[WotvJob] = field(default_factory=list) # Example: [<WotvJob>, <WotvJob>, <WotvJob>] (typically exactly 3 jobs, ordered)

    def hasElement(self, element_name: str):
        """Returns true if and only if the unit has the specified element (must be one of Fire, Ice, Wind, Water, Earth, Light, Lightning, or None)."""
        for element in self.elements:
            if element.lower() == element_name.lower():
                return True
        return False
