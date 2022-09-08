from abc import ABC, abstractmethod

class RelstClient(ABC):
    @abstractmethod
    def handle_request(self, function_name: str, **function_args) -> dict:
        pass
