# relst examples

```bash
pip install relst           # or, from a checkout: pip install -e .
```

| file | what it shows |
|---|---|
| [`server_demo.py`](server_demo.py) | one handler object served over http (`:1736`, json/xml/binary + console) and raw tcp (`:1737`, binary) |
| [`client_demo.py`](client_demo.py) | the same calls through every protocol and both client classes, error handling, introspection |
| [`wire_formats.py`](wire_formats.py) | prints one request as json, xml and binary bytes (no server needed) |

## Run the demo

Terminal 1:

```bash
python examples/server_demo.py
```

Terminal 2:

```bash
python examples/client_demo.py
```

Every call is repeated over `http/json`, `http/xml`, `http/binary` and `tcp/binary`, and gives the
same results.

## Try the console

With the server running open <http://127.0.0.1:1736/_relst/ui>.

1. Expand **mirror**, enter `{"x": 1, "y": 2}` as `point`, choose `binary`, press **Generate request**:
   the raw request appears as hex. Change a byte, press **Send raw** and read the reply (or the `400`).
2. Switch the protocol to `xml` and generate again to see the same call as xml.
3. Open **Traces** to see every request, including the ones `client_demo.py` made, with raw
   request/response bodies.

## Talking to the server without the client

json (the default, so plain `curl` works):

```bash
curl -X POST http://127.0.0.1:1736/add -H "Content-Type: application/json" -d '{"a": 1, "b": 2}'
# 3

curl http://127.0.0.1:1736/get_random_value
curl -X POST http://127.0.0.1:1736/echo -H "Content-Type: application/json" -d '{"prefix": "a", "text": "b"}'
```

xml:

```bash
curl -X POST http://127.0.0.1:1736/add -H "Content-Type: application/xml" \
     -d '<request><arg name="a"><value type="int">1</value></arg></request>'
# <?xml ...?><response><value type="int">11</value></response>
```

Ask for a different response format with `Accept`:

```bash
curl -X POST http://127.0.0.1:1736/add -d '{"a": 1}' -H "Accept: application/xml"
```

introspection (built in, works in every protocol):

```bash
curl http://127.0.0.1:1736/__get_methods_list
curl http://127.0.0.1:1736/__get_class_help
```

## Recipes

**Expose a class with a firstclass struct**

```py
from firstclass import firstclass, uint16_t

@firstclass
class Point:
    x: uint16_t
    y: uint16_t

class Geometry:
    def mirror(self, point: Point) -> Point:      # dict in, dict out for the client
        return Point(point.y, point.x)
```

Out-of-range values (`x=70000`) are refused with a `400` before the method runs.

**Pick a free port / run in the background (tests, notebooks)**

```py
with RelstTextualServer(0, handler) as server:
    client = RelstFlaskClient('127.0.0.1', server.port, protocol='xml')
    ...
```

**Change the server's methods while it runs**

```py
handler.new_method = lambda: 'hi'
client.UPDATE_SERVER()      # server re-scans its handler
client.UPDATE_METHODS()     # client re-reads the list
client.new_method()         # 'hi'
```

**Handle errors**

```py
from relst.protocol import RelstRemoteError

try:
    client.fail()
except RelstRemoteError as err:
    print(err.code, err.message)     # 500 Server error handling request
```

**Look at the traces from code**

```py
server = RelstTextualServer(1736, handler)
server.start()
...
for entry in server.traces.entries():
    print(entry['protocol'], entry['method'], entry['status'], entry['duration_ms'])
```
