import requests
from inspect import Signature
from relst_client import RelstClient, PRIVATE_OR_PROTECTED_PREFIX


class RelstFlaskClient(RelstClient):
    def __init__(self, server_address: str, server_port: int, is_https: bool = False):
        super().__init__()

        requests_protocol = "https" if is_https else "http"
        self.__request_prefix = f"{requests_protocol}://{server_address}:{server_port}"

    def _handle_request(self, function: str, **kwargs) -> dict:
        request_url = f"{self.__request_prefix}/{function}"
        response = requests.post(request_url, json=kwargs)

        response.raise_for_status()
        return response.json()

    def _remove_methods(self):
        pass
