import requests


class RelstClient:
    def __init__(self, server_address: str, server_port: int, is_https: bool = False):
        requests_protocol = "https" if is_https else "http"
        self.__request_prefix = f"{requests_protocol}://{server_address}:{server_port}"

    def handle_request(self, function: str, **kwargs) -> dict:
        request_url = f"{self.__request_prefix}/{function}"
        return requests.post(request_url, json=kwargs).json()
