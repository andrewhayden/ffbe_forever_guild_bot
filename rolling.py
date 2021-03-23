"""Utilities for dice-rolling simulation and similar functionality aka 'fun toys'."""
from __future__ import annotations
import random
import re
from dataclasses import dataclass
from typing import List
from wotv_bot_common import ExposableException

@dataclass
class DiceSpec:
    """Represents a number of dice each having the same number of sides."""
    num_dice: int = 0
    num_sides: int = 0
    @staticmethod
    def parse(dice_string: str) -> DiceSpec:
        """Parse a string of the form "#d#" where the first number is the number of dice to roll and the second number is the number of sides per die."""
        dice_pattern = re.compile(r'^(?P<num_dice>[0-9]+)d(?P<num_sides>[0-9]+)$')
        error_addendum = 'Dice rolls look like "2d7", where "2" is the number of dice and "7" is the number of sides per die.'
        match = dice_pattern.match(dice_string)
        if not match:
            raise ExposableException('Not a valid dice roll. ' + error_addendum)
        num_dice: int = int(match.group('num_dice'))
        if num_dice < 1:
            raise ExposableException('Must roll at least 1 die. ' + error_addendum)
        num_sides: int = int(match.group('num_sides'))
        if num_sides < 2:
            raise ExposableException('Dice need to have at least 2 sides. ' + error_addendum)
        result = DiceSpec()
        result.num_sides = num_sides
        result.num_dice = num_dice
        return result

class Rolling:
    """Simple class for rolling dice."""
    @staticmethod
    def rollDice(dice_spec: DiceSpec) -> List[int]:
        """Roll dice according to the specified DiceSpec and return an array of the resulting rolls, one per die."""
        result: List[int] = []
        for _ in range (0, dice_spec.num_dice):
            result.append(random.randint(1, dice_spec.num_sides))
        return result
