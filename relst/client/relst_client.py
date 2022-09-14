from inspect import Signature
from abc import ABC, abstractmethod


PRIVATE_OR_PROTECTED_PREFIX = '_'


class RelstClient(ABC):
    @abstractmethod
    def _handle_request(self, method_name: str, **method_args) -> dict:
        pass

    @abstractmethod
    def _remove_methods(self):
        pass

    @abstractmethod
    def _add_method(self, method_name: str, method_signature: Signature):
        pass
