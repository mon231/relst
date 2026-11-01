import struct
from typing import Optional, Tuple
from firstclass import firstclass, bytes_t, uint8_t, uint16_t, uint32_t
from .codec import Codec
from .values import to_plain
from .errors import RelstProtocolError, RelstRemoteError


MAGIC = b'RLST'
VERSION = 1
MAX_DEPTH = 64
MAX_NAME_LENGTH = 0xFFFF

KIND_REQUEST = 0
KIND_RESPONSE = 1
KIND_ERROR = 2

TAG_NONE, TAG_FALSE, TAG_TRUE, TAG_INT64, TAG_FLOAT64, TAG_STR, TAG_BYTES, TAG_LIST, TAG_DICT, TAG_BIGINT = range(10)


@firstclass(byteorder='big')
class FrameHeader:
    """
    Fixed 12-byte header preceding every binary relst message, followed by
    `name_length` bytes of utf8 method-name and `payload_length` bytes of payload
    """

    magic: bytes_t[4]
    version: uint8_t
    kind: uint8_t
    name_length: uint16_t
    payload_length: uint32_t


FRAME_HEADER_SIZE = FrameHeader.sizeof()


class Frame:
    def __init__(self, kind: int, name: str, payload: bytes):
        self.kind = kind
        self.name = name
        self.payload = payload

    def to_bytes(self) -> bytes:
        name = self.name.encode('utf-8')

        if len(name) > MAX_NAME_LENGTH:
            raise RelstProtocolError('method name too long')

        header = FrameHeader(MAGIC, VERSION, self.kind, len(name), len(self.payload))
        return header.to_bytes() + name + self.payload

    @classmethod
    def parse_header(cls, data: bytes) -> FrameHeader:
        if len(data) < FRAME_HEADER_SIZE:
            raise RelstProtocolError('truncated frame header')

        header = FrameHeader.unpack_from(data)

        if header.magic != MAGIC:
            raise RelstProtocolError('bad frame magic')

        if header.version != VERSION:
            raise RelstProtocolError(f'unsupported frame version {header.version}')

        if header.kind not in (KIND_REQUEST, KIND_RESPONSE, KIND_ERROR):
            raise RelstProtocolError(f'unknown frame kind {header.kind}')

        return header

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Frame':
        header = cls.parse_header(data)
        expected_size = FRAME_HEADER_SIZE + header.name_length + header.payload_length

        if len(data) != expected_size:
            raise RelstProtocolError(f'frame size mismatch: got {len(data)} bytes, header says {expected_size}')

        name_end = FRAME_HEADER_SIZE + header.name_length

        try:
            name = data[FRAME_HEADER_SIZE:name_end].decode('utf-8')
        except UnicodeDecodeError as err:
            raise RelstProtocolError('method name is not utf8') from err

        return cls(header.kind, name, data[name_end:])


class BinaryCodec(Codec):
    name = 'binary'
    content_type = 'application/octet-stream'

    def encode_request(self, method: str, kwargs: dict) -> bytes:
        return Frame(KIND_REQUEST, method, encode_value(kwargs)).to_bytes()

    def decode_request(self, data: bytes) -> Tuple[Optional[str], dict]:
        if not data:
            return None, dict()

        frame = Frame.from_bytes(data)

        if frame.kind != KIND_REQUEST:
            raise RelstProtocolError('expected a request frame')

        kwargs = decode_value(frame.payload)

        if not isinstance(kwargs, dict) or not all(isinstance(key, str) for key in kwargs):
            raise RelstProtocolError('request payload must be a dict of keyword-arguments')

        return frame.name or None, kwargs

    def encode_response(self, value) -> bytes:
        return Frame(KIND_RESPONSE, '', encode_value(value)).to_bytes()

    def encode_error(self, code: int, message: str) -> bytes:
        return Frame(KIND_ERROR, '', encode_value({'code': code, 'message': message})).to_bytes()

    def decode_response(self, data: bytes, status: int = 200):
        frame = Frame.from_bytes(data)
        value = decode_value(frame.payload)

        if frame.kind == KIND_ERROR:
            if not isinstance(value, dict):
                raise RelstProtocolError('malformed error frame')

            raise RelstRemoteError(value.get('code', status), str(value.get('message', '')))

        if frame.kind != KIND_RESPONSE:
            raise RelstProtocolError('expected a response frame')

        return value


