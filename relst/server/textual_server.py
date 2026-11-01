import json
import logging
from pathlib import Path
from flask import Flask, Response, request
from waitress import create_server
from werkzeug.exceptions import HTTPException
from .relst_server import RelstServer
from ..protocol import (
    CODECS, DEFAULT_PROTOCOL, JsonCodec, RelstProtocolError, RelstRemoteError,
    codec_from_content_type, get_codec,
)


UI_PATH = Path(__file__).parent / 'ui' / 'index.html'
UI_PREFIX = '/_relst'
MAX_REQUEST_BYTES = 1024 * 1024

logger = logging.getLogger(__name__)


class RelstTextualServer(RelstServer):
    """
    Relst over http, serves json / xml / binary payloads according to the request's Content-Type.
    Responses use the request's protocol unless the Accept header asks for another one.
    Also serves a swagger-like console (to trace requests and send manual ones) at /_relst/ui
    """

    def __init__(self, server_port: int, request_handler, host: str = '127.0.0.1', enable_ui: bool = True, trace_limit: int = 500):
        super().__init__(server_port, request_handler, trace_limit)

        self._host = host
        self._http_server = None
        self.__flask_app = Flask(__name__)
        self.__flask_app.config['MAX_CONTENT_LENGTH'] = MAX_REQUEST_BYTES

        self.__init_server()
        self.__register_exceptions_handler()

        if enable_ui:
            self.__init_ui()

    def _bind(self):
        self._http_server = create_server(self.__flask_app, host=self._host, port=self._server_port)
        self._server_port = self._http_server.effective_port

    def _run(self):
        http_server = self._http_server

        try:
            http_server.run()
        except OSError:
            # NOTE: waitress' loop dies on its closed sockets when stopped from another thread
            if self._http_server is not None:
                raise

    def _close(self):
        http_server, self._http_server = self._http_server, None

        if http_server:
            http_server.close()

    def __register_exceptions_handler(self):
        @self.__flask_app.errorhandler(Exception)
        def on_server_error(err: Exception):
            if isinstance(err, HTTPException):
                return self.__error_response(err.code, err.description or err.name)

            logger.exception('Unhandled error')
            return self.__error_response(500, 'Server error handling request')

    def __init_server(self):
        @self.__flask_app.route('/<callable_name>', methods=['POST', 'GET'])
        def handle_request(callable_name):
            try:
                codec = codec_from_content_type(request.content_type)
            except RelstProtocolError as err:
                return self.__error_response(415, str(err))

            response_codec = self.__response_codec(codec)
            status, body = self.handle(codec, callable_name, request.get_data(), 'http', response_codec)
            return Response(body, status=status, content_type=response_codec.content_type)

    @staticmethod
    def __response_codec(request_codec):
        accepted = request.headers.get('Accept', '')

        for codec in CODECS.values():
            if codec.content_type in accepted:
                return codec

        return request_codec

    @staticmethod
    def __error_response(code: int, message: str) -> Response:
        body = JsonCodec().encode_error(code, message)
        return Response(body, status=code, content_type=JsonCodec.content_type)

    def __init_ui(self):
        app = self.__flask_app

        @app.get(f'{UI_PREFIX}/ui')
        def ui_page():
            return Response(UI_PATH.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')

        @app.get(f'{UI_PREFIX}/info')
        def ui_info():
            methods = self.dispatch('__get_methods_list', {})

            return self.__json({
                'name': self.dispatch('__get_class_name', {}),
                'help': self.dispatch('__get_class_help', {}),
                'protocols': {name: codec.content_type for name, codec in CODECS.items()},
                'methods': methods,
            })

        @app.get(f'{UI_PREFIX}/traces')
        def ui_traces():
            after = request.args.get('after', default=0, type=int)
            return self.__json(self.traces.entries(after))

        @app.delete(f'{UI_PREFIX}/traces')
        def ui_clear_traces():
            self.traces.clear()
            return self.__json({'cleared': True})

        @app.post(f'{UI_PREFIX}/try')
        def ui_try():
            # NOTE: json-only, forces a cors preflight so foreign web-pages can't call methods through here
            if request.mimetype != JsonCodec.content_type:
                return self.__error_response(415, 'Content-Type must be application/json')

            return self.__json(self.__try_request(request.get_json(silent=True)))

    def __try_request(self, spec) -> dict:
        """
        :brief: builds (and optionally sends) a request of any protocol
        :param spec: {method, protocol, args | raw, [raw_encoding: text|hex], [send: bool]}
        """

        if not isinstance(spec, dict) or not isinstance(spec.get('method'), str):
            return {'error': 'body must be an object with a "method" string'}

        try:
            codec = get_codec(spec.get('protocol', DEFAULT_PROTOCOL))
            body = self.__spec_to_request_bytes(codec, spec)
        except (RelstProtocolError, ValueError, TypeError) as err:
            return {'error': str(err)}

        result = {'request': body.hex() if codec.is_binary else body.decode('utf-8', 'replace'), 'binary': codec.is_binary}

        if not spec.get('send', True):
            return result

        status, response = self.handle(codec, spec['method'], body, 'ui')
        result.update(status=status, response=response.hex() if codec.is_binary else response.decode('utf-8', 'replace'))

        try:
            result['decoded'] = json.loads(JsonCodec().encode_response(codec.decode_response(response, status)))
        except RelstRemoteError as err:
            result['decoded'] = {'error': {'code': err.code, 'message': err.message}}
        except RelstProtocolError as err:
            result['decoded_error'] = str(err)

        return result

    @staticmethod
    def __spec_to_request_bytes(codec, spec: dict) -> bytes:
        if 'raw' in spec:
            raw = spec['raw']

            if not isinstance(raw, str):
                raise TypeError('raw must be a string')

            return bytes.fromhex(raw) if spec.get('raw_encoding') == 'hex' else raw.encode('utf-8')

        args = spec.get('args', dict())

        if not isinstance(args, dict):
            raise TypeError('args must be an object')

        return codec.encode_request(spec['method'], args)

    @staticmethod
    def __json(value) -> Response:
        return Response(json.dumps(value), content_type=JsonCodec.content_type)
