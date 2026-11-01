class RelstProtocolError(ValueError):
    """Raised when a payload can't be encoded or decoded"""


class RelstRemoteError(Exception):
    """Raised on the client side when the server answered with an error"""

    def __init__(self, code: int, message: str):
        super().__init__(f'[{code}] {message}')
        self.code = code
        self.message = message
