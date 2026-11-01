from typing import Dict, Set, Tuple
from abc import ABC, abstractmethod
from ..protocol import Codec, get_codec, DEFAULT_PROTOCOL


GET_CLASS_NAME_REQUEST = '__get_class_name'
GET_CLASS_HELP_REQUEST = '__get_class_help'
GET_METHODS_LIST_REQUEST = '__get_methods_list'
GET_METHOD_HELP_REQUEST = '__get_method_help'
UPDATE_SERVER_REQUEST = '__update_server'

PRIVATE_OR_PROTECTED_PREFIX = '_'


class RelstClient(ABC):
    """
    Client of a relst server. After UPDATE_METHODS (or entering a `with` block)
    every public server-method is available as a python method of the client.
    NOTE: Uppercase names are reserved for the client, server methods can't override them
    """

    def __init__(self, protocol: str = DEFAULT_PROTOCOL):
        self._codec: Codec = get_codec(protocol)
        self._dynamic_methods: Set[str] = set()

    def UPDATE_METHODS(self):
        self._remove_methods()
        methods_list = self._handle_request(GET_METHODS_LIST_REQUEST)

        for method_name, method_description in methods_list.items():
            self._add_method(method_name, method_description)

    def CLASS_NAME(self) -> str:
        return self._handle_request(GET_CLASS_NAME_REQUEST)

    def CLASS_HELP(self) -> str:
        return self._handle_request(GET_CLASS_HELP_REQUEST)

    def METHOD_HELP(self, method_name: str) -> str:
        return self._handle_request(GET_METHOD_HELP_REQUEST, method_name=method_name)

    def UPDATE_SERVER(self):
        self._handle_request(UPDATE_SERVER_REQUEST)

    def _handle_request(self, method_name: str, /, **method_args):
        """
        :except: RelstRemoteError when the server reports an error, RelstProtocolError for bad payloads
        """

        request = self._codec.encode_request(method_name, method_args)
        status, response = self._send(method_name, request)
        return self._codec.decode_response(response, status)

    @abstractmethod
    def _send(self, method_name: str, request: bytes) -> Tuple[int, bytes]:
        """transport-level exchange, returns (http-like status, response bytes)"""

    def _remove_methods(self):
        for method_name in self._dynamic_methods:
            self.__dict__.pop(method_name, None)

        self._dynamic_methods.clear()

    def _add_method(self, method_name: str, description: Dict):
        # NOTE: server must not shadow client's own attributes
        if method_name.startswith(PRIVATE_OR_PROTECTED_PREFIX) or hasattr(type(self), method_name):
            return

        parameters = [param['name'] for param in description.get('params', [])]

        def method_caller(*args, **kwargs):
            if len(args) > len(parameters):
                raise TypeError(f'{method_name}() takes at most {len(parameters)} positional arguments')

            for parameter_name, argument in zip(parameters, args):
                if parameter_name in kwargs:
                    raise TypeError(f'{method_name}() got multiple values for argument {parameter_name!r}')

                kwargs[parameter_name] = argument

            return self._handle_request(method_name, **kwargs)

        method_caller.__name__ = method_name
        method_caller.__doc__ = description.get('doc')

        self._dynamic_methods.add(method_name)
        setattr(self, method_name, method_caller)

    def close(self):
        pass

    def __enter__(self):
        self.UPDATE_METHODS()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
