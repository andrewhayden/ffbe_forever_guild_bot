"""A module for extracting structured data from Vision Card screenshots."""
import re
import sys

import cv2
import imutils
import numpy
import pytesseract
import requests # for downloading images
from PIL import Image

from vision_card_common import VisionCard

class VisionCardOcrUtils:
    """Utilities for working with Optical Character Recognition (OCR) for Vision Cards"""
    # Ignore any party ability that is a string shorter than this length, usually
    # garbage from OCR gone awry.
    MIN_PARTY_ABILITY_STRING_LENGTH_SANITY = 4

    # Ignore any bestowed ability that is a string shorter than this length, usually
    # garbage from OCR gone awry.
    MIN_BESTOWED_ABILITY_STRING_LENGTH_SANITY = 4

    # If true, hints the OCR to be better at finding lines by tiling the "Cost" section of the stats panel horizontally.
    __USE_LATCHON_HACK = True

    @staticmethod
    def downloadScreenshotFromUrl(url):
        """Download a vision card screenshot from the specified URL and return as an OpenCV image object."""
        try:
            pilImage = Image.open(requests.get(url, stream=True).raw)
            opencvImage = cv2.cvtColor(numpy.array(pilImage), cv2.COLOR_RGB2BGR)
            return opencvImage
        except Exception as e:
            print(str(e))
            # pylint: disable=raise-missing-from
            raise Exception('Error while downloading or converting image: ' + url) # deliberately low on details as this may be surfaced online.

    @staticmethod
    def loadScreenshotFromFilesystem(path: str):
        """Load a vision card screenshot from the local filesystem and return as an OpenCV image object."""
        return cv2.imread(path)

    @staticmethod
    def extractRawTextFromVisionCard(vision_card_image, debug_vision_card:VisionCard = None) -> (str, str):
        """Get the raw, unstructured text from a vision card (basically the raw OCR dump string).

        If debug_vision_card is a VisionCard object, retains the intermediate images as debug information attached to that object.
        Returns a tuple of raw (card name text, card stats text) strings. These strings will need to be interpreted and cleaned of
        OCR mistakes / garbage.

        Returns a tuple of two strings, with the first string being the raw text extracted from the card info
        section (card name, etc) and the second string being the raw text extracted from the card stats section
        (stats, abilities granted, etc).
        """
        height, width, _ = vision_card_image.shape # ignored third element of the tuple is 'channels'

        # For vision cards, the screen is divided into left and right. The right side
        # always contains artwork. Drop it to reduce the contour iteration that will
        # be needed.
        vision_card_image = vision_card_image[0:height, 0:int(width/2)]

        # Convert the resized image to grayscale, blur it slightly, and threshold it
        # to set up the input to the contour finder.
        gray_image = cv2.cvtColor(vision_card_image, cv2.COLOR_BGR2GRAY)
        if debug_vision_card is not None:
            debug_vision_card.debug_image_step1_gray = Image.fromarray(gray_image)
        blurred_image = cv2.GaussianBlur(gray_image, (5, 5), 0)
        if debug_vision_card is not None:
            debug_vision_card.debug_image_step2_blurred = Image.fromarray(blurred_image)
        thresholded_image = cv2.threshold(blurred_image, 70, 255, cv2.THRESH_BINARY)[1]
        if debug_vision_card is not None:
            debug_vision_card.debug_image_step3_thresholded = Image.fromarray(thresholded_image)

        # Find and enumerate all the contours.
        contours = cv2.findContours(thresholded_image.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = imutils.grab_contours(contours)

        largestContour = None
        largestArea = 0
        largestX = None
        largestY = None
        largestW = None
        largestH = None

        # loop over the contours
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w*h
            if largestArea >= area:
                continue
            largestX = x
            largestY = y
            largestW = w
            largestH = h
            largestArea = area
            largestContour = contour

        if largestContour is None:
            raise Exception("No contours in image!")

        # Now on to text isolation

        # The name of the unit appears above the area where the stats are, just above buttons for
        # "Stats" and "Information". It appears that the unit name is always aligned vertically with
        # the top of the vision card, and that is the anchor point for the layout. So from here an
        # HTML-like table layout begins with one row containing the unit's rarity and name, then the
        # next row containing the stats and information boxes, and the third (and largest) row
        # contains all the stats we want to extract.
        # This table-like thing appears to be vertically floating in the center of the screen, with
        # any excess empty space appearing strictly above the unit name or below the stats table,
        # i.e. the three rows of data are kept together with no additional vertical space no matter
        # how much extra vertical space there is.
        # The top of the screen is reserved for the status bar and appears to have the same vertical
        # proportions as the rows for the unit name and the stats/information buttons. So to recap:
        # [player status bar, vertical size = X]
        # [any excess vertical space]
        # [unit name bar, vertical size ~= X]
        # [stats/information bar, vertical size ~=X]
        # Thus... if we take the area above the stats table, and remove the top 1/3, we should just
        # about always end up with the very first text being the unit rarity + unit name row.
        # Notably, long vision card names will overflow horizontal edge of the stats table and can
        # extend out to the center of the screen. So include the whole area up to where the original
        # center-cut was made, at width/2.
        # Finally, the unit rarity logo causes problems and is interpeted as garbage due to the
        # cursive script and color gradients. Fortunately the size of the logo appears to be in fixed
        # proportion to the size of the stats box, with the text always starting at the same position
        # relative to the left edge of the stats box no matter which logo (N, R, SR, MR or UR) is
        # used. For a stats panel about 420px wide the logo is about 75 pixels wide (about 18% of the
        # total width). So we will remove the left-most 18% of the space as well.
        info_bounds_logo_ratio = 0.18
        info_bounds_pad_left = (int) (info_bounds_logo_ratio * largestW)
        info_bounds_x = largestX + info_bounds_pad_left
        info_bounds_y = (int) (largestY * .33)
        info_bounds_w = ((int) (width/2)) - info_bounds_x
        info_bounds_h = (int) (largestY * .67)

        # Crop and invert the image, we need black on white.
        # Note that cropping via slicing has x values first, then y values
        stats_cropped_gray_image = gray_image[largestY:(largestY+largestH), largestX:(largestX+largestW)]
        info_cropped_gray_image = gray_image[info_bounds_y:(info_bounds_y+info_bounds_h), info_bounds_x:(info_bounds_x+info_bounds_w)]
        if debug_vision_card is not None:
            debug_vision_card.stats_debug_image_step4_cropped_gray = Image.fromarray(stats_cropped_gray_image)
            debug_vision_card.info_debug_image_step4_cropped_gray = Image.fromarray(info_cropped_gray_image)
        stats_cropped_gray_inverted_image = cv2.bitwise_not(stats_cropped_gray_image)
        info_cropped_gray_inverted_image = cv2.bitwise_not(info_cropped_gray_image)
        if debug_vision_card is not None:
            debug_vision_card.stats_debug_image_step5_cropped_gray_inverted = Image.fromarray(stats_cropped_gray_inverted_image)
            debug_vision_card.info_debug_image_step5_cropped_gray_inverted = Image.fromarray(info_cropped_gray_inverted_image)

        # Find only the darkest parts of the image, which should now be the text.
        stats_lower_bound_hsv_value = 0
        stats_upper_bound_hsv_value = 80
        # For the info area the text is pure white on a dark background normally. There is a unit logo with the text.
        # To try and eliminate the logo, be EXTREMELY restrictive on the HSV value here. Only almost-pure white (255,255,255) should
        # be considered at all. Everything else should be thrown out.
        info_lower_bound_hsv_value = 0
        info_upper_bound_hsv_value = 80
        stats_text_mask = cv2.inRange(stats_cropped_gray_inverted_image, stats_lower_bound_hsv_value, stats_upper_bound_hsv_value)
        info_text_mask = cv2.inRange(info_cropped_gray_inverted_image, info_lower_bound_hsv_value, info_upper_bound_hsv_value)
        stats_text_mask = cv2.bitwise_not(stats_text_mask)
        info_text_mask = cv2.bitwise_not(info_text_mask)
        stats_final_ocr_input_image = stats_text_mask
        info_final_ocr_input_image = info_text_mask

        # Now convert back to a regular Python image from CV2.
        stats_converted_final_ocr_input_image = Image.fromarray(stats_final_ocr_input_image)
        info_converted_final_ocr_input_image = Image.fromarray(info_final_ocr_input_image)

        # The Latch-On Hack
        # Now a strange tweak. Many vision cards, particularly of the more common rarities, have few stats. This results in lots
        # of empty space in the stats table and can cause the OCR to be unable to "latch on" to the fact that we want it to find
        # distinct lines of text. To fix this, we can add some text to the image - but what to add, and where, and how to match
        # the font and DPI? The "Cost ##" chunk of text near the top of the stats section holds the key. After the inRange()
        # operations above, the level bar will have been removed, leaving the area to the right of the "cost" section totally
        # empty. The cost section itself consists of the word "Cost", and then a number, and conveniently it takes up just a bit
        # less than the left 1/3 of the stats area. It occupies about the top 15.5% of the image as well. Using this knowledge,
        # we can grab a rectangle starting at (0,0) and extending to x=33.3%, y=15.5% of the image height and then copy and
        # paste it twice, each time moving 1/3 of the image to the right. The result is that we'll have three sets of "Cost ##"
        # in the top row, but this will magically have the same font and color as the currently-masked text, and the OCR will
        # "latch on" much better with that junk row in place.
        if VisionCardOcrUtils.__USE_LATCHON_HACK is True:
            latchon_hack_height_ratio = .155
            latchon_hack_width_ratio = .3333
            stats_area_height, stats_area_width = stats_text_mask.shape[:2]
            latchon_hack_height = int(stats_area_height * latchon_hack_height_ratio)
            latchon_hack_width = int(stats_area_width * latchon_hack_width_ratio)
            latchon_hack_region = stats_converted_final_ocr_input_image.crop((0, 0, latchon_hack_width, latchon_hack_height)) # left, upper, right, lower)
            stats_converted_final_ocr_input_image.paste(latchon_hack_region, (latchon_hack_width, 0))
            stats_converted_final_ocr_input_image.paste(latchon_hack_region, (latchon_hack_width * 2, 0))

        if debug_vision_card is not None:
            debug_vision_card.stats_debug_image_step6_converted_final_ocr_input_image = stats_converted_final_ocr_input_image
            debug_vision_card.info_debug_image_step6_converted_final_ocr_input_image = info_converted_final_ocr_input_image

        # And last but not least... extract the text from that image.
        stats_extracted_text = pytesseract.image_to_string(stats_converted_final_ocr_input_image)
        info_extracted_text = pytesseract.image_to_string(info_converted_final_ocr_input_image)
        if debug_vision_card is not None:
            debug_vision_card.stats_debug_raw_text = stats_extracted_text
            debug_vision_card.info_debug_raw_text = info_extracted_text
        return (info_extracted_text, stats_extracted_text)

    @staticmethod
    def bindStats(stat_tuples_list, vision_card):
        """Binds 0 or more (stat_name, stat_value) tuples from the specified list to the specified vision card."""
        for stat_tuple in stat_tuples_list:
            VisionCardOcrUtils.bindStat(stat_tuple[0], stat_tuple[1], vision_card)

    @staticmethod
    def isStatName(text) -> bool:
        """Returns True if and only if the specified text is a valid name of a stat on a vision card.

        Stats are COST, HP, DEF, TP, SPR, AP, DEX, ATK, AGI, MAG and LUCK.
        """
        stat_names = {'COST', 'HP', 'DEF', 'TP', 'SPR', 'AP', 'DEX', 'ATK', 'AGI', 'MAG', 'LUCK'}
        return text.upper() in stat_names

    @staticmethod
    def bindStat(stat_name, stat_value, vision_card):
        """Binds the value of the stat having the specified name to the specified vision card.

        Raises an exception if the stat name does not conform to any of the standard stat names.
        """
        stat_name = stat_name.upper()
        if stat_name == 'COST':
            vision_card.Cost = stat_value
        elif stat_name == 'HP':
            vision_card.HP = stat_value
        elif stat_name == 'DEF':
            vision_card.DEF = stat_value
        elif stat_name == 'TP':
            vision_card.TP = stat_value
        elif stat_name == 'SPR':
            vision_card.SPR = stat_value
        elif stat_name == 'AP':
            vision_card.AP = stat_value
        elif stat_name == 'DEX':
            vision_card.DEX = stat_value
        elif stat_name == 'ATK':
            vision_card.ATK = stat_value
        elif stat_name == 'AGI':
            vision_card.AGI = stat_value
        elif stat_name == 'MAG':
            vision_card.MAG = stat_value
        elif stat_name == 'LUCK':
            vision_card.Luck = stat_value
        elif stat_name.startswith('PARTY ABILITY'):
            vision_card.PartyAbility = stat_value
        elif stat_name.startswith('BESTOWED EFFECTS'):
            vision_card.BestowedEffects = [stat_value]
        else:
            raise Exception('Unknown stat name: "{0}"'.format(stat_name))

    @staticmethod
    def intOrNone(rawValueString) -> int:
        """Parse a raw value string and return either the integer it represents, or None if it does not represent an integer."""
        try:
            return int(rawValueString, 10)
        except ValueError:
            return None

    @staticmethod
    def coerceMalformedCardName(raw_string: str) -> str:
        """Given a card name that may be very close to a real card name, tries to coerce
        optically-close-matches to a valid card name and returns it.

        For example, if the given string contains a right single quotation mark	(0x2019 / &rsquo;),
        this method will normalize it to a standard apostrophe (0x27 / &apos;).
        """
        return raw_string.replace('\u2019', "'")

    @staticmethod
    def coerceMalformedStatNames(raw_uppercase_strings: [str]) -> [str]:
        """Given an array of things that are possibly stat names, all uppercase, tries to coerce
        optically-close-matches to a valid stat name.

        Returns an array of the same size, with any close-matches coerced to their canonical form.
        For example, if given the string 'AGL' this method will coerce it to "AGI"
        """
        result = []
        for raw_uppercase_string in raw_uppercase_strings:
            if raw_uppercase_string == 'AGL':
                result.append('AGI')
            else:
                result.append(raw_uppercase_string)
        return result

    @staticmethod
    def fuzzyStatExtract(raw_line) -> []:
        """ Try to permissively parse a line of stats that might include garbage.

        The only assumption is that the text for the NAME of the stat has been correctly parsed.
        Numbers that are trash (e.g. a greater-than sign, a non-ascii character, etc) will be normalized
        to None. The return is a list of tuples of (stat name, stat value).

        Note that it is still possible for this method to return trash if the input is mangled in new
        and terrifying ways, such as there being spaces stuck inside of words, or OCR garbage that gets
        misinterpreted as numbers where there should have been blank space or a hyphen, etc.

        Most of the common cases are all handled below specifically, and this should account for the
        vast majority of text encountered. Any case that can't be normalized will raise an exception.
        """
        # The only characters that should appear in stats are letters and numbers. Throw everyhing else
        # away, this takes care of noise in the image that might cause a spurious '.' or similar to
        # appear where it should not be. The code below gracefully handles the absence of a value.
        baked = ''
        for _, one_char in enumerate(raw_line):
            if one_char.isalnum():
                baked += one_char
            else:
                baked += ' '

        # Strip whitespace from the sides, upper-case, and then split on whitespace.
        substrings = VisionCardOcrUtils.coerceMalformedStatNames(baked.upper().strip().split())
        num_substrings = len(substrings)

        # There are only a few possibilities, and they depend on the length of the substrings array
        # In all cases the first word must be a valid stat.
        if not VisionCardOcrUtils.isStatName(substrings[0]):
            raise Exception('First word must consist of only letters')

        # For debugging nasty case issues below, re-enable these lines:
        _debug_cases = True
        if _debug_cases:
            print('baked line: ' + baked)
            print('num substrings: ' + str(num_substrings))

        # Length 6: Special case: The Latch-On Hack
        # As described in extractRawTextFromVisionCard(...) later, there is a special hack made to
        # "hint" the OCR library to treat the text in the card as full lines of text. To do this the
        # "Cost ##" section of the stats image is tiled horizontally, creating a 6-tuple of
        # ('Cost', <value>, 'Cost', <value>, 'Cost', <value>) across an entire line.
        # Detect this case and restore sanity.
        if num_substrings == 6 and substrings[0] == 'COST' and substrings[2] == 'COST' and substrings[4] == 'COST':
            substrings = [substrings[0], substrings[1]]
            num_substrings = 2
            print('special case: latch-on hack line')
            # And then fall through to regular processing code.

        # Length 1: Just a name, with no number (implies value is nothing)
        if num_substrings == 1:
            return [(substrings[0], None)] # example: "Cost -"

        # Now the possibility of numbers also exists.

        # Length 2:
        # Case 2.1: A name and an integer value (one valid tuple)
        # Case 2.2: Two names and no integer values (OCR lost the first and second value)
        # Case 2.3: A name and garbage (OCR misread the second value)
        if num_substrings == 2:
            if substrings[1].isdecimal(): # Case 2.1
                if _debug_cases: print('Case 2.1') # pylint: disable=multiple-statements
                return [(substrings[0], VisionCardOcrUtils.intOrNone(substrings[1]))]
            if VisionCardOcrUtils.isStatName(substrings[1]): # Case 2.2
                if _debug_cases: print('Case 2.2') # pylint: disable=multiple-statements
                return [(substrings[0], None), (substrings[1], None)] # example "ATK - AGI -"
            if _debug_cases: print('Case 2.3') # pylint: disable=multiple-statements
            return [(substrings[0], None)] # case 2.3

        # Length 3:
        # Case 3.1: A name, an integer, and another name (OCR lost the second value)
        # Case 3.2: A name, a name, and a value (OCR lost the first value)
        # Case 3.3: A name, a name, and garbage (OCR lost the first value and misread the second value)
        # Case 3.4: A name, garbage, and another name (OCR misread the first value and lost the second value)
        if num_substrings == 3:
            if substrings[1].isdecimal() and VisionCardOcrUtils.isStatName(substrings[2]): # Case 3.1
                if _debug_cases: print('Case 3.1') # pylint: disable=multiple-statements
                return [(substrings[0], VisionCardOcrUtils.intOrNone(substrings[1])), (substrings[2], None)]
            if VisionCardOcrUtils.isStatName(substrings[1]) and substrings[2].isdecimal(): # Case 3.2
                if _debug_cases: print('Case 3.2') # pylint: disable=multiple-statements
                return [(substrings[0], None), (substrings[1], VisionCardOcrUtils.intOrNone(substrings[2]))]
            if VisionCardOcrUtils.isStatName(substrings[1]): # Case 3.3
                if _debug_cases: print('Case 3.3') # pylint: disable=multiple-statements
                return [(substrings[0], None), (substrings[1], None)]
            if VisionCardOcrUtils.isStatName(substrings[2]): # Case 3.4
                if _debug_cases: print('Case 3.4') # pylint: disable=multiple-statements
                return [(substrings[0], None), (substrings[2], None)]

        # Length 4:
        # Case 4.1: A name, an integer, another name, and an integer (happy case)
        # Case 4.2: A name, an integer, another name, and garbage (OCR lost the final value)
        # Case 4.3: A name, another name, anything... (uncecoverable garbage: OCR has got more than one value after the second name)
        # Case 4.4: A name, garbage, another name, and an integer (OCR misread the first value)
        # Case 4.5: A name, garbage, another name, and garbage (OCR misread the final value)
        if num_substrings == 4:
            if substrings[1].isdecimal() and VisionCardOcrUtils.isStatName(substrings[2]) and substrings[3].isdecimal(): # Case 4.1 (Happy case)
                if _debug_cases: print('Case 4.1') # pylint: disable=multiple-statements
                return [(substrings[0], VisionCardOcrUtils.intOrNone(substrings[1])), (substrings[2], VisionCardOcrUtils.intOrNone(substrings[3]))]
            if substrings[1].isdecimal() and VisionCardOcrUtils.isStatName(substrings[2]): # Case 4.2
                if _debug_cases: print('Case 4.2') # pylint: disable=multiple-statements
                return [(substrings[0], VisionCardOcrUtils.intOrNone(substrings[1])), (substrings[2], None)]
            if VisionCardOcrUtils.isStatName(substrings[1]): # Case 4.3
                if _debug_cases: print('Case 4.3') # pylint: disable=multiple-statements
                raise Exception('Malformed input')
            if VisionCardOcrUtils.isStatName(substrings[2]) and substrings[3].isdecimal(): # Case 4.4
                if _debug_cases: print('Case 4.4') # pylint: disable=multiple-statements
                return [(substrings[0], None), (substrings[2], VisionCardOcrUtils.intOrNone(substrings[3]))]
            if VisionCardOcrUtils.isStatName(substrings[2]): # Case 4.5
                if _debug_cases: print('Case 4.5') # pylint: disable=multiple-statements
                return [(substrings[0], None), (substrings[2], None)]

        # Anything else (5 groups in the split, anything that fell past 4.5 above, etc) cannot be handled. Give up.
        print('Problematic line: ' + raw_line)
        print('Substrings: ' + str(substrings))
        raise Exception('Malformed input')

    @staticmethod
    def extractVisionCardFromScreenshot(vision_card_image, is_debug = False) -> VisionCard:
        """Fully process and extract structured, well-defined text from a Vision Card image.

        If is_debug == True, also captures debugging information.
        """
        # After the first major vision card update, it became possible for additional stats to be
        # boosted by vision cards. Thus the raw text changed, and now has a more complex form.
        # An example of the raw text is below, note that the order is fixed and should not vary:
        # ---- BEGIN RAW DUMP ----
        # Cost 50
        # HP 211 DEF -
        # TP - SPR -
        # AP - DEX _
        # ATK 81 AGI -
        # MAG 56 Luck -
        # Party Ability Cau
        #
        # ATK Up 30%
        #
        # Bestowed Effects
        #
        # Acquired JP Up 50%
        # TTR
        #
        # Awakening Bonus Resistance Display
        # ---- END RAW DUMP ----
        # Note that the "Cau" in "Party Ability Cau" is garbage from the icon that was added to the
        # vision card display showing the type of boost that the text described. Additionally, the
        # text is surrounded by garbage both before the "Cost 50" and after the "Acquired JP Up 50%"
        # due to (on top) the level gauge / star rating and (on bottom) awakening bonus / resistance
        # display buttons.
        #
        # Also, Bestowed Effects can contain multiple lines. Each line is a different effect.
        #
        # Thus text processing starts at the line that starts with "Cost" and finishes at the line that
        # starts with "Awakening Bonus"

        # A state machine will be used to accumulate the necessary strings for processing.
        AT_START = 0
        IN_PARTY_ABILITY = 1
        IN_BESTOWED_EFFECTS = 2
        DONE = 3
        progress = AT_START
        result = VisionCard()
        raw_info_text, raw_stats_text = VisionCardOcrUtils.extractRawTextFromVisionCard(vision_card_image, result if is_debug else None)
        # TODO: Remove these when the code is more bullet-proof
        print('raw info text from card:' + raw_info_text)
        print('raw stats text from card:' + raw_stats_text)
        result.Name = VisionCardOcrUtils.coerceMalformedCardName(raw_info_text.splitlines(keepends=False)[0].strip())
        # This regex is used to ignore trash from OCR that might appear at the boundaries of the party/bestowed ability boxes.
        safe_effects_regex = re.compile(r'^[a-zA-Z0-9 \+\-\%\&]+$')

        for line in raw_stats_text.splitlines(keepends=False):
            line = line.strip()
            if not line:
                continue
            upper = line.upper()
            if progress == AT_START:
                if upper.startswith('COST') or \
                upper.startswith('HP') or \
                upper.startswith('TP') or \
                upper.startswith('AP') or \
                upper.startswith('ATK') or \
                upper.startswith('MAG'):
                    try:
                        VisionCardOcrUtils.bindStats(VisionCardOcrUtils.fuzzyStatExtract(line), result)
                    # pylint: disable=broad-except
                    except Exception as ex:
                        result.error_messages.append(str(ex))
                        return result
                elif upper.startswith('PARTY'):
                    progress = IN_PARTY_ABILITY
            elif progress == IN_PARTY_ABILITY:
                if upper.startswith('BESTOWED EFFECTS'):
                    progress = IN_BESTOWED_EFFECTS
                elif len(upper) < VisionCardOcrUtils.MIN_PARTY_ABILITY_STRING_LENGTH_SANITY:
                    pass # Ignore trash, such as the "Cau" in the example above, if it appears on its own line.
                elif result.PartyAbility is not None: # should not happen, party ability is only one line of text
                    result.error_messages.append('Found multiple party ability lines in vision card')
                    return result
                elif safe_effects_regex.match(line):
                    result.PartyAbility = line
            elif progress == IN_BESTOWED_EFFECTS:
                if upper.startswith('AWAKENING BONUS'):
                    progress = DONE
                elif len(upper) < VisionCardOcrUtils.MIN_BESTOWED_ABILITY_STRING_LENGTH_SANITY:
                    pass # Ignore trash, such as the "TTR" in the example above, if it appears on its own line.
                elif safe_effects_regex.match(line):
                    result.BestowedEffects.append(line)
            elif progress == DONE:
                break
        if len(result.error_messages) == 0:
            result.successfully_extracted = True
        return result

    @staticmethod
    def mergeDebugImages(card: VisionCard) -> Image:
        """Merge all of the debugging images into one and return it."""
        return VisionCardOcrUtils.stitchImages([
            card.debug_image_step1_gray,
            card.debug_image_step2_blurred,
            card.debug_image_step3_thresholded,
            card.stats_debug_image_step4_cropped_gray,
            card.stats_debug_image_step5_cropped_gray_inverted,
            card.stats_debug_image_step6_converted_final_ocr_input_image,
            card.info_debug_image_step4_cropped_gray,
            card.info_debug_image_step5_cropped_gray_inverted,
            card.info_debug_image_step6_converted_final_ocr_input_image])

    @staticmethod
    def stitchImages(images):
        """Combine images horizontally, into a single large image."""
        total_width = 0
        max_height = 0
        for one_image in images:
            total_width += one_image.width
            max_height = max(max_height, one_image.height)
        result = Image.new('RGB', (total_width, max_height))
        left_pad = 0
        for one_image in images:
            result.paste(one_image, (left_pad, 0))
            left_pad += one_image.width
        return result

    @staticmethod
    def invokeStandalone(path):
        """For local/standalone running, a method that can process an image from the filesystem or a URL."""
        vision_card_image = None
        if path.startswith('http'):
            # Read image from the specified URL (e.g., image uploaded to a Discord channel)
            vision_card_image = VisionCardOcrUtils.downloadScreenshotFromUrl(path)
        else:
            # Read image from the specified path
            vision_card_image = VisionCardOcrUtils.loadScreenshotFromFilesystem(sys.argv[1])
        vision_card = VisionCardOcrUtils.extractVisionCardFromScreenshot(vision_card_image, True)
        debug_image = VisionCardOcrUtils.mergeDebugImages(vision_card)
        debug_image.save('debug.png')
        print(vision_card)

if __name__ == "__main__":
    VisionCardOcrUtils.invokeStandalone(sys.argv[1])
