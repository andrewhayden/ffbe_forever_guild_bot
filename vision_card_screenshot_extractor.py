import re
import sys
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

def downloadScreenshotFromUrl(url):
    try:
        pilImage = Image.open(requests.get(url, stream=True).raw)
        opencvImage = cv2.cvtColor(numpy.array(pilImage), cv2.COLOR_RGB2BGR)
        return opencvImage
    except Exception as e:
        print(str(e))
        raise Exception('Error while downloading or converting image: ' + url)

def extractRawTextFromVisionCard(image):
    height, width, channels = image.shape

    # For vision cards, the screen is divided into left and right. The righ side
    # always contains artwork. Drop it to reduce the contour iteration that will
    # be needed.
    image = image[0:height, 0:int(width/2)]

    # Convert the resized image to grayscale, blur it slightly, and threshold it
    # to set up the input to the contour finder.
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresholded = cv2.threshold(blurred, 70, 255, cv2.THRESH_BINARY)[1]

    # Find and enumerate all the contours.
    contours = cv2.findContours(thresholded.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
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
        if (largestArea >= area):
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
    croppedGrayscale = gray[largestY:(largestY+largestH), largestX:(largestX+largestW)]
    croppedGrayscaleInverted = cv2.bitwise_not(croppedGrayscale)

    # Find only the darkest parts of the image, which should now be the text.
    lowerBoundHsvValue = 0
    upperBoundHsvValue = 80
    mainTextMask = cv2.inRange(croppedGrayscaleInverted, lowerBoundHsvValue, upperBoundHsvValue)
    mainTextMask = cv2.bitwise_not(mainTextMask)
    finalImage = mainTextMask

    # show the output image
    # cv2.namedWindow("Result",  cv2.WINDOW_NORMAL)
    # cv2.imshow("Result", finalImage)
    # cv2.waitKey(30000)

    # Yank text
    regularImage = Image.fromarray(finalImage)
    extractedText = pytesseract.image_to_string(regularImage)
    return extractedText

def extractStat(rawStatString):
    match = VISION_CARD_MAINSTAT_PATTERN.match(rawStatString)
    if not match:
        raise Exception('No stat found in text: "{0}"'.format(rawStatString))
    statname = match.group('statname').upper()
    statvalue = int(match.group('statvalue'))
    return (statname, statvalue)

def extractNiceTextFromVisionCard(image):
    raw = extractRawTextFromVisionCard(image)
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
        if (progress == AT_START):
            if upper.startswith('HP'):
                found_hp = extractStat(line)
            elif upper.startswith('ATK'):
                found_atk = extractStat(line)
            elif upper.startswith('MAG'):
                found_mag = extractStat(line)
            elif (upper.startswith('BESTOW')):
                progress = IN_BESTOWED_EFFECTS
            else:
                pass
        elif (progress == IN_BESTOWED_EFFECTS):
            if (upper.startswith('PARTY')):
                progress = IN_PARTY_ABILITY
            else:
                bestowed_effects.append(line)
        elif (progress == IN_PARTY_ABILITY):
            if len(upper) < MIN_PARTY_ABILITY_STRING_LENGTH_SANITY:
                pass
            if (upper.startswith('AWAKENING')):
                progress = DONE
            else:
                party_ability = line
                progress = DONE
        elif (progress == DONE):
            break
    result = {}
    result['HP'] = found_hp[1]
    result['MAG'] = found_mag[1]
    result['ATK'] = found_atk[1]
    result['Bestowed Effects'] = bestowed_effects
    result['Party Ability'] = party_ability
    return result

if __name__ == "__main__":
    path = sys.argv[1]
    image = None
    if (path.startswith('http')):
        image = downloadScreenshotFromUrl(path)
    else:
        image = cv2.imread(sys.argv[1])
    print(extractNiceTextFromVisionCard(image))
