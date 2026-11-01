import time
import pytest
from enum import IntEnum
from firstclass import firstclass, uint8_t, uint16_t, char_array
from relst.server import RelstTextualServer, RelstBinaryServer
from relst.client import RelstFlaskClient, RelstSocketClient


PROTOCOLS = ['json', 'xml', 'binary']


class Color(IntEnum):
    RED = 1
    BLUE = 2


@firstclass
class Point:
    x: uint16_t
    y: uint16_t


@firstclass
class Tagged:
    kind: uint8_t
    name: char_array[8]
    origin: Point


class Handler:
    """
    Test handler
    second line
    """

    calls = 0

    def echo(self, prefix: str, text: str) -> str:
        "Concatenates"
        return prefix + text

    def identity(self, value):
        return value

    def add(self, a: int, b: int = 10) -> int:
        return a + b

    def halve(self, value: float) -> float:
        return value / 2

    def length(self, data: bytes) -> int:
        return len(data)

    def swap(self, point: Point) -> Point:
        return Point(point.y, point.x)

    def tagged(self) -> Tagged:
        return Tagged(7, 'abc', Point(1, 2))

    def color(self) -> Color:
        return Color.BLUE

    def tuple_and_set(self):
        return (1, 2), {3}

    def nothing(self):
        return None

    def raising(self):
        raise RuntimeError('SECRET-INTERNAL-DETAIL')

    def slow(self, seconds: float):
        time.sleep(seconds)
        return seconds

    def counter(self) -> int:
        Handler.calls += 1
        return Handler.calls

    async def async_echo(self, text: str) -> str:
        return text

    @staticmethod
    def static_double(value: int) -> int:
        return value * 2

    @classmethod
    def class_name(cls) -> str:
        return cls.__name__

    def _private(self):
        return 'private'


@pytest.fixture
def handler():
    return Handler()


@pytest.fixture
def http_server(handler):
    with RelstTextualServer(0, handler) as server:
        yield server


@pytest.fixture
def tcp_server(handler):
    with RelstBinaryServer(0, handler) as server:
        yield server


@pytest.fixture(params=PROTOCOLS)
def http_client(request, http_server):
    with RelstFlaskClient('127.0.0.1', http_server.port, protocol=request.param) as client:
        yield client


@pytest.fixture
def tcp_client(tcp_server):
    with RelstSocketClient('127.0.0.1', tcp_server.port) as client:
        yield client


@pytest.fixture
def base_url(http_server):
    return f'http://127.0.0.1:{http_server.port}'
