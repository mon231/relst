from waitress import serve
from typing import Callable
from flask import Flask, request
from .relst_server import RelstServer
from inspect import iscoroutinefunction
from werkzeug.exceptions import HTTPException, NotFound, \
    ServiceUnavailable, InternalServerError


class RelstTextualServer(RelstServer):
    def __init__(self, server_port: int, request_hanlder):
        self.__flask_app = Flask(__name__)
        self.__should_handle_requests = False

        self.__register_exceptions_handler()
        self.__init_server()

        super().__init__(server_port, request_hanlder)

    def serve(self):
        serve(self.__flask_app, port=self._server_port)

    def _register_callable(self, callable: Callable, name: str):
        self.__should_handle_requests = True

    def _unregister_all_callables(self):
        self.__should_handle_requests = False

    def __register_exceptions_handler(self):
        @self.__flask_app.errorhandler(Exception)
        def on_server_error(err: Exception):
            if isinstance(err, HTTPException):
                return err

            if isinstance(err, NotFound):
                return err

            print(err)
            return InternalServerError('Server error handling request')

    def __init_server(self):
        @self.__flask_app.route('/<callable_name>', methods=['POST', 'GET'])
        async def handle_request(callable_name):
            if not self.__should_handle_requests:
                raise ServiceUnavailable("Server doesn't currently accept requests")

            callable = self._callables.get(callable_name)

            if not callable:
                print(f'Attempt to access non existing function {callable_name}')
                raise NotFound(f"Mehtod {callable_name} does not exist")

            if iscoroutinefunction(callable):
                return await callable(**request.json)

            return callable(**request.json)
