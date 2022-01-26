"""Managers leaderboards."""
from sqlalchemy import column
from wotv_bot_common import ExposableException
from admin_utils import AdminUtils
from worksheet_utils import WorksheetUtils, AmbiguousSearchException, NoResultsException

class LeaderboardManager:
    """Main class for managing leaderboard content."""
    SUMMARY_TAB_NAME = 'Summary'
    DATA_TAB_NAME = 'Data'
    RANKED_PREFIX = 'Ranked: '
    USER_NAME_COLUMN_A1 = 'A'
    # TODO: Make these non-static once the manager is persisted across requests.
    ranked_column_cache = {}
    category_name_cache = {}
    user_row_cache = {}
    data_sheet_id = None # the sheet ID (not SPREADsheet ID) of the sheet (tab) within the leaderboard spreadsheet

    def __init__(self,
                 leaderboard_spreadsheet_id: str,
                 access_control_spreadsheet_id: str,
                 spreadsheet_app):
        self.leaderboard_spreadsheet_id = leaderboard_spreadsheet_id
        self.access_control_spreadsheet_id = access_control_spreadsheet_id
        self.spreadsheet_app = spreadsheet_app

    def findRankedColumn(self, ranked_column_name: str):
        """Performs a fuzzy lookup for a ranked column, returning the column (in A1 notation) and the category name (extracted from the column text)."""
        if ranked_column_name in LeaderboardManager.ranked_column_cache:
            columnA1 = LeaderboardManager.ranked_column_cache[ranked_column_name]
            return columnA1, LeaderboardManager.category_name_cache[columnA1]
        try:
            columnA1, column_name = WorksheetUtils.fuzzyFindColumn(self.spreadsheet_app, self.leaderboard_spreadsheet_id, LeaderboardManager.DATA_TAB_NAME, LeaderboardManager.RANKED_PREFIX + ranked_column_name, '1')
            LeaderboardManager.ranked_column_cache[ranked_column_name] = columnA1
            LeaderboardManager.category_name_cache[columnA1] = self.extractCategoryNameFromColumnText(column_name)
            print('cached ranked column name: ' + ranked_column_name + ' is at column ' + columnA1)
            return columnA1, LeaderboardManager.category_name_cache[columnA1]
        except AmbiguousSearchException:
            raise ExposableException('Be more specific, more than one category matched: ' + ranked_column_name)

    def findUserRow(self, user_id: str):
        """Performs a strict lookup for a user name row, returning the row index (1-based integer)."""
        if user_id in LeaderboardManager.user_row_cache:
            return LeaderboardManager.user_row_cache[user_id]
        try:
            user_name = AdminUtils.findAssociatedUserName(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)
            row_number, _ = WorksheetUtils.fuzzyFindRow(self.spreadsheet_app, self.leaderboard_spreadsheet_id, LeaderboardManager.DATA_TAB_NAME, '"' + user_name + '"', LeaderboardManager.USER_NAME_COLUMN_A1)
            LeaderboardManager.user_row_cache[user_id] = row_number
            print('cached user row: user ID' + str(user_id) + ' (' + user_name + ') is at row ' + str(row_number))
            return row_number
        except AmbiguousSearchException:
            raise ExposableException('more than one user matched')

    def findOrAddUserRow(self, user_id: str):
        """Find a user name row, adding it if it does not exist, and returning the row index (1-based integer)."""
        try:
            return self.findUserRow(user_id)
        except NoResultsException:
            print('user does not yet exist in leaderboard, adding...')
            pass
        # Add the row since it does not exist
        spreadsheet = self.spreadsheet_app.get(spreadsheetId=self.leaderboard_spreadsheet_id).execute()

        user_name = AdminUtils.findAssociatedUserName(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)
        allRequests = [WorksheetUtils.generateRequestToAppendRow(self.getDataSheetId(), [user_name])]
        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=self.leaderboard_spreadsheet_id, body=requestBody).execute()
        print('added user to leaderboard')
        return self.findUserRow(user_id)

    def readCurrentRankedValue(self, user_id: str, ranked_column_name: str):
        """Find the current value of the ranked column for the specified user, or none if there is not yet a value for that category and user combination, and the name of the category extracted from the column match"""
        columnA1, category_name = self.findRankedColumn(ranked_column_name)
        row_index = self.findUserRow(user_id)
        # We have the location. Get the value!
        range_name = WorksheetUtils.safeWorksheetName(LeaderboardManager.DATA_TAB_NAME) + '!' + columnA1  + str(row_index) + ':' + columnA1 + str(row_index)
        result = self.spreadsheet_app.values().get(spreadsheetId=self.leaderboard_spreadsheet_id, range=range_name).execute()
        final_rows = result.get('values', [])
        if not final_rows:
            return None, category_name
        return final_rows[0][0], category_name

    def getDataSheetId(self):
        if LeaderboardManager.data_sheet_id is not None:
            return LeaderboardManager.data_sheet_id
        spreadsheet = self.spreadsheet_app.get(spreadsheetId=self.leaderboard_spreadsheet_id).execute()
        for sheet in spreadsheet['sheets']:
            sheetTitle = sheet['properties']['title']
            if sheetTitle == LeaderboardManager.DATA_TAB_NAME:
                LeaderboardManager.data_sheet_id = sheet['properties']['sheetId']
                print('cached leaderboard data sheet id = ' + str(LeaderboardManager.data_sheet_id))
                return LeaderboardManager.data_sheet_id
        if LeaderboardManager.data_sheet_id is None:
            raise ExposableException('Internal error: sheet not found for leaderboard data')

    def extractCategoryNameFromColumnText(self, column_text: str):
        """Given a column header for a ranked category, extract the category name."""
        if column_text.startswith(LeaderboardManager.RANKED_PREFIX):
            return column_text[len(LeaderboardManager.RANKED_PREFIX):]
        raise ExposableException('Bad category name string')

    def setCurrentRankedValue(self, user_id: str, ranked_column_name: str, value: str, proof_url: str):
        """Set the current value of the ranked column for the specified user. Returns the previous value, if any, and the name of the category that was matched."""
        if value is None:
            raise ExposableException('Must specify a value.')
        if not value.isnumeric():
            raise ExposableException('The value of the ranked value must be a number and consist only of digits, without any characters such as commas or decimals')
        columnA1, category_name = self.findRankedColumn(ranked_column_name)
        proof_column_A1 = WorksheetUtils.toA1(WorksheetUtils.fromA1(columnA1) + 1)
        row_index = self.findOrAddUserRow(user_id)
        current_value, _ = self.readCurrentRankedValue(user_id, ranked_column_name)
        allRequests = [WorksheetUtils.generateRequestToSetCellIntValue(
            sheetId=self.getDataSheetId(),
            row_1_based=row_index,
            column_A1=columnA1,
            int_value=int(value))]
        # Add proof URL column
        if proof_url is None:
            proof_url = '' # to clear the existing value
        allRequests.append(WorksheetUtils.generateRequestToSetCellText(
            sheetId=self.getDataSheetId(),
            row_1_based=row_index,
            column_A1=proof_column_A1,
            text='click here',
            url=proof_url))
        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=self.leaderboard_spreadsheet_id, body=requestBody).execute()
        return current_value, category_name
