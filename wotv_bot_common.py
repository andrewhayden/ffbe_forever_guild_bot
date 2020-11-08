"""Common exceptions and types"""
class ExposableException(Exception):
    """An exception safe to expose to end-users, that does not contain exploitable information in its message.
    Attributes:
        message -- explanation of the error
    """
    def __init__(self, message):
        super(ExposableException, self).__init__(message)
        self.message = message
