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

    # Unit names are on column B.
    range_name = safeWorksheetName(sheet_name) + '!' + columnA1 + ':' + columnA1
    unit_name_rows = None
    unit_name = normalizeName(search_text)
    try:
        values = spreadsheet_app.values().get(spreadsheetId=document_id, range=range_name).execute()
        unit_name_rows = values.get('values', [])
        if not unit_name_rows:
            raise Exception('')
    except:
        # pylint: disable=raise-missing-from
        raise Exception(
            'No such sheet : {0}'.format(sheet_name))  # deliberately low on details as this may be public.

    fuzzy_matches = []
    prefix_matches = []
    row_count = 0
    exact_match_string = None
    if search_text.startswith('"') and search_text.endswith('"'):
        exact_match_string = (search_text[1:-1])
    for unit_name_row in unit_name_rows:
        row_count += 1
        for pretty_name in unit_name_row:
            if exact_match_string and (pretty_name.lower() == exact_match_string.lower()):
                return (row_count, pretty_name)
            if normalizeName(pretty_name).startswith(unit_name):
                prefix_matches.append((row_count, pretty_name))
            if fuzzyMatches(pretty_name, search_text):
                fuzzy_matches.append((row_count, pretty_name))
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
