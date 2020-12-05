"""Common utilities used for searching, across multiple facets of the bot."""
class CommonSearchUtils:
    """Common utilities used for searching, across multiple facets of the bot."""
    @staticmethod
    def fuzzyMatches(candidate_text, search_text):
        """Performs a fuzzy match within the specified text.

        Breaks the specified search_text on whitespace, then does a case-insensitive substring match on each of the
        resulting words. If ALL the words are found somewhere in the candidate_text, then it is considered to be a
        match and the method returns True; otherwise, returns False.
        """
        words = search_text.split() # by default splits on all whitespace PRESERVING punctuation, which is important...
        for word in words:
            if not word.lower() in candidate_text.lower():
                return False
        return True
