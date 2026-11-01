from abc import ABC, abstractmethod
from typing import Optional, Tuple


class Codec(ABC):
    """
    Wire-format of relst requests and responses.
    Codecs speak the plain value model (see values.py), the method name travels on the transport
    (url for http, frame for raw sockets) and may optionally be repeated in the payload.
    """

    name: str
    content_type: str

    @abstractmethod
    def encode_request(self, method: str, kwargs: dict, embed_method: bool = True) -> bytes:
        """
        :param embed_method: repeat the method name inside the payload (pointless when the transport carries it)
        """

    @abstractmethod
    def decode_request(self, data: bytes) -> Tuple[Optional[str], dict]:
        """
        :return: (method-name or None when payload doesn't carry it, keyword-arguments)
        :except: RelstProtocolError for malformed payloads
        """

    @abstractmethod
    def encode_response(self, value) -> bytes:
        pass

    @abstractmethod
    def encode_error(self, code: int, message: str) -> bytes:
        pass

    @abstractmethod
    def decode_response(self, data: bytes, status: int = 200):
        """
        :return: the returned value
        :except: RelstRemoteError if payload is an error, RelstProtocolError for malformed payloads
        """

    @property
    def is_binary(self) -> bool:
        return True
