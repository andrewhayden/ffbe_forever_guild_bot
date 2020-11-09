"""A module for working with Google Sheets across the bot."""
from wotv_bot_common import ExposableException

class AmbiguousSearchException(ExposableException):
    """An exception indicating a lookup failure due to ambiguous results.
    Attributes:
        message -- explanation of the error
    """
    def __init__(self, message):
        super(AmbiguousSearchException, self).__init__(message)
        self.message = message

class NoResultsException(ExposableException):
    """An exception indicating a lookup failure due to lack of any match.
    Attributes:
        message -- explanation of the error
    """
    def __init__(self, message):
        super(NoResultsException, self).__init__(message)
        self.message = message

class WorksheetUtils:
    """Collection of static utility methods work working on bot-maintained worksheets."""
    @staticmethod
    def toA1(intValue):
        """Convert an integer value to "A1 Notation", i.e. the column name in a spreadsheet. Max value 26*26."""
        if intValue > 26*26:
            raise Exception('number too large')
        if intValue <= 26:
            return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[intValue - 1]
        bigPart = intValue // 26
        remainder = intValue - (bigPart * 26)
        return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[bigPart - 1] + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[remainder - 1]


    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def normalizeName(fancy_name):
        """Normalize a name, lowercasing it and replacing spaces with hyphens."""
        return fancy_name.strip().lower().replace(' ', '-')

    @staticmethod
    def safeWorksheetName(sheet_name):
        """Ensures that the name of a worksheet is safe to use."""
        if "'" in sheet_name:
            raise Exception('Names must not contain apostrophes.')
        return "'" + sheet_name + "'"

    @staticmethod
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
        range_name = WorksheetUtils.safeWorksheetName(sheet_name) + '!' + columnA1 + ':' + columnA1
        search_rows = None
        normalized_search_text = WorksheetUtils.normalizeName(search_text)
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
                if WorksheetUtils.normalizeName(candidate_text).startswith(normalized_search_text):
                    prefix_matches.append((row_count, candidate_text))
                if WorksheetUtils.fuzzyMatches(candidate_text, search_text):
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

    @staticmethod
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
        range_name = WorksheetUtils.safeWorksheetName(sheet_name) + '!' + rowNumber + ':' + rowNumber
        search_rows = None
        normalized_search_text = WorksheetUtils.normalizeName(search_text)
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
                    column_A1 = WorksheetUtils.toA1(column_count)
                    return (column_A1, candidate_text)
                if WorksheetUtils.normalizeName(candidate_text).startswith(normalized_search_text):
                    column_A1 = WorksheetUtils.toA1(column_count)
                    prefix_matches.append((column_A1, candidate_text))
                if WorksheetUtils.fuzzyMatches(candidate_text, search_text):
                    column_A1 = WorksheetUtils.toA1(column_count)
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

    @staticmethod
    def generateRequestsToAddColumnToAllSheets(spreadsheet, columnA1: str, left_or_right_of: str, set_header: bool = False,
                                               header_row_index: int = 0, header_text: str = None, header_url: str = None) -> [{}]:
        """Generate and return a series of Google Sheets requests that will add a column (with optional header row) to every worksheet in the spreadsheet.

        :param spreadsheet: the spreadsheet to generate requests for
        :param column_A1: the column from which to copy formatting, in A1 notation (see next parameter below)
        :param left_or_right_of: either 'left-of', meaning to insert left-of columnA1, or 'right-of', meaning to insert right-of columnA1
        :param set_header: if True, set a header row in the newly inserted column. Defaults to False (all remaining parameters ignored)
        :param header_row_index: The 0-based offset of the header row to set the value of, i.e. a value of zero refers to the first row
        :param header_text: The text to set in the header row
        :param header_url: If set, converts the header_text to a hyperlink having the specified URL target.
        """
        columnInteger = WorksheetUtils.fromA1(columnA1)
        inheritFromBefore = None
        if left_or_right_of == 'left-of':
            inheritFromBefore = False  # Meaning, inherit from right
        elif left_or_right_of == 'right-of':
            inheritFromBefore = True  # Meaning, inherit from left
            columnInteger += 1
        else:
            raise ExposableException('Incorrect parameter for position of new column, must be "left-of" or "right-of": ' + left_or_right_of)

        allRequests = []
        for sheet in spreadsheet['sheets']:
            sheetId = sheet['properties']['sheetId']
            # First create an 'insertDimension' request to add a blank column on each sheet.
            insertDimensionRequest = {
                'insertDimension': {
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#insertdimensionrequest
                    'inheritFromBefore': inheritFromBefore,
                    'range': {
                        'sheetId': sheetId,
                        'dimension': 'COLUMNS',
                        'startIndex': columnInteger - 1,
                        'endIndex': columnInteger
                    }
                }
            }
            allRequests.append(insertDimensionRequest)

            if not set_header:
                continue

            # Now add the header row to the new column on each sheet.
            startColumnIndex = columnInteger - 1
            userEnteredValue = None
            if header_url:
                userEnteredValue = {
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/other#ExtendedValue
                    'formulaValue': '=HYPERLINK("' + header_url + '", "' + header_text + '")'
                }
            else:
                userEnteredValue = {
                    'stringValue': header_text
                }

            updateCellsRequest = {
                'updateCells': {
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#updatecellsrequest
                    'rows': [{
                        # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/sheets#RowData
                        'values': [{
                            # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/cells#CellData
                            'userEnteredValue': userEnteredValue
                        }]
                    }],
                    'fields': 'userEnteredValue',
                    'range': {
                        'sheetId': sheetId,
                        'startRowIndex': header_row_index,  # inclusive
                        'endRowIndex': header_row_index + 1,  # exclusive
                        'startColumnIndex': startColumnIndex,  # inclusive
                        'endColumnIndex': startColumnIndex + 1  # exclusive
                    }
                }
            }
            allRequests.append(updateCellsRequest)
        return allRequests

    @staticmethod
    def generateRequestsToAddRowToAllSheets(spreadsheet, row_1_based: int, above_or_below: str, set_header: bool = False,
                                               header_column_A1: str = None, header_text: str = None, header_url: str = None) -> [{}]:
        """Generate and return a series of Google Sheets requests that will add a row (with optional header column) to every worksheet in the spreadsheet.

        :param spreadsheet: the spreadsheet to generate requests for
        :param row_1_based: the row from which to copy formatting (first row is row 1) (see next parameter below)
        :param above_or_below: either 'above', meaning to insert just above row_1_based, or 'after', meaning to insert just below row_1_based
        :param set_header: if True, set a header column in the newly inserted row. Defaults to False (all remaining parameters ignored)
        :param header_column_A1: The A1 notation of the header column to set the value of, i.e. a value of 'A' refers to the first column
        :param header_text: The text to set in the header column
        :param header_url: If set, converts the header_text to a hyperlink having the specified URL target.
        """
        inheritFromBefore = None
        if above_or_below == 'above':
            inheritFromBefore = False  # Meaning, inherit from below
        elif above_or_below == 'below':
            inheritFromBefore = True  # Meaning, inherit from above
            row_1_based += 1
        else:
            raise ExposableException('Incorrect parameter for position of new row, must be "above" or "below": ' + above_or_below)

        allRequests = []
        for sheet in spreadsheet['sheets']:
            sheetId = sheet['properties']['sheetId']
            # First create an 'insertDimension' request to add a blank row on each sheet.
            insertDimensionRequest = {
                'insertDimension': {
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#insertdimensionrequest
                    'inheritFromBefore': inheritFromBefore,
                    'range': {
                        'sheetId': sheetId,
                        'dimension': 'ROWS',
                        'startIndex': row_1_based - 1,
                        'endIndex': row_1_based
                    }
                }
            }
            allRequests.append(insertDimensionRequest)

            if not set_header:
                continue

            # Now add the header row to the new column on each sheet.
            startRowIndex = row_1_based - 1
            userEnteredValue = None
            if header_url:
                userEnteredValue = {
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/other#ExtendedValue
                    'formulaValue': '=HYPERLINK("' + header_url + '", "' + header_text + '")'
                }
            else:
                userEnteredValue = {
                    'stringValue': header_text
                }

            updateCellsRequest = {
                'updateCells': {
                    # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#updatecellsrequest
                    'rows': [{
                        # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/sheets#RowData
                        'values': [{
                            # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/cells#CellData
                            'userEnteredValue':userEnteredValue
                        }]
                    }],
                    'fields': 'userEnteredValue',
                    'range': {
                        'sheetId': sheetId,
                        'startRowIndex': startRowIndex,  # inclusive
                        'endRowIndex': startRowIndex+1,  # exclusive
                        'startColumnIndex': WorksheetUtils.fromA1(header_column_A1) - 1,  # inclusive
                        'endColumnIndex': WorksheetUtils.fromA1(header_column_A1)  # exclusive
                    }
                }
            }
            allRequests.append(updateCellsRequest)
        return allRequests

    @staticmethod
    def generateRequestToSetCellText(sheetId, row_1_based: int, column_A1: str, text: str, url: str = None):
        """Generate and return a Google Sheets request that will set the specified cell to the specified text value (with optional hyperlink).

        :param sheetId: the ID of the sheet (tab) within the spreadsheet to generate the request for
        :param row_1_based: the 1-based row number of the cell to be updated
        :param column_A1: The A1 notation of the column of the cell to be updated, i.e. a value of 'A' refers to the first column
        :param text: The text to set
        :param url: If set, converts the text to a hyperlink having the specified URL target.
        """
        userEnteredValue = None
        if url:
            userEnteredValue = {
                # Format: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/other#ExtendedValue
                'formulaValue': '=HYPERLINK("' + url + '", "' + text + '")'
            }
        else:
            userEnteredValue = {
                'stringValue': text
            }
        updateCellsRequest = {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'userEnteredValue': userEnteredValue
                    }]
                }],
                'fields': 'userEnteredValue',
                'range': {
                    'sheetId': sheetId,
                    'startRowIndex': row_1_based - 1,  # inclusive
                    'endRowIndex': row_1_based,  # exclusive
                    'startColumnIndex': WorksheetUtils.fromA1(column_A1)-1,  # inclusive
                    'endColumnIndex': WorksheetUtils.fromA1(column_A1)  # exclusive
                }
            }
        }
        return updateCellsRequest
