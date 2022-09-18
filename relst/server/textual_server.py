import json
from waitress import serve
from types import NoneType
from flask import Flask, request
from .relst_server import RelstServer
from dataclasses import is_dataclass, asdict
from typing import Callable, Dict, List, Tuple
from inspect import Signature, iscoroutinefunction
from werkzeug.exceptions import HTTPException, NotFound, InternalServerError


class RelstTextualServer(RelstServer):
    def __init__(self, server_port: int, request_hanlder):
        self.__flask_app = Flask(__name__)

        self.__init_server()
        self.__register_exceptions_handler()

        super().__init__(server_port, request_hanlder)

    def serve(self):
        serve(self.__flask_app, port=self._server_port)

    def _register_callable(self, callable: Callable, name: str):
        self._callables[name] = callable

    def _unregister_all_callables(self):
        self._callables = dict()

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
            callable = self._callables.get(callable_name)
            kwargs = request.json if request.is_json else dict()

            if not callable:
                print(f'Attempt to access non existing function {callable_name}')
                raise NotFound(f"Mehtod {callable_name} does not exist")

            if iscoroutinefunction(callable):
                method_result = await callable(**kwargs)
            else:
                method_result = callable(**kwargs)

            serializable_response = RelstTextualServer.__make_serializable(method_result)
            return json.dumps(serializable_response)

    @staticmethod
    def __make_serializable(obj) -> str:
        make_serialize = RelstTextualServer.__make_serializable

        if isinstance(obj, (str, NoneType, int, float, bool)):
            return obj
        elif is_dataclass(obj):
            return make_serialize(asdict(obj))
        elif isinstance(obj, (List, Tuple)):
            return [make_serialize(element) for element in obj]
        elif isinstance(obj, Dict):
            return {
                make_serialize(key): make_serialize(value)
                for key, value in obj.items()
            }
        elif isinstance(obj, Signature):
            return RelstTextualServer.__serialize_signature(obj)
        elif isinstance(obj, type):
            return RelstTextualServer.__serialize_annotation(obj)
        else:
            # NOTE: throws when obj isn't serializable
            return str(obj)

    @staticmethod
    def __serialize_signature(obj: Signature):
        params = []

        for param in obj.parameters.values():
            serialized_param = {
                'name': param.name,
                'type': param.annotation
            }

            if param.default is not Signature.empty:
                serialized_param['default'] = param.default

            params.append(param)

        return RelstTextualServer.__make_serializable(
            {
                'params': params,
                'return': obj.return_annotation
            }
        )

    @staticmethod
    def __serialize_annotation(obj: type) -> bool:
        # NOTE: currently won't support complicated types parsing
        return obj.__name__
