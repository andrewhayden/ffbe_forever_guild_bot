"""A module for working with Google Sheets across the bot."""

class AmbiguousSearchException(Exception):
    """An exception indicating a lookup failure due to ambiguous results.
    Attributes:
        message -- explanation of the error
    """
    def __init__(self, message):
        super(AmbiguousSearchException, self).__init__(message)
        self.message = message

class NoResultsException(Exception):
    """An exception indicating a lookup failure due to lack of any match.
    Attributes:
        message -- explanation of the error
    """
    def __init__(self, message):
        super(NoResultsException, self).__init__(message)
        self.message = message

def toA1(intValue):
    """Convert an integer value to "A1 Notation", i.e. the column name in a spreadsheet. Max value 26*26."""
    if intValue > 26*26:
        raise Exception('number too large')
    if intValue <= 26:
        return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[intValue - 1]
    bigPart = intValue // 26
    remainder = intValue - (bigPart * 26)
    return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[bigPart - 1] + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[remainder - 1]


def fromA1(a1Value):
    """Convert a value in "A1 Notation", i.e. the column name in a spreadsheet, to a 1-based integer offset."""
    numChars = len(a1Value)
    if numChars > 2:
        raise Exception('number too large: ' + a1Value)
    a1Value = a1Value.upper()
    result = (ord(a1Value[-1]) - ord('A')) + 1
    if numChars == 2:
        upper = (ord(a1Value[-2]) - ord('A')) + 1
        result = (26 * upper) + result
    return result

def fuzzyMatches(sheet_text, search_text):
    """Performs a fuzzy match within the specified text.

    Breaks the specified search_text on whitespace, then does a case-insensitive substring match on each of the
    resulting words. If ALL the words are found somewhere in the sheet_text, then it is considered to be a
    match and the method returns True; otherwise, returns False.
    """
    words = search_text.split() # by default splits on all whitespace PRESERVING punctuation, which is important...
    for word in words:
        if not word.lower() in sheet_text.lower():
            return False
    return True

def normalizeName(fancy_name):
    """Normalize a name, lowercasing it and replacing spaces with hyphens."""
    return fancy_name.strip().lower().replace(' ', '-')

def safeWorksheetName(sheet_name):
    """Ensures that the name of a worksheet is safe to use."""
    if "'" in sheet_name:
        raise Exception('Names must not contain apostrophes.')
    return "'" + sheet_name + "'"

def fuzzyFindRow(spreadsheet_app, document_id, sheet_name, search_text, columnA1):
    """Return the row number (integer value, 1-based) and content of the cell for the given search parameters.

    Parameters:
    spreadsheet_app: The application object for accessing Google Sheets
    document_id: The ID of the spreadsheet in which to perform the search
    sheet_name: The name of the sheet in which to perform the search
    search_text: The text to find (see rules below)
    columnA1: The column in which to search (in A1 notation)

    Search works as follows:
    1. If the search_text starts with and ends with double quotes, only an case-insensitive exact matches and is returned.
    2. Else, if there is exactly one cell whose case-insensitive name starts with the specified search_text, it is returned.
    3. Else, if there is exactly one cell whose case-insensitive name contains all of the words in the specified search_text, it is returned.
    4. Else, an exception is raised with a safe error message that can be shown publicly.
    """
    range_name = safeWorksheetName(sheet_name) + '!' + columnA1 + ':' + columnA1
    search_rows = None
    normalized_search_text = normalizeName(search_text)
    try:
        values = spreadsheet_app.values().get(spreadsheetId=document_id, range=range_name).execute()
        search_rows = values.get('values', [])
        if not search_rows:
            raise Exception('')
    except:
        # pylint: disable=raise-missing-from
        raise NoResultsException(
            'No such sheet : {0}'.format(sheet_name))  # deliberately low on details as this may be public.

    fuzzy_matches = []
    prefix_matches = []
    row_count = 0
    exact_match_string = None
    if search_text.startswith('"') and search_text.endswith('"'):
        exact_match_string = (search_text[1:-1])
    for search_row in search_rows:
        row_count += 1
        for candidate_text in search_row: # There's really just one but it's easiest to write it this way
            if exact_match_string and (candidate_text.lower() == exact_match_string.lower()):
                return (row_count, candidate_text)
            if normalizeName(candidate_text).startswith(normalized_search_text):
                prefix_matches.append((row_count, candidate_text))
            if fuzzyMatches(candidate_text, search_text):
                fuzzy_matches.append((row_count, candidate_text))
    if exact_match_string or (len(fuzzy_matches) == 0 and len(prefix_matches) == 0):
        raise NoResultsException('No match for ```{0}```'.format(search_text))
    if len(prefix_matches) == 1: # Prefer prefix match.
        return prefix_matches[0]
    if len(fuzzy_matches) == 1: # Fall back to fuzzy match
        return fuzzy_matches[0]
    all_matches = set()
    all_matches.update(prefix_matches)
    all_matches.update(fuzzy_matches)
    all_matches_string = ""
    all_matches = list(all_matches)
    max_results = min(5, len(all_matches))
    for index in range(0, max_results):
        all_matches_string += all_matches[index][1]
        if index < max_results - 1:
            all_matches_string += ", "
    raise AmbiguousSearchException(
        'Multiple matches for ```{0}``` Please make your text more specific and try again. '\
        'For an exact match, enclose your text in double quotes. '\
        'Possible matches (max 5) are {1}'.format(search_text, all_matches_string))

