"""
Compact binary wire format.

Frame
    header      1 byte   (FrameHeader: kind:2 | version:2 | reserved:4)
    name_size   varint   \\ requests only, 0 when the transport already carries the method (http url)
    name        utf8     /
    payload_size varint
    payload     value    (an empty payload means {} for requests and None for responses)

Sizes are unsigned LEB128 varints limited to the uint32 range (1 byte up to 127, 5 bytes at most).

Value (first byte)
    1xxxxxxx    small uint 0..127
    01xxxxxx    str of 0..63 bytes, bytes follow
    001xxxxx    list of 0..31 elements
    0001xxxx    dict of 0..15 entries (key, value, key, value...)
    0000xxxx    ValueTag: NONE FALSE TRUE INT(zigzag varint) FLOAT32 FLOAT64 STR BYTES LIST DICT
                (the last four are followed by a varint size / count)
"""

import struct
from enum import IntEnum
from typing import Callable, Optional, Tuple
from firstclass import firstclass, bitfield, uint8_t
from .codec import Codec
from .values import to_plain
from .errors import RelstProtocolError, RelstRemoteError


VERSION = 1
MAX_DEPTH = 64
MAX_SIZE = 0xFFFFFFFF
MAX_NAME_SIZE = 0xFFFF
MAX_INT_BYTES = 4096


class FrameKind(IntEnum):
    REQUEST = 0
    RESPONSE = 1
    ERROR = 2


class ValueTag(IntEnum):
    NONE = 0
    FALSE = 1
    TRUE = 2
    INT = 3
    FLOAT32 = 4
    FLOAT64 = 5
    STR = 6
    BYTES = 7
    LIST = 8
    DICT = 9


SMALL_UINT_FLAG = 0x80
SHORT_STR_FLAG = 0x40
SHORT_LIST_FLAG = 0x20
SHORT_DICT_FLAG = 0x10
SHORT_STR_MAX, SHORT_LIST_MAX, SHORT_DICT_MAX = 0x3F, 0x1F, 0x0F


@firstclass
class FrameHeader:
    """The whole fixed part of a frame: a single byte"""

    kind: bitfield[uint8_t, 2]
    version: bitfield[uint8_t, 2]
    reserved: bitfield[uint8_t, 4]


FRAME_HEADER_SIZE = FrameHeader.sizeof()
Reader = Callable[[int], bytes]


# ---------------------------------------------------------------- varints

def encode_varint(number: int) -> bytes:
    if not 0 <= number <= MAX_SIZE:
        raise RelstProtocolError(f'size {number} does not fit uint32')

    output = bytearray()

    while number > 0x7F:
        output.append((number & 0x7F) | 0x80)
        number >>= 7

    output.append(number)
    return bytes(output)


def _read_varint(data: memoryview, offset: int, limit: int = MAX_SIZE) -> Tuple[int, int]:
    number = shift = 0

    for index in range(5):
        byte = _take(data, offset + index, 1)[0]
        number |= (byte & 0x7F) << shift
        shift += 7

        if not byte & 0x80:
            if number > limit:
                raise RelstProtocolError(f'size {number} exceeds limit {limit}')

            return number, offset + index + 1

    raise RelstProtocolError('varint longer than uint32')


# ---------------------------------------------------------------- frames

class Frame:
    def __init__(self, kind: int, name: str, payload: bytes):
        self.kind = FrameKind(kind)
        self.name = name
        self.payload = payload

    def to_bytes(self) -> bytes:
        output = bytearray(FrameHeader(self.kind, VERSION, 0).to_bytes())

        if self.kind == FrameKind.REQUEST:
            name = self.name.encode('utf-8')

            if len(name) > MAX_NAME_SIZE:
                raise RelstProtocolError('method name too long')

            output += encode_varint(len(name)) + name

        output += encode_varint(len(self.payload)) + self.payload
        return bytes(output)

    @classmethod
    def read(cls, read: Reader, max_size: int = MAX_SIZE) -> Tuple['Frame', bytes]:
        """
        :brief: reads exactly one frame from a stream
        :param read: read(n) -> exactly n bytes, raises when stream ends
        :return: (frame, raw bytes of the frame)
        """

        raw = bytearray()

        def take(size: int) -> bytes:
            data = read(size)
            raw.extend(data)
            return data

        def take_varint(limit: int) -> int:
            data = bytearray()

            for _ in range(5):
                byte = take(1)
                data += byte

                if not byte[0] & 0x80:
                    return _read_varint(memoryview(bytes(data)), 0, limit)[0]

            raise RelstProtocolError('varint longer than uint32')

        kind = cls.parse_header(take(FRAME_HEADER_SIZE))
        name = ''

        if kind == FrameKind.REQUEST:
            name = cls.__decode_name(take(take_varint(MAX_NAME_SIZE)))

        payload = take(take_varint(max_size))
        return cls(kind, name, payload), bytes(raw)

    @classmethod
    def parse_header(cls, data: bytes) -> FrameKind:
        if len(data) < FRAME_HEADER_SIZE:
            raise RelstProtocolError('truncated frame header')

        header = FrameHeader.unpack_from(data)

        if header.version != VERSION or header.reserved:
            raise RelstProtocolError(f'unsupported frame version {header.version}')

        try:
            return FrameKind(header.kind)
        except ValueError:
            raise RelstProtocolError(f'unknown frame kind {header.kind}') from None

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Frame':
        stream = memoryview(data)
        position = 0

        def read(size: int) -> bytes:
            nonlocal position

            if position + size > len(stream):
                raise RelstProtocolError('truncated frame')

            chunk = bytes(stream[position:position + size])
            position += size
            return chunk

        frame, _ = cls.read(read)

        if position != len(data):
            raise RelstProtocolError(f'{len(data) - position} trailing bytes after frame')

        return frame

    @staticmethod
    def __decode_name(raw: bytes) -> str:
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError as err:
            raise RelstProtocolError('method name is not utf8') from err


