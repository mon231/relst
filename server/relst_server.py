from flask import Flask
from waitress import serve
from typing import Callable
from name_generator import NameGenerator
from types import FunctionType, MethodType
from inspect import iscoroutinefunction, signature


class RelstServer:
    def __init__(self, server_port: int, request_hanlder):
        self.__app = Flask(__name__)
        self.__name_generator = NameGenerator()

        self.__server_port = server_port
        self.__request_handler = request_hanlder

        self.__register_attributes()
        self.__register_relst_methods()

    def serve(self):
        serve(self.__app, port=self.__server_port)

    def __register_relst_methods(self):
        # TODO: support get-help, methods-list and types
        pass

    def __register_attributes(self):
        for attr_name in dir(self.__request_handler):
            if attr_name[0] == '_':
                continue

            current_attribute = getattr(self.__request_handler, attr_name)

            if isinstance(current_attribute, (FunctionType, MethodType)):
                self.__register_callable(current_attribute, attr_name)
            # TODO: if is_dataclass / premitive (support get + set)

    def __register_callable(self, callable: Callable, name: str):
        if iscoroutinefunction(callable):
            @self.__app.route("/" + name)
            @self.__name_generator.rename_function
            async def async_callable_wrapper(**kwargs):
                return await callable(**kwargs)
        else:
            @self.__app.route("/" + name)
            @self.__name_generator.rename_function
            def callable_wrapper(**kwargs):
                return callable(**kwargs)

        callable_signature = signature(callable)
        # TODO: add to dict
        pass