def fuzzyFindColumn(spreadsheet_app, document_id, sheet_name, search_text, rowNumber):
    """Return the column (A1 notation) and content of the cell for the given search parameters.

    Parameters:
    spreadsheet_app: The application object for accessing Google Sheets
    document_id: The ID of the spreadsheet in which to perform the search
    sheet_name: The name of the sheet in which to perform the search
    search_text: The text to find (see rules below)
    columnA1: The column in which to search (in A1 notation)

    Search works as follows:
    1. If the search_text starts with and ends with double quotes, only an case-insensitive exact matches and is returned.
    2. Else, if there is exactly one cell whose case-insensitive name starts with the specified search_text, it is returned.
    3. Else, if there is exactly one cell whose case-insensitive name contains all of the words in the specified search_text, it is returned.
    4. Else, an exception is raised with a safe error message that can be shown publicly.
    """
    range_name = safeWorksheetName(sheet_name) + '!' + rowNumber + ':' + rowNumber
    search_rows = None
    normalized_search_text = normalizeName(search_text)
    try:
        values = spreadsheet_app.values().get(spreadsheetId=document_id, range=range_name).execute()
        search_rows = values.get('values', [])
        if not search_rows:
            raise Exception('')
    except:
        # pylint: disable=raise-missing-from
        raise NoResultsException(
            'No such sheet : {0}'.format(sheet_name))  # deliberately low on details as this may be public.

    # Search for a match and return when found.
    fuzzy_matches = []
    prefix_matches = []
    exact_match_string = None
    if search_text.startswith('"') and search_text.endswith('"'):
        exact_match_string = (search_text[1:-1])
    for search_row in search_rows:
        column_count = 0
        for candidate_text in search_row: # There's really just one but it's easiest to write it this way
            column_count += 1
            if exact_match_string and (candidate_text.lower() == exact_match_string.lower()):
                column_A1 = toA1(column_count)
                return (column_A1, candidate_text)
            if normalizeName(candidate_text).startswith(normalized_search_text):
                column_A1 = toA1(column_count)
                prefix_matches.append((column_A1, candidate_text))
            if fuzzyMatches(candidate_text, search_text):
                column_A1 = toA1(column_count)
                fuzzy_matches.append((column_A1, candidate_text))
    if exact_match_string or (len(fuzzy_matches) == 0 and len(prefix_matches) == 0):
        raise NoResultsException('No match for ```{0}```'.format(search_text))
    if len(prefix_matches) == 1: # Prefer prefix match.
        return prefix_matches[0]
    if len(fuzzy_matches) == 1: # Fall back to fuzzy match
        return fuzzy_matches[0]
    all_matches = set()
    all_matches.update(prefix_matches)
    all_matches.update(fuzzy_matches)
    all_matches_string = ""
    all_matches = list(all_matches)
    max_results = min(5, len(all_matches))
    for index in range(0, max_results):
        all_matches_string += all_matches[index][1]
        if index < max_results - 1:
            all_matches_string += ", "
    raise AmbiguousSearchException(
        'Multiple matches for ```{0}``` Please make your text more specific and try again. '\
        'For an exact match, enclose your text in double quotes. '\
        'Possible matches (max 5) are {1}'.format(search_text, all_matches_string))