# ---------------------------------------------------------------- codec

class BinaryCodec(Codec):
    name = 'binary'
    content_type = 'application/octet-stream'

    def encode_request(self, method: str, kwargs: dict, embed_method: bool = True) -> bytes:
        payload = b'' if not kwargs else encode_value(kwargs)
        return Frame(FrameKind.REQUEST, method if embed_method else '', payload).to_bytes()

    def decode_request(self, data: bytes) -> Tuple[Optional[str], dict]:
        if not data:
            return None, dict()

        frame = Frame.from_bytes(data)

        if frame.kind != FrameKind.REQUEST:
            raise RelstProtocolError('expected a request frame')

        kwargs = decode_value(frame.payload) if frame.payload else dict()

        if not isinstance(kwargs, dict) or not all(isinstance(key, str) for key in kwargs):
            raise RelstProtocolError('request payload must be a dict of keyword-arguments')

        return frame.name or None, kwargs

    def encode_response(self, value) -> bytes:
        payload = b'' if value is None else encode_value(value)
        return Frame(FrameKind.RESPONSE, '', payload).to_bytes()

    def encode_error(self, code: int, message: str) -> bytes:
        return Frame(FrameKind.ERROR, '', encode_value([code, message])).to_bytes()

    def decode_response(self, data: bytes, status: int = 200):
        frame = Frame.from_bytes(data)

        if frame.kind == FrameKind.ERROR:
            error = decode_value(frame.payload)

            if not (isinstance(error, list) and len(error) == 2 and isinstance(error[0], int) and isinstance(error[1], str)):
                raise RelstProtocolError('malformed error frame')

            raise RelstRemoteError(error[0], error[1])

        if frame.kind != FrameKind.RESPONSE:
            raise RelstProtocolError('expected a response frame')

        return decode_value(frame.payload) if frame.payload else None


# ---------------------------------------------------------------- values

def encode_value(value) -> bytes:
    output = bytearray()
    _encode(to_plain(value), output, 0)
    return bytes(output)


def decode_value(data: bytes):
    value, offset = _decode(memoryview(data), 0, 0)

    if offset != len(data):
        raise RelstProtocolError(f'{len(data) - offset} trailing bytes after value')

    return value


def _zigzag(number: int) -> int:
    return (number << 1) if number >= 0 else ((-number << 1) - 1)


def _unzigzag(number: int) -> int:
    return (number >> 1) if not number & 1 else -((number + 1) >> 1)


def _write_varint_unbounded(number: int, output: bytearray):
    while number > 0x7F:
        output.append((number & 0x7F) | 0x80)
        number >>= 7

    output.append(number)


def _write_sized(tag: ValueTag, size: int, output: bytearray):
    output.append(tag)
    output += encode_varint(size)