def encode_value(value) -> bytes:
    output = bytearray()
    _encode(to_plain(value), output, 0)
    return bytes(output)


def decode_value(data: bytes):
    value, offset = _decode(memoryview(data), 0, 0)

    if offset != len(data):
        raise RelstProtocolError(f'{len(data) - offset} trailing bytes after value')

    return value


def _encode(value, output: bytearray, depth: int):
    if depth > MAX_DEPTH:
        raise RelstProtocolError(f'value nested deeper than {MAX_DEPTH}')

    if value is None:
        output.append(TAG_NONE)
    elif value is True:
        output.append(TAG_TRUE)
    elif value is False:
        output.append(TAG_FALSE)
    elif isinstance(value, int):
        if -2 ** 63 <= value < 2 ** 63:
            output.append(TAG_INT64)
            output += struct.pack('>q', value)
        else:
            raw = value.to_bytes((value.bit_length() + 8) // 8, 'big', signed=True)
            output.append(TAG_BIGINT)
            output += struct.pack('>I', len(raw)) + raw
    elif isinstance(value, float):
        output.append(TAG_FLOAT64)
        output += struct.pack('>d', value)
    elif isinstance(value, str):
        raw = value.encode('utf-8', 'surrogatepass')
        output.append(TAG_STR)
        output += struct.pack('>I', len(raw)) + raw
    elif isinstance(value, bytes):
        output.append(TAG_BYTES)
        output += struct.pack('>I', len(value)) + value
    elif isinstance(value, list):
        output.append(TAG_LIST)
        output += struct.pack('>I', len(value))

        for element in value:
            _encode(element, output, depth + 1)
    elif isinstance(value, dict):
        output.append(TAG_DICT)
        output += struct.pack('>I', len(value))

        for key, element in value.items():
            _encode(key, output, depth + 1)
            _encode(element, output, depth + 1)
    else:
        raise RelstProtocolError(f'unsupported value {type(value).__name__}')


def _take(data: memoryview, offset: int, size: int) -> memoryview:
    if size < 0 or offset + size > len(data):
        raise RelstProtocolError('truncated value')

    return data[offset:offset + size]


def _take_length(data: memoryview, offset: int) -> int:
    return struct.unpack('>I', _take(data, offset, 4))[0]


def _decode(data: memoryview, offset: int, depth: int):
    if depth > MAX_DEPTH:
        raise RelstProtocolError(f'value nested deeper than {MAX_DEPTH}')

    tag = _take(data, offset, 1)[0]
    offset += 1

    if tag == TAG_NONE:
        return None, offset

    if tag == TAG_FALSE:
        return False, offset

    if tag == TAG_TRUE:
        return True, offset

    if tag == TAG_INT64:
        return struct.unpack('>q', _take(data, offset, 8))[0], offset + 8

    if tag == TAG_FLOAT64:
        return struct.unpack('>d', _take(data, offset, 8))[0], offset + 8

    if tag in (TAG_STR, TAG_BYTES, TAG_BIGINT):
        length = _take_length(data, offset)
        raw = bytes(_take(data, offset + 4, length))
        offset += 4 + length

        if tag == TAG_BYTES:
            return raw, offset

        if tag == TAG_BIGINT:
            if not raw:
                raise RelstProtocolError('empty bigint')

            return int.from_bytes(raw, 'big', signed=True), offset

        try:
            return raw.decode('utf-8', 'surrogatepass'), offset
        except UnicodeDecodeError as err:
            raise RelstProtocolError('string is not utf8') from err

    if tag in (TAG_LIST, TAG_DICT):
        count = _take_length(data, offset)
        offset += 4
        entries_size = 1 if tag == TAG_LIST else 2

        # NOTE: every element takes at least a byte, stops forged huge counts before any allocation
        if count * entries_size > len(data) - offset:
            raise RelstProtocolError('container count exceeds payload size')

        if tag == TAG_LIST:
            result = []

            for _ in range(count):
                element, offset = _decode(data, offset, depth + 1)
                result.append(element)

            return result, offset

        mapping = dict()

        for _ in range(count):
            key, offset = _decode(data, offset, depth + 1)
            element, offset = _decode(data, offset, depth + 1)

            try:
                mapping[key] = element
            except TypeError as err:
                raise RelstProtocolError('unhashable dict key') from err

        return mapping, offset

    raise RelstProtocolError(f'unknown value tag {tag}')
