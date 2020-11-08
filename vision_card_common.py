"""Common code for working with Vision Cards"""
from dataclasses import dataclass, field
from typing import List
from PIL import Image

@dataclass
class VisionCard:
    """All data for a Vision Card, with optional debugging fields."""
    Name: str = None
    Cost: int = 0
    HP: int = 0
    DEF: int = 0
    TP: int = 0
    SPR: int = 0
    AP: int = 0
    DEX: int = 0
    ATK: int = 0
    AGI: int = 0
    MAG: int = 0
    Luck: int = 0
    PartyAbility: str = None
    BestowedEffects: List[str] = field(default_factory=list)
    debug_image_step1_gray: Image = None
    debug_image_step2_blurred: Image = None
    debug_image_step3_thresholded: Image = None
    stats_debug_image_step4_cropped_gray: Image = None
    stats_debug_image_step5_cropped_gray_inverted: Image = None
    stats_debug_image_step6_converted_final_ocr_input_image: Image = None
    info_debug_image_step4_cropped_gray: Image = None
    info_debug_image_step5_cropped_gray_inverted: Image = None
    info_debug_image_step6_converted_final_ocr_input_image: Image = None
    stats_debug_raw_text: str = None
    info_debug_raw_text: str = None
    successfully_extracted: bool = False
    error_messages: List[str] = field(default_factory=list)

    def prettyPrint(self):
        """Print a human-readable textual representation of a Vision Card"""
        result = self.Name + '\n'
        result += '  Cost: ' + str(self.Cost) + '\n'
        result += '  HP: ' + str(self.HP) + '\n'
        result += '  DEF: ' + str(self.DEF) + '\n'
        result += '  TP: ' + str(self.TP) + '\n'
        result += '  SPR: ' + str(self.SPR) + '\n'
        result += '  AP: ' + str(self.AP) + '\n'
        result += '  DEX: ' + str(self.DEX) + '\n'
        result += '  ATK: ' + str(self.ATK) + '\n'
        result += '  AGI: ' + str(self.AGI) + '\n'
        result += '  MAG: ' + str(self.MAG) + '\n'
        result += '  Luck: ' + str(self.Luck) + '\n'
        result += '  Party Ability: ' + str(self.PartyAbility) + '\n'
        result += '  Bestowed Effects:\n'
        for bestowed_effect in self.BestowedEffects:
            result += '    ' + bestowed_effect + '\n'
        return result
