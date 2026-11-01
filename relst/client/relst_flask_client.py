import requests
from typing import Tuple
from .relst_client import RelstClient
from ..protocol import DEFAULT_PROTOCOL


class RelstFlaskClient(RelstClient):
    """Client of RelstTextualServer, speaks json / xml / binary over http"""

    _embed_method = False

    def __init__(self, server_address: str, server_port: int, is_https: bool = False,
                 protocol: str = DEFAULT_PROTOCOL, timeout: float = 30):
        super().__init__(protocol)

        requests_protocol = "https" if is_https else "http"
        self.__request_prefix = f"{requests_protocol}://{server_address}:{server_port}"
        self.__timeout = timeout
        self.__session = requests.Session()

    def _send(self, method_name: str, request: bytes) -> Tuple[int, bytes]:
        response = self.__session.post(
            f"{self.__request_prefix}/{method_name}",
            data=request,
            headers={'Content-Type': self._codec.content_type, 'Accept': self._codec.content_type},
            timeout=self.__timeout,
        )

        return response.status_code, response.content

    def close(self):
        self.__session.close()
