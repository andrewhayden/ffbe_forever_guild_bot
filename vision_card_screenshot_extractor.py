"""A module for extracting structured data from Vision Card screenshots."""
import re
import sys
from dataclasses import dataclass
import cv2
import imutils
import numpy
import pytesseract
import requests # for downloading images
from PIL import Image

VISION_CARD_MAINSTAT_PATTERN = re.compile(r'^(?P<statname>[a-zA-Z]+)\s+(?P<statvalue>[0-9]+)$')

# Ignore any party ability that is a string shorter than this length, usually
# garbage from OCR gone awry.
MIN_PARTY_ABILITY_STRING_LENGTH_SANITY = 4

# dataclass
@dataclass
class VisionCard:
    """Contains all the raw stats for a vision card."""
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
    BestowedEffects: str = None

def downloadScreenshotFromUrl(url):
    """Download a vision card screenshot from the specified URL and return as an OpenCV image object."""
    try:
        pilImage = Image.open(requests.get(url, stream=True).raw)
        opencvImage = cv2.cvtColor(numpy.array(pilImage), cv2.COLOR_RGB2BGR)
        return opencvImage
    except Exception as e:
        print(str(e))
        # pylint: disable=raise-missing-from
        raise Exception('Error while downloading or converting image: ' + url) # deliberately low on details as this is replying in Discord.

def extractRawTextFromVisionCard(vision_card_image):
    """Get the raw, unstructured text from a vision card (basically the raw OCR dump string)."""
    height, width, _ = vision_card_image.shape # ignored third element of the tuple is 'channels'

    # For vision cards, the screen is divided into left and right. The right side
    # always contains artwork. Drop it to reduce the contour iteration that will
    # be needed.
    vision_card_image = vision_card_image[0:height, 0:int(width/2)]

    # Convert the resized image to grayscale, blur it slightly, and threshold it
    # to set up the input to the contour finder.
    gray_image = cv2.cvtColor(vision_card_image, cv2.COLOR_BGR2GRAY)
    blurred_image = cv2.GaussianBlur(gray_image, (5, 5), 0)
    thresholded_image = cv2.threshold(blurred_image, 70, 255, cv2.THRESH_BINARY)[1]

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
    # Crop and invert the image, we need black on white.
    # Note that cropping via slicing has x values first, then y values
    cropped_gray_image = gray_image[largestY:(largestY+largestH), largestX:(largestX+largestW)]
    cropped_gray_inverted_image = cv2.bitwise_not(cropped_gray_image)

    # Find only the darkest parts of the image, which should now be the text.
    lowerBoundHsvValue = 0
    upperBoundHsvValue = 80
    main_text_mask = cv2.inRange(cropped_gray_inverted_image, lowerBoundHsvValue, upperBoundHsvValue)
    main_text_mask = cv2.bitwise_not(main_text_mask)
    final_ocr_input_image = main_text_mask

    # show the output image
    # cv2.namedWindow("Result",  cv2.WINDOW_NORMAL)
    # cv2.imshow("Result", finalImage)
    # cv2.waitKey(30000)

    # Now convert back to a regular Python image from CV2.
    converted_final_ocr_input_image = Image.fromarray(final_ocr_input_image)
    # And last but not least... extract the text from that image.
    extractedText = pytesseract.image_to_string(converted_final_ocr_input_image)
    return extractedText

def extractStat(rawStatString):
    """Return a tuple of (stat name, stat value) from a raw OCR'd string"""
    match = VISION_CARD_MAINSTAT_PATTERN.match(rawStatString)
    if not match:
        raise Exception('No stat found in text: "{0}"'.format(rawStatString))
    statname = match.group('statname').upper()
    statvalue = int(match.group('statvalue'))
    return (statname, statvalue)

def extractNiceTextFromVisionCard(vision_card_image):
    """Fully process and extract structured, well-defined text from a Vision Card image."""
    raw = extractRawTextFromVisionCard(vision_card_image)
    # After the first major vision card update, it became possible for additional stats to be
    # boosted by vision cards. Thus the raw text changed, and now has a more complex form.
    # And example of the raw text is below:
    #
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
    #
    # Note that the "Cau" in "Party Ability Cau" is garbage from the icon that was added to the
    # vision card display showing the type of boost that the text described. Additionally, the
    # text is surrounded by garbage both before the "Cost 50" and after the "Acquired JP Up 50%"
    # due to (on top) the level gauge / star rating and (on bottom) awakening bonus / resistance
    # display buttons.
    #
    # Thus text processing starts at the line that starts with "Cost" and finishes after the
    # first non-blank line that follows the line that starts with "Bestowed EFfects".

    print('raw text from card:' + raw)
    AT_START = 0
    IN_BESTOWED_EFFECTS = 1
    IN_PARTY_ABILITY = 2
    DONE = 3

    progress = AT_START

    found_hp = None
    found_atk = None
    found_mag = None
    bestowed_effects = []
    party_ability = None

    for line in raw.splitlines(keepends=False):
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        if progress == AT_START:
            if upper.startswith('HP'):
                found_hp = extractStat(line)
            elif upper.startswith('ATK'):
                found_atk = extractStat(line)
            elif upper.startswith('MAG'):
                found_mag = extractStat(line)
            elif upper.startswith('BESTOW'):
                progress = IN_BESTOWED_EFFECTS
            else:
                pass
        elif progress == IN_BESTOWED_EFFECTS:
            if upper.startswith('PARTY'):
                progress = IN_PARTY_ABILITY
            else:
                bestowed_effects.append(line)
        elif progress == IN_PARTY_ABILITY:
            if len(upper) < MIN_PARTY_ABILITY_STRING_LENGTH_SANITY:
                pass
            if upper.startswith('AWAKENING'):
                progress = DONE
            else:
                party_ability = line
                progress = DONE
        elif progress == DONE:
            break
    result = {}
    result['HP'] = found_hp[1]
    result['MAG'] = found_mag[1]
    result['ATK'] = found_atk[1]
    result['Bestowed Effects'] = bestowed_effects
    result['Party Ability'] = party_ability
    return result

def invokeStandalone(path):
    """For local/standalone running, a method that can process an image from the filesystem or a URL."""
    vision_card_image = None
    if path.startswith('http'):
        # Read image from the specified URL (e.g., image uploaded to a Discord channel)
        vision_card_image = downloadScreenshotFromUrl(path)
    else:
        # Read image from the specified path
        vision_card_image = cv2.imread(sys.argv[1])
    print(extractNiceTextFromVisionCard(vision_card_image))

if __name__ == "__main__":
    invokeStandalone(sys.argv[1])
