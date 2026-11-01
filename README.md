# relst

Expose any python object as an API, and call it from python as if it were local.
One server, three wire formats: **json**, **xml** and a very small **binary** protocol,
plus a swagger-like console to trace and hand-craft requests.

[![PyPI](https://img.shields.io/pypi/v/relst)](https://pypi.org/project/relst/)

## Installation

```bash
pip install relst
```

Python 3.10+. Optional desktop client extras: `pip install "relst[gui]"`.
Source code: <https://github.com/mon231/relst>

## Quick start

Server:

```py
from relst.server import RelstTextualServer


class Calculator:
    """Server's help string"""

    def add(self, a: int, b: int = 10) -> int:
        "Help string of this method"
        return a + b

    async def shout(self, text: str) -> str:
        return text.upper()

    def _not_exposed(self):
        return 'MySecretCode'


RelstTextualServer(1736, Calculator()).serve()
```

Client:

```py
from relst.client import RelstFlaskClient

with RelstFlaskClient('127.0.0.1', 1736, protocol='binary') as client:   # json | xml | binary
    print(client.add(1, b=2))      # 3, server methods became python methods
    print(client.shout('hi'))      # 'HI'
    print(client.METHOD_HELP('add'))
```

Open <http://127.0.0.1:1736/_relst/ui> for the console. More in [`examples/`](examples/README.md).

## What gets exposed

Every public (not starting with `_`) method of the handler object: instance methods, `staticmethod`,
`classmethod`, and `async def` coroutines. Arguments are keyword arguments, validated against the
method signature before the call (`400` on mismatch). Type hints are used to rebuild values:
`float` accepts ints, `bytes` accepts hex strings, and `firstclass` / dataclass hints accept dicts.

Return values may be `None`, `bool`, `int`, `float`, `str`, `bytes`, lists/tuples/sets, dicts,
enums, dataclasses and [`firstclass`](https://pypi.org/project/firstclass/) objects.

Failures reach the client as `RelstRemoteError(code, message)`:

| code | meaning |
|---|---|
| 400 | malformed payload, bad / missing arguments, bad value for a `firstclass` argument |
| 404 | unknown (or private) method |
| 413 | request bigger than 1 MiB (http) |
| 415 | unsupported `Content-Type` |
| 500 | the method raised, the message is generic, details stay in the server log |

Built-in methods (`__get_class_name`, `__get_class_help`, `__get_methods_list`, `__get_method_help`,
`__update_server`) power the client's `CLASS_NAME()`, `CLASS_HELP()`, `METHOD_HELP(name)`,
`UPDATE_SERVER()` and `UPDATE_METHODS()`. Uppercase client names are reserved, a server method can
never shadow them.

## Servers and clients

| class | transport | protocols |
|---|---|---|
| `RelstTextualServer(port, handler, host='127.0.0.1', enable_ui=True, trace_limit=500)` | http (waitress + flask) | json, xml, binary by `Content-Type` |
| `RelstBinaryServer(port, handler, host='127.0.0.1')` | raw tcp, connections are reused | binary |
| `RelstFlaskClient(address, port, is_https=False, protocol='json')` | http | json, xml, binary |
| `RelstSocketClient(address, port)` | tcp (thread-safe, auto-reconnect) | binary |

Servers bind to `127.0.0.1` by default; pass `host='0.0.0.0'` to expose them. `serve()` blocks,
`start()` / `stop()` / `with server:` run in the background (`port=0` picks a free port, read it
from `server.port`).

## Protocols

The protocol of an http request is picked by `Content-Type` (default json), the response uses the
same protocol unless `Accept` names another one. The method name is the url path: `POST /add`.

### json (`application/json`)

Body is an object of keyword arguments, the response body is the returned value.
Things json can't carry are wrapped: bytes as `{"$bytes": "00ff"}`, nan/inf as `{"$float": "nan"}`
(a dict that itself has `$`-keys is wrapped in `{"$dict": ...}`).
Errors: `{"error": {"code": 404, "message": "..."}}` with the matching http status.

### xml (`application/xml`)

```xml
<request method="add">
  <arg name="a"><value type="int">1</value></arg>
</request>
<!-- response -->  <response><value type="int">11</value></response>
<!-- error -->     <error code="404">Method x does not exist</error>
```

Value types: `none bool int float str bytes list dict`; `<value>` without a type is a string,
strings that xml can't carry (control characters, `\r`) travel as `encoding="base64"`.
DTDs / entities are rejected.

### binary (`application/octet-stream`, also raw tcp)

Built for minimal traffic: a 1-byte header, varint sizes (unsigned LEB128, uint32 range), no magic,
no padding.

```
frame    = header:1  [name_size:varint name:utf8]  payload_size:varint  payload
header   = FrameKind:2 bits | version:2 bits | reserved:4 bits       (a firstclass bitfield struct)
FrameKind: REQUEST=0  RESPONSE=1  ERROR=2
```

- The `name` part exists only in requests, and is empty (1 byte) over http where the url has the method.
- An empty payload is `{}` in a request and `None` in a response.
- An error payload is the value `[code, message]`.

```
value (first byte)
  1xxxxxxx   small uint 0..127                  (1 byte total)
  01xxxxxx   str, 0..63 utf8 bytes follow
  001xxxxx   list, 0..31 elements follow
  0001xxxx   dict, 0..15 key/value pairs follow
  0000xxxx   ValueTag: NONE=0 FALSE=1 TRUE=2 INT=3 FLOAT32=4 FLOAT64=5 STR=6 BYTES=7 LIST=8 DICT=9
             INT is a zigzag varint (any size), STR/BYTES/LIST/DICT carry a varint size or count,
             floats are 4 bytes when that is lossless, else 8 (big-endian)
```

The same call `{"prefix": "pre", "text": "txt", "count": 3, "flag": true, "blob": b"\x00\x01"}`:
json 86 bytes, xml 324 bytes, binary 46 bytes (`python examples/wire_formats.py`).

Safety limits (all protocols): nesting depth 64, 1 MiB per http body / tcp frame, forged lengths
and counts are rejected before allocating, bad input is always a `400` / `RelstProtocolError`,
never a crash.

## Console (swagger-like UI)

`http://<host>:<port>/_relst/ui` on every `RelstTextualServer`:

- **Methods**: signatures, docstrings, a generated form per method; run it in json, xml or binary.
- **Generate request**: shows the raw request (text, or hex for binary) without sending it.
  Edit the bytes freely and **Send raw** to test malformed or hand-written payloads.
- **Traces**: live table of everything the server handled (http, tcp and console calls) with raw
  request/response, status and duration. `GET /_relst/traces?after=<id>` returns the same as json,
  `DELETE /_relst/traces` clears it. `RelstBinaryServer.traces` is available in code for tcp.

Disable with `enable_ui=False`. Executing methods from the console needs a json POST (so
other websites can't trigger calls through your browser), keep the default `127.0.0.1` bind
unless you trust the network.

## Development

```bash
git clone https://github.com/mon231/relst
cd relst
pip install -e ".[dev]"
python -m pytest tests
```

The suite (250+ tests) covers property-based round trips of every protocol, fuzzed / mutated /
hostile payloads (XML entity bombs, deep nesting, huge ints, forged binary lengths), http and tcp
end-to-end behavior, concurrency, server restarts and the console endpoints.

Publishing: pushing a version tag releases to PyPI through GitHub Actions (`.github/workflows/publish.yml`,
needs the repo secret `PYPI_API_TOKEN`). The package version is taken from the tag.

```bash
git tag v1.2.3
git push origin v1.2.3
```

Manual upload: `python -m build && python -m twine upload dist/*`.
