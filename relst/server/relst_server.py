import asyncio
import logging
import threading
from time import perf_counter
from abc import ABC, abstractmethod
from typing import Callable, Dict, Iterator, Optional, Tuple
from inspect import getattr_static, getdoc, isawaitable, isroutine, signature
from ..protocol import Codec, RelstProtocolError, to_plain
from .tracing import TraceLog, render_body


PRIVATE_OR_PROTECTED_PREFIX = '_'
SERVER_ERROR_MESSAGE = 'Server error handling request'

logger = logging.getLogger(__name__)


class RelstRequestError(Exception):
    """Error that should be reported to the caller as-is (http-like status code)"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RelstServer(ABC):
    def __init__(self, server_port: int, request_handler, trace_limit: int = 500):
        self._server_port = server_port
        self._request_handler = request_handler
        self._callables: Dict[str, Callable] = dict()
        self._relst_callables: Dict[str, Callable] = dict()
        self.traces = TraceLog(trace_limit)

        self._thread: Optional[threading.Thread] = None

        self._register_attributes()
        self.__register_relst_methods()

    @property
    def port(self) -> int:
        """the actually bound port (differs from requested one when requested port is 0)"""
        return self._server_port

    def serve(self):
        """blocking"""
        self._bind()

        try:
            self._run()
        finally:
            self._close()

    def start(self) -> 'RelstServer':
        """serve in a background thread, returns once the server accepts connections"""
        self._bind()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._close()

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    @abstractmethod
    def _bind(self):
        pass

    @abstractmethod
    def _run(self):
        pass

    @abstractmethod
    def _close(self):
        pass

    def handle(self, codec: Codec, method: Optional[str], body: bytes, transport: str,
               response_codec: Optional[Codec] = None) -> Tuple[int, bytes]:
        """
        :brief: transport-agnostic request pipeline: decode, dispatch, encode, trace. never raises
        :param method: method-name the transport knows about (url / frame), None to use the payload's
        :param response_codec: protocol of the response, same as request's by default
        :return: (http-like status, encoded response)
        """

        started = perf_counter()
        response_codec = response_codec or codec
        status, response, method = self.__handle(codec, response_codec, method, body)

        self.traces.record(
            transport=transport,
            protocol=codec.name if response_codec is codec else f'{codec.name}->{response_codec.name}',
            method=method,
            status=status,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            request=render_body(body, codec.is_binary),
            response=render_body(response, response_codec.is_binary),
        )

        return status, response

    def __handle(self, codec: Codec, response_codec: Codec, method: Optional[str], body: bytes) -> Tuple[int, bytes, Optional[str]]:
        try:
            payload_method, kwargs = codec.decode_request(body)

            if method and payload_method and method != payload_method:
                raise RelstRequestError(400, f'method mismatch: {method!r} vs {payload_method!r}')

            method = method or payload_method

            if not method:
                raise RelstRequestError(400, 'request has no method name')

            return 200, response_codec.encode_response(self.dispatch(method, kwargs)), method
        except RelstRequestError as err:
            return err.code, response_codec.encode_error(err.code, err.message), method
        except RelstProtocolError as err:
            return 400, response_codec.encode_error(400, str(err)), method
        except Exception:
            logger.exception('Failed handling request for %s', method)
            return 500, response_codec.encode_error(500, SERVER_ERROR_MESSAGE), method

    def dispatch(self, method: str, kwargs: dict):
        """
        :except: RelstRequestError for unknown methods and bad arguments,
                 anything the method itself raises is propagated
        """

        callable = self._relst_callables.get(method) or self._callables.get(method)

        if not callable:
            logger.warning('Attempt to access non existing function %s', method)
            raise RelstRequestError(404, f'Method {method} does not exist')

        method_signature = signature(callable)

        try:
            bound = method_signature.bind(**kwargs)
        except TypeError as err:
            raise RelstRequestError(400, f'Bad arguments for {method}: {err}') from None

        RelstServer.__coerce_arguments(method_signature, bound)
        result = callable(*bound.args, **bound.kwargs)

        if isawaitable(result):
            result = asyncio.run(RelstServer.__await(result))

        return result

    @staticmethod
    async def __await(awaitable):
        return await awaitable

    @staticmethod
    def __coerce_arguments(method_signature, bound):
        """json has no float/object distinction, rebuild the python types the signature asks for"""

        for name, value in bound.arguments.items():
            annotation = method_signature.parameters[name].annotation

            try:
                bound.arguments[name] = RelstServer.__coerce(annotation, value)
            except (ValueError, TypeError, KeyError) as err:
                raise RelstRequestError(400, f'Bad value for argument {name}: {err}') from None

    @staticmethod
    def __coerce(annotation, value):
        if annotation is float and isinstance(value, int) and not isinstance(value, bool):
            return float(value)

        if annotation is bytes and isinstance(value, str):
            return bytes.fromhex(value)

        if isinstance(annotation, type) and isinstance(value, dict):
            if hasattr(annotation, 'from_dict'):
                return annotation.from_dict(value)

            if hasattr(annotation, '__dataclass_fields__'):
                return annotation(**value)

        return value

    def _register_attributes(self):
        self._callables = dict(RelstServer.__get_object_methods(self._request_handler))

    def __register_relst_methods(self):
        # NOTE: relst-methods are the only methods allowed to start with '_'
        self._relst_callables = {
            '__get_class_name': self.__get_class_name,
            '__get_class_help': self.__get_class_help,
            '__get_methods_list': self.__get_methods_list,
            '__get_method_help': self.__get_method_help,
            '__update_server': self.__update_server,
        }

    def __get_class_name(self) -> str:
        return type(self._request_handler).__name__

    def __get_class_help(self) -> Optional[str]:
        return getdoc(self._request_handler)

    def __get_methods_list(self) -> Dict[str, dict]:
        return {
            callable_name: {**to_plain(signature(callable)), 'doc': getdoc(callable)}
            for callable_name, callable in self._callables.items()
        }

    def __get_method_help(self, method_name: str) -> Optional[str]:
        callable = self._callables.get(method_name)

        if not callable:
            raise RelstRequestError(404, f'Method {method_name} does not exist')

        return getdoc(callable)

    def __update_server(self) -> None:
        self._register_attributes()

    @staticmethod
    def __get_object_methods(obj) -> Iterator[Tuple[str, Callable]]:
        """
        :brief: public methods of obj (bound, static and class methods, plain functions)
        """

        for attribute_name in dir(obj):
            if attribute_name.startswith(PRIVATE_OR_PROTECTED_PREFIX):
                continue

            try:
                # NOTE: properties may be expensive or have side effects, never evaluate them
                if isinstance(getattr_static(obj, attribute_name), property):
                    continue

                attribute_value = getattr(obj, attribute_name)
            except Exception:
                # NOTE: race (attribute removed between dir(obj) and getattr) or a broken descriptor
                continue

            if isroutine(attribute_value):
                yield attribute_name, attribute_value
