from typing import Callable
from abc import abstractmethod, ABC
from types import FunctionType, MethodType


class RelstServer(ABC):
    def __init__(self, server_port: int, request_hanlder):
        self._server_port = server_port
        self._request_handler = request_hanlder

        self._register_attributes()
        self.__register_relst_methods()

    @abstractmethod
    def serve(self):
        pass

    def __register_relst_methods(self):
        # TODO: support get-help, methods-list and types
        pass

    def _register_attributes(self):
        for attr_name in dir(self._request_handler):
            if attr_name[0] == '_':
                continue

            current_attribute = getattr(self._request_handler, attr_name)

            if isinstance(current_attribute, (FunctionType, MethodType)):
                self._register_callable(current_attribute, attr_name)
            # TODO: if is_dataclass / premitive (support get + set)

    @abstractmethod
    def _register_callable(self, callable: Callable, name: str):
        pass
