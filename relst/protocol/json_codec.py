import json
import math
from typing import Optional, Tuple
from .codec import Codec
from .values import to_plain, text_keys
from .errors import RelstProtocolError, RelstRemoteError


BYTES_MARKER = '$bytes'
FLOAT_MARKER = '$float'
ESCAPE_MARKER = '$dict'
FLOAT_NAMES = {'nan': math.nan, 'inf': math.inf, '-inf': -math.inf}


class JsonCodec(Codec):
    name = 'json'
    content_type = 'application/json'

    @property
    def is_binary(self) -> bool:
        return False

    def encode_request(self, method: str, kwargs: dict, embed_method: bool = True) -> bytes:
        return self._dumps(kwargs)

    def decode_request(self, data: bytes) -> Tuple[Optional[str], dict]:
        if not data or not data.strip():
            return None, dict()

        kwargs = self._loads(data)

        if not isinstance(kwargs, dict):
            raise RelstProtocolError('json request body must be an object of keyword-arguments')

        return None, kwargs

    def encode_response(self, value) -> bytes:
        return self._dumps(value)

    def encode_error(self, code: int, message: str) -> bytes:
        return self._dumps({'error': {'code': code, 'message': message}})

    def decode_response(self, data: bytes, status: int = 200):
        value = self._loads(data)

        if status >= 400:
            error = value.get('error') if isinstance(value, dict) else None
            error = error if isinstance(error, dict) else {}
            raise RelstRemoteError(error.get('code', status), error.get('message', str(value)))

        return value

    @staticmethod
    def _dumps(value) -> bytes:
        try:
            return json.dumps(_mark(text_keys(to_plain(value))), allow_nan=False, ensure_ascii=True).encode('ascii')
        except (ValueError, RecursionError, OverflowError) as err:
            raise RelstProtocolError(f'unable to encode json: {err}') from err

    @staticmethod
    def _loads(data: bytes):
        def reject_constant(name):
            raise ValueError(f'invalid json constant {name}')

        try:
            return _unmark(json.loads(data, parse_constant=reject_constant))
        except (ValueError, RecursionError) as err:
            # NOTE: UnicodeDecodeError and JSONDecodeError are ValueErrors
            raise RelstProtocolError(f'invalid json: {err}') from err


def _mark(value):
    """json can't carry bytes / nan / inf, wrap them into marker-objects"""
    if isinstance(value, bytes):
        return {BYTES_MARKER: value.hex()}

    if isinstance(value, float) and not math.isfinite(value):
        return {FLOAT_MARKER: 'nan' if math.isnan(value) else ('inf' if value > 0 else '-inf')}

    if isinstance(value, list):
        return [_mark(element) for element in value]

    if isinstance(value, dict):
        marked = {key: _mark(element) for key, element in value.items()}

        if any(key.startswith('$') for key in marked):
            return {ESCAPE_MARKER: marked}

        return marked

    return value


def _unmark(value):
    if isinstance(value, list):
        return [_unmark(element) for element in value]

    if not isinstance(value, dict):
        return value

    if len(value) == 1:
        (key, content), = value.items()

        if key == ESCAPE_MARKER and isinstance(content, dict):
            return {name: _unmark(element) for name, element in content.items()}

        if key == BYTES_MARKER:
            try:
                return bytes.fromhex(content)
            except (TypeError, ValueError) as err:
                raise RelstProtocolError(f'invalid {BYTES_MARKER} hex') from err

        if key == FLOAT_MARKER:
            if content not in FLOAT_NAMES:
                raise RelstProtocolError(f'invalid {FLOAT_MARKER} value')

            return FLOAT_NAMES[content]

    return {name: _unmark(element) for name, element in value.items()}
