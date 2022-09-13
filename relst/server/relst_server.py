from typing import Callable, Dict
from abc import ABC, abstractmethod
from .relst_methods import RelstMethods
from inspect import Signature, signature


class RelstServer(ABC):
    def __init__(self, server_port: int, request_hanlder):
        self._server_port = server_port
        self._request_handler = request_hanlder
        self._callables: Dict[str, Signature] = dict()
        self.__relst_methods = RelstMethods(request_hanlder)

        self._register_attributes()
        self.__register_relst_methods()

    @abstractmethod
    def serve(self):
        pass

    def __register_relst_methods(self):
        callables_getter = RelstMethods.get_object_methods

        for method in callables_getter(self.__relst_methods):
            self._register_callable(method, f"${method.__name__}")

    def _register_attributes(self):
        for callable in self.__relst_methods.get_methods_list():
            self._register_callable(callable, callable.__name__)
            self._callables[callable.__name__] = signature()

            # TODO: if is_dataclass / premitive (support get + set)

    @abstractmethod
    def _register_callable(self, callable: Callable, name: str):
        pass
