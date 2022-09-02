from flask import Flask
from waitress import serve
from typing import Callable
from .relst_server import RelstServer
from .name_generator import NameGenerator
from types import FunctionType, MethodType
from inspect import iscoroutinefunction, signature


class RelstFlaskServer(RelstServer):
    def __init__(self, server_port: int, request_hanlder):
        self.__flask_app = Flask(__name__)
        self.__name_generator = NameGenerator()

        super().__init__(server_port, request_hanlder)

    def serve(self):
        serve(self.__flask_app, port=self._server_port)

    def _register_callable(self, callable: Callable, name: str):
        if iscoroutinefunction(callable):
            @self.__flask_app.route("/" + name)
            @self.__name_generator.rename_function
            async def async_callable_wrapper(**kwargs):
                return await callable(**kwargs)
        else:
            @self.__flask_app.route("/" + name)
            @self.__name_generator.rename_function
            def callable_wrapper(**kwargs):
                return callable(**kwargs)

        callable_signature = signature(callable)
        # TODO: add to dict
        pass
