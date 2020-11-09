"""Manages the Esper Resonance spreadsheet."""
from wotv_bot_common import ExposableException
from admin_utils import AdminUtils
from worksheet_utils import WorksheetUtils

class EsperResonanceManager:
    """Main class for managing esper resonance."""
    # Templates for the various resonance quantities. These match validation rules in the spreadsheet.
    RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE = 'Low Priority: {0}/10'
    RESONANCE_MEDIUM_PRIORITY_VALUE_TEMPLATE = 'Medium Priority: {0}/10'
    RESONANCE_HIGH_PRIORITY_VALUE_TEMPLATE = 'High Priority: {0}/10'
    RESONANCE_MAX_VALUE = '10/10'

    def __init__(self,
                 esper_resonance_spreadsheet_id: str,
                 sandbox_esper_resonance_spreadsheet_id: str,
                 access_control_spreadsheet_id: str,
                 spreadsheet_app):
        self.esper_resonance_spreadsheet_id = esper_resonance_spreadsheet_id
        self.sandbox_esper_resonance_spreadsheet_id = sandbox_esper_resonance_spreadsheet_id
        self.access_control_spreadsheet_id = access_control_spreadsheet_id
        self.spreadsheet_app = spreadsheet_app

    def findEsperColumn(self, document_id: str, user_name: str, search_text: str):
        """Performs a fuzzy lookup for an esper, returning the column (in A1 notation) and the text from within the one matched cell."""
        return WorksheetUtils.fuzzyFindColumn(self.spreadsheet_app, document_id, user_name, search_text, "2")

    def findUnitRow(self, document_id: str, user_name: str, search_text: str):
        """Performs a fuzzy lookup for a unit, returning the row number and the text from within the one matched cell."""
        return WorksheetUtils.fuzzyFindRow(self.spreadsheet_app, document_id, user_name, search_text, "B")

    def addEsperColumn(self, user_id: str, esper_name: str, esper_url: str, left_or_right_of: str, columnA1: str, sandbox: bool):
        """Add a new column for an esper.

        The left_or_right_of parameter needs to be either the string 'left-of' or 'right-of'. The column should be in A1 notation.
        If sandbox is True, uses a sandbox sheet so that the admin can ensure the results are good before committing to everyone.
        """
        if not AdminUtils.isAdmin(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id):
            raise ExposableException('You do not have permission to add an esper.')

        target_spreadsheet_id = None
        if sandbox:
            target_spreadsheet_id = self.sandbox_esper_resonance_spreadsheet_id
        else:
            target_spreadsheet_id = self.esper_resonance_spreadsheet_id
        spreadsheet = self.spreadsheet_app.get(spreadsheetId=target_spreadsheet_id).execute()
        allRequests = WorksheetUtils.generateRequestsToAddColumnToAllSheets(
            spreadsheet, columnA1, left_or_right_of,
            True, # Set a header row...
            1, # ...On the second row (row index is zero-based)
            esper_name, # With text content being the esper name
            esper_url) # As a hyperlink to the esper URL
        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=target_spreadsheet_id, body=requestBody).execute()
        return


    def addUnitRow(self, user_id: str, unit_name: str, unit_url: str, above_or_below: str, row_1_based: str, sandbox: str):
        """Add a new row for a unit.

        The above_or_below parameter needs to be either the string 'above' or 'below'. The row should be in 1-based notation,
        i.e. the first row is row 1, not row 0.
        If sandbox is True, uses a sandbox sheet so that the admin can ensure the results are good before committing to everyone.
        """
        if not AdminUtils.isAdmin(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id):
            raise ExposableException('You do not have permission to add a unit.')

        target_spreadsheet_id = None
        if sandbox:
            target_spreadsheet_id = self.sandbox_esper_resonance_spreadsheet_id
        else:
            target_spreadsheet_id = self.esper_resonance_spreadsheet_id
        spreadsheet = self.spreadsheet_app.get(spreadsheetId=target_spreadsheet_id).execute()
        int(row_1_based)

        allRequests = WorksheetUtils.generateRequestsToAddRowToAllSheets(
            spreadsheet, int(row_1_based), above_or_below,
            True, # Set a header column...
            'B', # ... On the second column (A1 notation)
            unit_name, # With text content being the unit name
            unit_url) # As a hyperlink to the unit URL
        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=target_spreadsheet_id, body=requestBody).execute()
        return


    def readResonance(self, user_name: str, user_id: str, unit_name: str, esper_name: str):
        """Read and return the esper resonance, pretty unit name, and pretty esper name for the given (unit, esper) tuple, for the given user.

        Set either the user name or the user ID, but not both. If the ID is set, the tab name for the resonance lookup is done the
        same way as setResonance - an indirection through the access control spreadsheet is used to map the ID of the user to the
        correct tab. This is best for self-lookups, so that even if a user changes their own nickname, they are still reading their own data
        and not the data of, e.g., another user who has their old nickname.
        """
        if (user_name is not None) and (user_id is not None):
            print('internal error: both user_name and user_id specified. Specify one or the other, not both.')
            raise ExposableException('Internal error')
        if user_id is not None:
            user_name = AdminUtils.findAssociatedTab(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)

        esper_column_A1, pretty_esper_name = self.findEsperColumn(self.esper_resonance_spreadsheet_id, user_name, esper_name)
        unit_row, pretty_unit_name = self.findUnitRow(self.esper_resonance_spreadsheet_id, user_name, unit_name)

        # We have the location. Get the value!
        range_name = WorksheetUtils.safeWorksheetName(
            user_name) + '!' + esper_column_A1 + str(unit_row) + ':' + esper_column_A1 + str(unit_row)
        result = self.spreadsheet_app.values().get(spreadsheetId=self.esper_resonance_spreadsheet_id, range=range_name).execute()
        final_rows = result.get('values', [])

        if not final_rows:
            raise ExposableException('{0} is not tracking any resonance for esper {1} on unit {2}'.format(
                user_name, pretty_esper_name, pretty_unit_name))

        return final_rows[0][0], pretty_unit_name, pretty_esper_name


    def readResonanceList(self, user_name: str, user_id: str, query_string: str):
        """Read and return the pretty name of the query subject (either a unit or an esper), and resonance list for the given user.

        Set either the user name or the user ID, but not both. If the ID is set, the tab name for the resonance lookup is done the
        same way as setResonance - an indirection through the access control spreadsheet is used to map the ID of the user to the
        correct tab. This is best for self-lookups, so that even if a user changes their own nickname, they are still reading their own data
        and not the data of, e.g., another user who has their old nickname.

        The returned list of resonances is either (unit/resonance) or (esper/resonance) tuples.
        """

        if (user_name is not None) and (user_id is not None):
            print('internal error: both user_name and user_id specified. Specify one or the other, not both.')
            raise ExposableException('Internal error')
        if user_id is not None:
            user_name = AdminUtils.findAssociatedTab(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)

        esper_column_A1 = None
        pretty_esper_name = None
        unit_row_index = None
        pretty_unit_name = None
        mode = None
        target_name = None

        # First try to look up a unit whose name matches.
        unit_lookup_exception_message = None
        try:
            unit_row_index, pretty_unit_name = self.findUnitRow(self.esper_resonance_spreadsheet_id, user_name, query_string)
            mode = 'for unit'
            target_name = pretty_unit_name
        except ExposableException as ex:
            unit_lookup_exception_message = ex.message

        # Try an esper lookup instead
        esper_lookup_exception_message = None
        if mode is None:
            try:
                esper_column_A1, pretty_esper_name = self.findEsperColumn(self.esper_resonance_spreadsheet_id, user_name, query_string)
                mode = 'for esper'
                target_name = pretty_esper_name
            except ExposableException as ex:
                esper_lookup_exception_message = ex.message

        # If neither esper or unit is found, fail now.
        if mode is None:
            raise ExposableException(
                'Unable to find a singular match for: ```{0}```\nUnit lookup results: {1}\nEsper lookup results: {2}'.format(
                    query_string, unit_lookup_exception_message, esper_lookup_exception_message))

        # Grab all the data in one call, so we can read everything at once and have atomicity guarantees.
        result = self.spreadsheet_app.values().get(spreadsheetId=self.esper_resonance_spreadsheet_id,
                                                   range=WorksheetUtils.safeWorksheetName(user_name)).execute()
        result_rows = result.get('values', [])
        resonances = []
        if mode == 'for esper':
            esper_index = WorksheetUtils.fromA1(esper_column_A1) - 1  # 0-indexed in result
            rowCount = 0
            for row in result_rows:
                rowCount += 1
                if rowCount < 3:
                    # skip headers
                    continue
                # rows collapse to the left, so only the last non-empty column exists in the data
                if len(row) > esper_index:
                    # annnnd as a result, there might be a value to the right, while this column could be empty.
                    if row[esper_index]:
                        resonances.append(row[1] + ': ' + row[esper_index])
        else:  # mode == 'for unit'
            colCount = 0
            unit_row = result_rows[unit_row_index - 1]  # 0-indexed in result
            for column in unit_row:
                colCount += 1
                if colCount < 3:
                    # skip headers
                    continue
                if column:
                    # Grab the esper name from the top of this column, and then append the column value.
                    resonances.append(result_rows[1][colCount - 1] + ': ' + column)

        # Format the list nicely
        resultString = ''
        for resonance in resonances:
            resultString += resonance + '\n'
        resultString = resultString.strip()
        return (target_name, resultString)


    def setResonance(self, user_id: str, unit_name: str, esper_name: str, resonance_numeric_string: str, priority: str, comment: str):
        """Set the esper resonance.

        Returns the old value, new value, pretty unit name, and pretty esper name for the given (unit, esper) tuple, for the given user.
        """
        resonance_int = None
        try:
            resonance_int = int(resonance_numeric_string)
        except:
            # pylint: disable=raise-missing-from
            raise ExposableException(
                'Invalid resonance level: "{0}"'.format(resonance_numeric_string)) # deliberately low on details as this is replying publicly.
        if (resonance_int < 0) or (resonance_int > 10):
            raise ExposableException(
                'Resonance must be a value in the range 0 - 10')

        user_name = AdminUtils.findAssociatedTab(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)

        esper_column_A1, pretty_esper_name = self.findEsperColumn(self.esper_resonance_spreadsheet_id, user_name, esper_name)
        unit_row, pretty_unit_name = self.findUnitRow(self.esper_resonance_spreadsheet_id, user_name, unit_name)

        spreadsheet = self.spreadsheet_app.get(spreadsheetId=self.esper_resonance_spreadsheet_id).execute()
        sheetId = None
        for sheet in spreadsheet['sheets']:
            sheetTitle = sheet['properties']['title']
            if sheetTitle == user_name:
                sheetId = sheet['properties']['sheetId']
                break
        if sheetId is None:
            raise ExposableException(
                'Internal error: sheet not found for {0}.'.format(user_name))

        # We have the location. Get the old value first.
        range_name = WorksheetUtils.safeWorksheetName(
            user_name) + '!' + esper_column_A1 + str(unit_row) + ':' + esper_column_A1 + str(unit_row)
        result = self.spreadsheet_app.values().get(spreadsheetId=self.esper_resonance_spreadsheet_id, range=range_name).execute()
        final_rows = result.get('values', [])
        old_value_string = '(not set)'
        if final_rows:
            old_value_string = final_rows[0][0]

        # Now that we have the old value, try to update the new value.
        # If priority is blank, leave the level (high/medium/low) alone.
        if priority is not None:
            priority = priority.lower()
        priorityString = None
        if resonance_int == 10:
            priorityString = '10/10'
        elif (priority == 'l') or (priority == 'low') or (priority is None and 'low' in old_value_string.lower()):
            priorityString = EsperResonanceManager.RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE.format(
                resonance_int)
        elif (priority == 'm') or (priority == 'medium') or (priority is None and 'medium' in old_value_string.lower()):
            priorityString = EsperResonanceManager.RESONANCE_MEDIUM_PRIORITY_VALUE_TEMPLATE.format(
                resonance_int)
        elif (priority == 'h') or (priority == 'high') or (priority is None and 'high' in old_value_string.lower()):
            priorityString = EsperResonanceManager.RESONANCE_HIGH_PRIORITY_VALUE_TEMPLATE.format(
                resonance_int)
        elif priority is None:
            # Priority not specified, and old value doesn't have high/medium/low -> old value was blank, or old value was 10.
            # Default to low priority.
            priorityString = EsperResonanceManager.RESONANCE_LOW_PRIORITY_VALUE_TEMPLATE.format(
                resonance_int)
        else:
            raise ExposableException(
                'Unknown priority value. Priority should be blank or one of "L", "low", "M", "medium", "H", "high"')

        # Now write the new value
        updateValueRequest = {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'userEnteredValue': {
                            'stringValue': priorityString
                        }
                    }]
                }],
                'fields': 'userEnteredValue',
                'range': {
                    'sheetId': sheetId,
                    'startRowIndex': unit_row-1,  # inclusive
                    'endRowIndex': unit_row,  # exclusive
                    'startColumnIndex': WorksheetUtils.fromA1(esper_column_A1)-1,  # inclusive
                    'endColumnIndex': WorksheetUtils.fromA1(esper_column_A1)  # exclusive
                }
            }
        }
        allRequests = []
        allRequests.append(updateValueRequest)

        if comment:
            commentText = comment
            if comment == '<blank>':  # Allow clearing the comment
                commentText = ''
            updateCommentRequest = {
                'updateCells': {
                    'rows': [{
                        'values': [{
                            'note': commentText
                        }]
                    }],
                    'fields': 'note',
                    'range': {
                        'sheetId': sheetId,
                        'startRowIndex': unit_row-1,  # inclusive
                        'endRowIndex': unit_row,  # exclusive
                        'startColumnIndex': WorksheetUtils.fromA1(esper_column_A1)-1,  # inclusive
                        'endColumnIndex': WorksheetUtils.fromA1(esper_column_A1)  # exclusive
                    }
                }
            }
            allRequests.append(updateCommentRequest)

        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=self.esper_resonance_spreadsheet_id, body=requestBody).execute()
        return old_value_string, priorityString, pretty_unit_name, pretty_esper_name
