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

    def _remove_methods(self):
        for attribute_name in dir(self):
            if attribute_name[0] != PRIVATE_OR_PROTECTED_PREFIX:
                delattr(self, attribute_name)

    def _add_method(self, method_name: str, method_signature: Signature):
        def method_caller(**kwargs):
            return self._handle_request(method_name, **kwargs)

        method_caller.__name__ = method_name
        method_caller.__annotations__ = method_signature.__annotations__

        setattr(self, method_name, method_caller)