def _encode(value, output: bytearray, depth: int):
    if depth > MAX_DEPTH:
        raise RelstProtocolError(f'value nested deeper than {MAX_DEPTH}')

    if value is None:
        output.append(ValueTag.NONE)
    elif value is True:
        output.append(ValueTag.TRUE)
    elif value is False:
        output.append(ValueTag.FALSE)
    elif isinstance(value, int):
        if 0 <= value <= 0x7F:
            output.append(SMALL_UINT_FLAG | value)
        else:
            if value.bit_length() > MAX_INT_BYTES * 7:
                raise RelstProtocolError('int too big')

            output.append(ValueTag.INT)
            _write_varint_unbounded(_zigzag(value), output)
    elif isinstance(value, float):
        single = struct.pack('>f', value) if _fits_float32(value) else None

        if single is not None:
            output.append(ValueTag.FLOAT32)
            output += single
        else:
            output.append(ValueTag.FLOAT64)
            output += struct.pack('>d', value)
    elif isinstance(value, str):
        raw = value.encode('utf-8', 'surrogatepass')

        if len(raw) <= SHORT_STR_MAX:
            output.append(SHORT_STR_FLAG | len(raw))
        else:
            _write_sized(ValueTag.STR, len(raw), output)

        output += raw
    elif isinstance(value, bytes):
        _write_sized(ValueTag.BYTES, len(value), output)
        output += value
    elif isinstance(value, list):
        if len(value) <= SHORT_LIST_MAX:
            output.append(SHORT_LIST_FLAG | len(value))
        else:
            _write_sized(ValueTag.LIST, len(value), output)

        for element in value:
            _encode(element, output, depth + 1)
    elif isinstance(value, dict):
        if len(value) <= SHORT_DICT_MAX:
            output.append(SHORT_DICT_FLAG | len(value))
        else:
            _write_sized(ValueTag.DICT, len(value), output)

        for key, element in value.items():
            _encode(key, output, depth + 1)
            _encode(element, output, depth + 1)
    else:
        raise RelstProtocolError(f'unsupported value {type(value).__name__}')


def _fits_float32(value: float) -> bool:
    """True when the float survives a trip through 32 bits unchanged (nan and inf included)"""
    try:
        packed = struct.pack('>f', value)
    except OverflowError:
        return False

    unpacked = struct.unpack('>f', packed)[0]
    return struct.pack('>d', unpacked) == struct.pack('>d', value)


def _take(data: memoryview, offset: int, size: int) -> memoryview:
    if size < 0 or offset + size > len(data):
        raise RelstProtocolError('truncated value')

    return data[offset:offset + size]


def _decode(data: memoryview, offset: int, depth: int):
    if depth > MAX_DEPTH:
        raise RelstProtocolError(f'value nested deeper than {MAX_DEPTH}')

    first = _take(data, offset, 1)[0]
    offset += 1

    if first & SMALL_UINT_FLAG:
        return first & 0x7F, offset

    if first & SHORT_STR_FLAG:
        return _decode_str(data, offset, first & SHORT_STR_MAX)

    if first & SHORT_LIST_FLAG:
        return _decode_list(data, offset, first & SHORT_LIST_MAX, depth)

    if first & SHORT_DICT_FLAG:
        return _decode_dict(data, offset, first & SHORT_DICT_MAX, depth)

    try:
        tag = ValueTag(first)
    except ValueError:
        raise RelstProtocolError(f'unknown value tag {first}') from None

    if tag == ValueTag.NONE:
        return None, offset

    if tag == ValueTag.FALSE:
        return False, offset

    if tag == ValueTag.TRUE:
        return True, offset

    if tag == ValueTag.FLOAT32:
        return struct.unpack('>f', _take(data, offset, 4))[0], offset + 4

    if tag == ValueTag.FLOAT64:
        return struct.unpack('>d', _take(data, offset, 8))[0], offset + 8

    if tag == ValueTag.INT:
        return _decode_int(data, offset)

    size, offset = _read_varint(data, offset)

    if tag == ValueTag.STR:
        return _decode_str(data, offset, size)

    if tag == ValueTag.BYTES:
        return bytes(_take(data, offset, size)), offset + size

    if tag == ValueTag.LIST:
        return _decode_list(data, offset, size, depth)

    return _decode_dict(data, offset, size, depth)


def _decode_int(data: memoryview, offset: int) -> Tuple[int, int]:
    number = shift = 0

    for index in range(MAX_INT_BYTES):
        byte = _take(data, offset + index, 1)[0]
        number |= (byte & 0x7F) << shift
        shift += 7

        if not byte & 0x80:
            return _unzigzag(number), offset + index + 1

    raise RelstProtocolError('int too big')


def _decode_str(data: memoryview, offset: int, size: int) -> Tuple[str, int]:
    try:
        return bytes(_take(data, offset, size)).decode('utf-8', 'surrogatepass'), offset + size
    except UnicodeDecodeError as err:
        raise RelstProtocolError('string is not utf8') from err


def _decode_list(data: memoryview, offset: int, count: int, depth: int):
    # NOTE: every element takes at least a byte, stops forged huge counts before any allocation
    if count > len(data) - offset:
        raise RelstProtocolError('container count exceeds payload size')

    result = []

    for _ in range(count):
        element, offset = _decode(data, offset, depth + 1)
        result.append(element)

    return result, offset


def _decode_dict(data: memoryview, offset: int, count: int, depth: int):
    if count * 2 > len(data) - offset:
        raise RelstProtocolError('container count exceeds payload size')

    mapping = dict()

    for _ in range(count):
        key, offset = _decode(data, offset, depth + 1)
        element, offset = _decode(data, offset, depth + 1)

        try:
            mapping[key] = element
        except TypeError as err:
            raise RelstProtocolError('unhashable dict key') from err

    return mapping, offset
