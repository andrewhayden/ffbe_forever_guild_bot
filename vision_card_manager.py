"""Manages a Vision Card spreadsheet."""
from wotv_bot_common import ExposableException
from admin_utils import AdminUtils
from worksheet_utils import WorksheetUtils
from vision_card_common import VisionCard

class VisionCardManager:
    """Manages a Vision Card spreadsheet."""

    def __init__(self,
                 vision_card_spreadsheet_id: str,
                 access_control_spreadsheet_id: str,
                 spreadsheet_app):
        self.vision_card_spreadsheet_id = vision_card_spreadsheet_id
        self.access_control_spreadsheet_id = access_control_spreadsheet_id
        self.spreadsheet_app = spreadsheet_app

    def findVisionCardRow(self, user_name: str, search_text: str):
        """Performs a fuzzy lookup for a unit, returning the row number and the text from within the one matched cell."""
        return WorksheetUtils.fuzzyFindRow(self.spreadsheet_app, self.vision_card_spreadsheet_id, user_name, search_text, "B")

    def addVisionCardRow(self, user_id: str, name: str, url: str, above_or_below: str, row_1_based: str):
        """Add a new row for a Vision Card.

        The above_or_below parameter needs to be either the string 'above' or 'below'. The row should be in 1-based notation,
        i.e. the first row is row 1, not row 0.
        """
        if not AdminUtils.isAdmin(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id):
            raise ExposableException('You do not have permission to add a vision card.')

        spreadsheet = self.spreadsheet_app.get(spreadsheetId=self.vision_card_spreadsheet_id).execute()

        allRequests = WorksheetUtils.generateRequestsToAddRowToAllSheets(
            spreadsheet, int(row_1_based), above_or_below,
            True, # Set a header column...
            'B', # ... On the second column (A1 notation)
            name, # With text content being the vision card name
            url) # As a hyperlink to the url
        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=self.vision_card_spreadsheet_id, body=requestBody).execute()
        return

    @staticmethod
    def intOrNone(rawValueString) -> int:
        """Parse a raw value string and return either the integer it represents, or None if it does not represent an integer."""
        try:
            return int(rawValueString, 10)
        except ValueError:
            return None

    @staticmethod
    def valueOrNone(rowdata: [], index: int):
        """Return either the nth element of the specified array, or None if the array does not have that many elements."""
        if len(rowdata) > index:
            return rowdata[index]
        return None

    @staticmethod
    def valueOrEmpty(value):
        """Either return a string representation of the supplied value or, if the supplied value is None, return the empty string."""
        if value is not None:
            return str(value)
        return ''

    @staticmethod
    def toMultiLineString(values: []):
        """If the supplied list is not None and is a non-empty list of items, returns a string representation of the elements of the list,
        joined by newlines. Otherwise, returns the empty string."""
        if values is None or len(values) == 0:
            return ''
        return '\n'.join(values)

    @staticmethod
    def fromMultiLineString(value: []):
        """If the supplied string is not None and is non-empty, returns a list representation of the lines in the string.
        Otherwise, returns the empty string."""
        if value is None:
            return ''
        return str(value).splitlines()

    def __readVisionCardFromRawRow(self, row):
        """Read a VisionCard object out of a raw row of strings from the spreadsheet. The first element of the row must be the vision card name."""
        # Columns:
        # Name,Awakening,Level,Cost,HP,DEF,TP,SPR,AP,DEX,ATK,AGI,MAG,Luck,Party Ability,Bestowed Abilities
        # (B) ..........................................................................(Q)
        name_from_sheet = VisionCardManager.valueOrNone(row, 0)
        # TODO: Read awakening and level once they are available
        # awakening = VisionCardManager.valueOrNone(row, 1)
        # level = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 2))
        cost = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 3))
        hp_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 4))
        def_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 5))
        tp_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 6))
        spr_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 7))
        ap_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 8))
        dex_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 9))
        atk_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 10))
        agi_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 11))
        mag_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 12))
        luck_value = VisionCardManager.intOrNone(VisionCardManager.valueOrNone(row, 13))
        party_ability = VisionCardManager.valueOrNone(row, 14)
        bestowed_abilities = VisionCardManager.fromMultiLineString(VisionCardManager.valueOrNone(row, 15))
        result = VisionCard(
            name_from_sheet, cost, hp_value, def_value, tp_value, spr_value, ap_value, dex_value,
            atk_value, agi_value, mag_value, luck_value, party_ability, bestowed_abilities)
        return result

    def readVisionCardByName(self, user_name: str, user_id: str, vision_card_name: str) -> VisionCard:
        """Read and return a VisionCard containing the stats for the specified vision card name, for the given user.

        Set either the user name or the user ID, but not both. If the ID is set, the tab name for the lookup is done as an indirection through
        the access control spreadsheet to map the ID of the user to the correct tab. This is best for self-lookups, so that even if a user
        changes their own nickname, they are still reading their own data and not the data of, e.g., another user who has their old nickname.
        """
        if (user_name is not None) and (user_id is not None):
            print('internal error: both user_name and user_id specified. Specify one or the other, not both.')
            raise ExposableException('Internal error')
        if user_id is not None:
            user_name = AdminUtils.findAssociatedTab(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)
        row_number, _ = self.findVisionCardRow(user_name, vision_card_name)
        # We have the location. Get the value!
        range_name = WorksheetUtils.safeWorksheetName(user_name) + '!B' + str(row_number) + ':Q' + str(row_number)
        result = self.spreadsheet_app.values().get(spreadsheetId=self.vision_card_spreadsheet_id, range=range_name).execute()
        rows = result.get('values', [])
        if not rows:
            raise ExposableException('{0} is not tracking any data for vision card {1}'.format(user_name, vision_card_name))
        return self.__readVisionCardFromRawRow(rows[0])

    def setVisionCard(self, user_id: str, vision_card: VisionCard) -> None:
        """Copy the vision card data from the specified object into the spreadsheet."""
        user_name = AdminUtils.findAssociatedTab(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)
        row_index_1_based, _ = self.findVisionCardRow(user_name, vision_card.Name)
        spreadsheet = self.spreadsheet_app.get(spreadsheetId=self.vision_card_spreadsheet_id).execute()
        sheet_id = None
        for sheet in spreadsheet['sheets']:
            sheetTitle = sheet['properties']['title']
            if sheetTitle == user_name:
                sheet_id = sheet['properties']['sheetId']
                break
        if sheet_id is None:
            raise ExposableException(
                'Internal error: sheet not found for {0}.'.format(user_name))

        # Columns:
        # Name,Awakening,Level,Cost,HP,DEF,TP,SPR,AP,DEX,ATK,AGI,MAG,Luck,Party Ability,Bestowed Abilities
        # (B) ..........................................................................(Q)
        new_values = []
        # TODO: Write awakening and level once they are available
        new_values.append('') # Awakening
        new_values.append('') # Level
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.Cost))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.HP))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.DEF))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.TP))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.SPR))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.AP))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.DEX))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.ATK))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.AGI))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.MAG))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.Luck))
        new_values.append(VisionCardManager.valueOrEmpty(vision_card.PartyAbility))
        new_values.append(VisionCardManager.toMultiLineString(vision_card.BestowedEffects))
        allRequests = [WorksheetUtils.generateRequestToSetRowText(sheet_id, row_index_1_based, 'C', new_values)]
        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=self.vision_card_spreadsheet_id, body=requestBody).execute()

    def searchVisionCardsByAbility(self, user_name: str, user_id: str, search_text: str) -> [VisionCard]:
        """Search for and return all VisionCards matching the specified search text, for the given user. Returns an empty list if there are no matches.

        Set either the user name or the user ID, but not both. If the ID is set, the tab name for the lookup is done as an indirection through
        the access control spreadsheet to map the ID of the user to the correct tab. This is best for self-lookups, so that even if a user
        changes their own nickname, they are still reading their own data and not the data of, e.g., another user who has their old nickname.
        """
        if (user_name is not None) and (user_id is not None):
            print('internal error: both user_name and user_id specified. Specify one or the other, not both.')
            raise ExposableException('Internal error')
        if user_id is not None:
            user_name = AdminUtils.findAssociatedTab(self.spreadsheet_app, self.access_control_spreadsheet_id, user_id)
        party_ability_row_tuples = WorksheetUtils.fuzzyFindAllRows(
            self.spreadsheet_app, self.vision_card_spreadsheet_id, user_name, search_text, 'P', 2)
        bestowed_ability_row_tuples = WorksheetUtils.fuzzyFindAllRows(
            self.spreadsheet_app, self.vision_card_spreadsheet_id, user_name, search_text, 'Q', 2)
        if len(party_ability_row_tuples) == 0 and len(bestowed_ability_row_tuples) == 0:
            return []

        # Accumulate all the matching rows
        all_matching_row_numbers = set()
        for (row_number, _) in party_ability_row_tuples:
            all_matching_row_numbers.add(row_number)
        for (row_number, _) in bestowed_ability_row_tuples:
            all_matching_row_numbers.add(row_number)
        all_matching_row_numbers = sorted(all_matching_row_numbers)

        range_name = WorksheetUtils.safeWorksheetName(user_name) + '!B2:Q' # Fetch everything from below the header row, starting with the name
        result = self.spreadsheet_app.values().get(spreadsheetId=self.vision_card_spreadsheet_id, range=range_name).execute()
        all_rows = result.get('values', [])
        all_matching_vision_cards = []
        for row_number in all_matching_row_numbers:
            all_matching_vision_cards.append(self.__readVisionCardFromRawRow(all_rows[row_number - 1])) # -1 for the header row
        return all_matching_vision_cards

    def addUser(self, user_name: str) -> None:
        """Adds the user with the specified name by creating a new tab that duplicates the first tab in the spreadsheet.

        Raises an exception on failure. Otherwise, you may assume that the new sheet was successfully created.
        """
        spreadsheet = self.spreadsheet_app.get(spreadsheetId=self.vision_card_spreadsheet_id).execute()
        home_sheet_id = spreadsheet['sheets'][0]['properties']['sheetId']
        allRequests = [WorksheetUtils.generateRequestToDuplicateSheetInAlphabeticOrder(
            spreadsheet,
            home_sheet_id,
            user_name,
            True)] # True to skip the 'Home' tab, the first tab in the spreadsheet, for sorting purposes
        requestBody = {
            'requests': [allRequests]
        }
        # Execute the whole thing as a batch, atomically, so that there is no possibility of partial update.
        self.spreadsheet_app.batchUpdate(spreadsheetId=self.vision_card_spreadsheet_id, body=requestBody).execute()
        return
