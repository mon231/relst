"""
Serves one handler object twice:
  * http  on 127.0.0.1:1736  (json / xml / binary payloads + the console at /_relst/ui)
  * tcp   on 127.0.0.1:1737  (compact binary frames)

Run it, open http://127.0.0.1:1736/_relst/ui, then run client_demo.py
"""

import random
from firstclass import firstclass, uint8_t, uint16_t, char_array
from relst.server import RelstTextualServer, RelstBinaryServer


HTTP_PORT = 1736
TCP_PORT = 1737


@firstclass
class Point:
    x: uint16_t
    y: uint16_t


@firstclass
class Sensor:
    kind: uint8_t
    name: char_array[8]
    position: Point


class Demo:
    """
    Demo relst server.
    Every public method of this object is exposed, methods starting with '_' are not.
    """

    def echo(self, prefix: str, text: str) -> str:
        "Concatenates prefix and text"
        return prefix + text

    def add(self, a: int, b: int = 10) -> int:
        "Adds two numbers, b defaults to 10"
        return a + b

    def mirror(self, point: Point) -> Point:
        "Swaps x and y, accepts / returns a firstclass struct"
        return Point(point.y, point.x)

    def sensor(self) -> Sensor:
        return Sensor(7, 'thermo', Point(3, 4))

    def checksum(self, data: bytes) -> int:
        "Sums the bytes of `data`, bytes are first-class in the binary and json protocols"
        return sum(data) & 0xFFFF

    def get_random_value(self):
        return random.choice(('m', 1, 5.5, False, None, [1, 2], {'k': b'v'}))

    async def get_length(self, string: str) -> int:
        "Coroutines are supported"
        return len(string)

    @staticmethod
    def static_double(value: int) -> int:
        return value * 2

    def fail(self):
        "Raises, callers get a generic 500 (details stay in the server log)"
        raise RuntimeError('this message never reaches the client')

    def _will_not_be_exposed(self):
        return 'MySecretCode'


def main():
    handler = Demo()

    RelstTextualServer(HTTP_PORT, handler).start()
    print(f'http console: http://127.0.0.1:{HTTP_PORT}/_relst/ui')
    print(f'tcp binary:   127.0.0.1:{TCP_PORT}')

    RelstBinaryServer(TCP_PORT, handler).serve()


if __name__ == "__main__":
    main()
