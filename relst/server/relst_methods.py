from inspect import Signature, getdoc, signature
from typing import Callable, List, Optional, Tuple, Dict, Any


PRIVATE_OR_PROTECTED_PREFIX = '_'



class RelstMethods:
    def __init__(self, request_handler):
        self.__request_handler = request_handler

    def get_class_name(self) -> str:
        return type(self.__request_hanlder).__name__

    def get_class_help(self):
        return getdoc(self.__request_hanlder)

    def get_methods_list(self):
        return RelstMethods.get_object_methods(self.__request_handler)

    def get_method_help(self, method_name: str) -> Tuple[Optional[str], Signature]:
        """
        :brief: method used to get help for specific callabe
        :param method_name: name of method to fetch help for
        :except: may raise AttributeError or ValueError invalid method-name
        """

        if method_name.startswith(PRIVATE_OR_PROTECTED_PREFIX):
            raise ValueError("Invalid attempt to access private or protected method")

        method = getattr(self.__request_handler, method_name)

        if not isinstance(method, Callable):
            raise ValueError("Failed attempt to get help for non-callable")

        return getdoc(method), signature(method)

    @staticmethod
    def get_object_methods(obj, ignore_statics: bool = False) -> List[Callable]:
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
