from typing import Callable, Dict
from abc import ABC, abstractmethod
from inspect import Signature, getdoc, signature
from typing import Callable, List, Optional, Tuple, Dict, Any


PRIVATE_OR_PROTECTED_PREFIX = '_'


class RelstServer(ABC):
    def __init__(self, server_port: int, request_hanlder):
        self._server_port = server_port
        self._callables: Dict[str, Signature]
        self._request_handler = request_hanlder

        self._register_attributes()
        self.__register_relst_methods()

    @abstractmethod
    def serve(self):
        pass

    def _register_attributes(self):
        self._callables = dict()

        for callable in RelstServer.__get_object_methods(self._request_handler):
            self._register_callable(callable, callable.__name__)
            self._callables[callable.__name__] = signature(callable)

    @abstractmethod
    def _register_callable(self, callable: Callable, name: str):
        pass

    @abstractmethod
    def _unregister_all_callables():
        pass

    def __register_relst_methods(self):
        relst_methods = [
            self.__get_class_name,
            self.__get_class_help,
            self.__get_methods_list,
            self.__get_method_help,
            self.__update_server
        ]

        for method in relst_methods:
            # NOTE: relst-methods are the only methods allowed to start with '_'
            self._register_callable(method, f"{method.__name__}")

    def __get_class_name(self) -> str:
        return type(self.__request_hanlder).__name__

    def __get_class_help(self):
        return getdoc(self.__request_hanlder)

    def __get_methods_list(self) -> Dict[str, Signature]:
        return self._callables

    def __get_method_help(self, method_name: str) -> str:
        """
        :except: may raise KeyError for invalid method-name
        """

        return getdoc(self._callables[method_name])

    def __update_server(self):
        self._unregister_all_callables()
        self._register_attributes()

    @staticmethod
    def __get_object_methods(obj, ignore_statics: bool = False) -> List[Callable]:
        """
        :except: may raise AttributeError for non-existing methods
                 notice race condition, method may be removed between dir(obj) to getattr
                 we might like to use pyrsistent.freeze
        """

        for attribute_name in dir(obj):
            if attribute_name.startswith(PRIVATE_OR_PROTECTED_PREFIX):
                continue

            attribute_value = getattr(obj, attribute_name)

            if not isinstance(attribute_value, Callable):
                continue

            if ignore_statics and isinstance(attribute_value, staticmethod):
                continue

            yield attribute_value
