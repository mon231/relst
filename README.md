# Relst package


## Installation

clone the project:
```bash
git clone https://github.com/mon231/relst
```

install as a package:
```bash
pip install ./relst
```

## Usage

server side:
```py
import random
from relst.server import RelstTextualServer


class EchoMethodName:
    """
    This is the server's help string
    """

    def get_random_value(self):
        "This is the help string of this method"
        return random.choice(('m', 1, 5.5, False))

    @staticmethod
    def return_str_function() -> str:
        return 'function'

    @staticmethod
    async def get_length(string: str) -> int:
        return len(string)

    def _will_not_be_exposed():
        return 'MySecretCode'


request_handler = EchoMethodName()
server = RelstTextualServer(SERVER_PORT, request_handler)
server.serve()
```


## Protocols

`RelstTextualServer` speaks three wire formats over HTTP, chosen by the request `Content-Type`
(`Accept` may ask for a different response format):

| protocol | Content-Type | notes |
|---|---|---|
| json (default) | `application/json` | body is an object of keyword-arguments; bytes / nan / inf travel as `{"$bytes": hex}` / `{"$float": "nan"}` |
| xml | `application/xml` | `<request><arg name="a"><value type="int">1</value></arg></request>`; DTDs are rejected |
| binary | `application/octet-stream` | `RLST` frame (header defined with `firstclass`) + typed values |

`RelstBinaryServer` serves the same binary frames over raw TCP (reusable connections).

```py
from relst.client import RelstFlaskClient, RelstSocketClient

with RelstFlaskClient('127.0.0.1', 1736, protocol='xml') as client:   # json | xml | binary
    print(client.echo(prefix='a', text='b'))

with RelstSocketClient('127.0.0.1', 1737) as client:
    print(client.echo('a', 'b'))
```

Servers bind to `127.0.0.1` by default (pass `host='0.0.0.0'` to expose them) and can run in the
background: `with RelstTextualServer(0, handler) as server: server.port`.

## Console (swagger-like UI)

`RelstTextualServer` serves a console at `http://<host>:<port>/_relst/ui`: browse methods and
signatures, execute them in any protocol, generate the raw request (xml / json / hex), edit it and
send it raw, and watch a live trace of every request/response handled by the server.
Disable it with `enable_ui=False`. Raw trace data: `GET /_relst/traces?after=<id>`.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests
```
