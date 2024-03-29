"""For working with the guild administration data"""

from worksheet_utils import WorksheetUtils
from wotv_bot_common import ExposableException

class AdminUtils:
    """Static utility methods for checking access and indirecting from user ID to a symbolic name."""
    # The name of the tab that contains the user bindings that map Discord IDs to data tabs.
    USERS_TAB_NAME = 'Users'
    USER_NAME_BY_ID_CACHE = {}

    @staticmethod
    def isAdmin(spreadsheet_app, access_control_spreadsheet_id, user_id):
        """Return True if the specified user id has administrator permissions."""
        # Discord IDs are in column A, the associated tab name is in column B, and if 'Admin' is in column C, then it's an admin.
        range_name = WorksheetUtils.safeWorksheetName(AdminUtils.USERS_TAB_NAME) + '!A:C'
        rows = None
        try:
            values = spreadsheet_app.values().get(spreadsheetId=access_control_spreadsheet_id, range=range_name).execute()
            rows = values.get('values', [])
            if not rows:
                raise Exception('')
        except:
            # pylint: disable=raise-missing-from
            raise ExposableException('Spreadsheet misconfigured') # deliberately low on details as this is replying in Discord.

        for row in rows:
            if str(row[0]) == str(user_id):
                result = (len(row) > 2 and row[2] and row[2].lower() == 'admin')
                print('Admin check for user {0}: {1}'.format(user_id, result))
                return result
        return False

    @staticmethod
    def findAssociatedUserName(spreadsheetApp, access_control_spreadsheet_id, user_id):
        """Return the symbolic name of the user, to which the specified user ID (such as a Discord snowflake ID) is bound.

        If the ID can't be found, an exception is raised with a safe error message that can be shown publicly in Discord.
        """
        # Discord IDs are in column A, the associated tab name is in column B
        if user_id in AdminUtils.USER_NAME_BY_ID_CACHE:
            return AdminUtils.USER_NAME_BY_ID_CACHE[user_id]
        range_name = WorksheetUtils.safeWorksheetName(AdminUtils.USERS_TAB_NAME) + '!A:B'
        rows = None
        try:
            values = spreadsheetApp.values().get(spreadsheetId=access_control_spreadsheet_id, range=range_name).execute()
            rows = values.get('values', [])
            if not rows:
                raise Exception('')
        except:
            # pylint: disable=raise-missing-from
            raise ExposableException('Spreadsheet misconfigured') # deliberately low on details as this is replying in Discord.

        for row in rows:
            if str(row[0]) == str(user_id):
                AdminUtils.USER_NAME_BY_ID_CACHE[user_id] = row[1]
                return row[1]
        raise ExposableException(
            'User with ID {0} is not configured, or is not allowed to access this data. Ask your guild administrator for assistance.'.format(user_id))

    # TODO: Rename to findAssociatedNameForWorksheets
    @staticmethod
    def findAssociatedTab(spreadsheetApp, access_control_spreadsheet_id, user_id):
        """Deprecated. User findAssociatedUserName instead."""
        return AdminUtils.findAssociatedUserName(spreadsheetApp, access_control_spreadsheet_id, user_id)

    @staticmethod
    def addUser(spreadsheet_app, access_control_spreadsheet_id: str, user_name: str, user_id: str, is_admin: bool = False):
        """Add a user to the admin spreadsheet."""
        admin_string = ''
        if is_admin:
            admin_string = 'Admin'
        spreadsheet = spreadsheet_app.get(spreadsheetId=access_control_spreadsheet_id).execute()
        home_sheet_id = spreadsheet['sheets'][0]['properties']['sheetId']
        requestBody = {
            'requests': [WorksheetUtils.generateRequestToAppendRow(home_sheet_id, [user_id, user_name, admin_string])]
        }
        spreadsheet_app.batchUpdate(spreadsheetId=access_control_spreadsheet_id, body=requestBody).execute()
