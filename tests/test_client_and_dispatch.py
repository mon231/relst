import types
import pytest
import requests
from relst.client import RelstFlaskClient, RelstSocketClient
from relst.protocol import CODECS, RelstProtocolError, RelstRemoteError
from relst.server import RelstBinaryServer, RelstRequestError, RelstTextualServer


def make_server(handler):
    # NOTE: never bound, only the request pipeline is used
    return RelstTextualServer(0, handler)


def call(server, method, protocol='json', **kwargs):
    codec = CODECS[protocol]
    status, response = server.handle(codec, method, codec.encode_request(method, kwargs, embed_method=False), 'test')

    try:
        return status, codec.decode_response(response, status)
    except RelstRemoteError as err:
        return status, err


# ---------------------------------------------------------------- handler discovery

def test_properties_are_never_evaluated_or_exposed():
    class Handler:
        evaluated = 0

        @property
        def expensive(self):
            Handler.evaluated += 1
            raise RuntimeError('boom')

        @property
        def callable_property(self):
            return lambda: 'x'

        def real(self):
            return 'real'

    server = make_server(Handler())

    assert Handler.evaluated == 0
    assert call(server, 'real') == (200, 'real')
    assert call(server, 'expensive')[0] == 404 and call(server, 'callable_property')[0] == 404


def test_namespace_and_module_like_handlers():
    server = make_server(types.SimpleNamespace(double=lambda x: x * 2, value=5))

    assert call(server, 'double', x=4) == (200, 8)
    assert call(server, 'value')[0] == 404


def test_attributes_that_are_not_routines_are_skipped():
    class Handler:
        number = 5
        nested_class = dict
        text = 'abc'

        def ok(self):
            return 1

    server = make_server(Handler())
    assert sorted(server.dispatch('__get_methods_list', {})) == ['ok']


def test_builtin_callable_objects_as_handlers():
    server = make_server([])
    assert 'append' in server.dispatch('__get_methods_list', {})
    assert call(server, 'append', object=1)[0] == 400


def test_alias_names_are_the_attribute_names():
    class Handler:
        def original(self):
            return 'x'

        alias = original

    server = make_server(Handler())
    assert call(server, 'alias') == (200, 'x') and call(server, 'original') == (200, 'x')


# ---------------------------------------------------------------- argument binding

def test_variadic_and_special_signatures():
    class Handler:
        def kwargs_only(self, **kwargs):
            return kwargs

        def with_star(self, *args):
            return list(args)

        def positional_only(self, a, /):
            return a

        def keyword_only(self, *, a):
            return a

        def default_none(self, a=None):
            return a

    server = make_server(Handler())

    assert call(server, 'kwargs_only', x=1, y=[2]) == (200, {'x': 1, 'y': [2]})
    assert call(server, 'with_star') == (200, [])
    assert call(server, 'positional_only', a=1)[0] == 400
    assert call(server, 'keyword_only', a=7) == (200, 7)
    assert call(server, 'default_none') == (200, None)


def test_argument_name_that_collides_with_internals():
    class Handler:
        def method(self, method_name, kwargs, self_=1):
            return [method_name, kwargs]

    server = make_server(Handler())
    assert call(server, 'method', method_name='a', kwargs='b') == (200, ['a', 'b'])


def test_bad_hex_for_bytes_parameter_is_400():
    class Handler:
        def size(self, data: bytes):
            return len(data)

    server = make_server(Handler())
    assert call(server, 'size', data='zz')[0] == 400
    assert call(server, 'size', data='0aff') == (200, 2)
    assert call(server, 'size', data=b'abc') == (200, 3)


def test_float_annotation_accepts_ints_but_not_bools_or_strings():
    class Handler:
        def typed(self, value: float):
            return repr(value)

    server = make_server(Handler())
    assert call(server, 'typed', value=3) == (200, '3.0')
    assert call(server, 'typed', value=True) == (200, 'True')


def test_dataclass_annotated_parameter():
    from tests.test_values import Inner

    class Handler:
        def numbers(self, inner: Inner):
            return inner.numbers

    server = make_server(Handler())
    assert call(server, 'numbers', inner={'numbers': [5]}) == (200, [5])
    assert call(server, 'numbers', inner={'wrong': 1})[0] == 400


def test_handler_raising_request_error_keeps_its_code():
    class Handler:
        def forbidden(self):
            raise RelstRequestError(403, 'nope')

    status, error = call(make_server(Handler()), 'forbidden')
    assert status == 403 and error.message == 'nope'


def test_handler_returning_unserializable_object_becomes_string():
    class Handler:
        def weird(self):
            return object()

    status, value = call(make_server(Handler()), 'weird')
    assert status == 200 and value.startswith('<object object')


def test_handler_returning_cyclic_structure_is_500_not_crash():
    class Handler:
        def cycle(self):
            data = []
            data.append(data)
            return data

        def fine(self):
            return 1

    server = make_server(Handler())
    assert call(server, 'cycle')[0] in (400, 500)
    assert call(server, 'fine') == (200, 1)


def test_async_method_raising_is_500():
    class Handler:
        async def broken(self):
            raise ValueError('x')

    assert call(make_server(Handler()), 'broken')[0] == 500


def test_async_methods_running_concurrently_in_threads(http_client):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as pool:
        assert list(pool.map(lambda number: http_client.async_echo(str(number)), range(40))) == [str(number) for number in range(40)]


def test_dispatch_is_usable_without_a_transport():
    server = make_server(types.SimpleNamespace(f=lambda: 1))

    assert server.dispatch('f', {}) == 1

    with pytest.raises(RelstRequestError) as caught:
        server.dispatch('missing', {})

    assert caught.value.code == 404


def test_method_name_edge_cases():
    server = make_server(types.SimpleNamespace(ok=lambda: 1))

    for name in ('', ' ', 'ok ', 'OK', '../ok', 'ok/', 'o\x00k', 'ok' * 10_000):
        assert call(server, name)[0] in (400, 404)


# ---------------------------------------------------------------- clients

def test_positional_arguments_are_mapped_by_signature(http_client):
    assert http_client.add(5, 6) == 11

    with pytest.raises(TypeError):
        http_client.add(1, 2, 3)

    with pytest.raises(TypeError):
        http_client.add(1, a=1)


def test_dynamic_methods_carry_name_and_doc(http_client):
    assert http_client.echo.__name__ == 'echo'
    assert http_client.echo.__doc__ == 'Concatenates'


def test_methods_are_removed_when_server_drops_them(handler, http_server):
    with RelstFlaskClient('127.0.0.1', http_server.port) as client:
        assert hasattr(client, 'echo')

        handler.__class__ = type('Smaller', (), {'only': lambda self: 1})
        client.UPDATE_SERVER()
        client.UPDATE_METHODS()

        assert hasattr(client, 'only') and not hasattr(client, 'echo')


def test_methods_are_not_available_before_update(http_server):
    client = RelstFlaskClient('127.0.0.1', http_server.port)
    assert not hasattr(client, 'echo')
    client.UPDATE_METHODS()
    assert client.echo('a', 'b') == 'ab'
    client.close()


def test_private_server_names_never_become_client_methods(handler, http_server):
    handler.__class__ = type('Evil', (), {'__get_methods_list': lambda self: 1, 'ok': lambda self: 1})

    with RelstFlaskClient('127.0.0.1', http_server.port) as client:
        client.UPDATE_SERVER()
        client.UPDATE_METHODS()
        assert hasattr(client, 'ok') and not hasattr(client, '__get_methods_list')


def test_unknown_protocol_is_rejected():
    with pytest.raises(RelstProtocolError):
        RelstFlaskClient('127.0.0.1', 1, protocol='yaml')


def test_connection_refused_surfaces_as_connection_error():
    with pytest.raises(requests.ConnectionError):
        RelstFlaskClient('127.0.0.1', 1, timeout=0.5)._handle_request('x')

    with pytest.raises(OSError):
        RelstSocketClient('127.0.0.1', 1, timeout=0.5)._handle_request('x')


def test_http_client_timeout(http_server):
    with RelstFlaskClient('127.0.0.1', http_server.port, timeout=0.2) as client:
        with pytest.raises(requests.Timeout):
            client._handle_request('slow', seconds=1.5)

        assert client.echo('a', 'b') == 'ab'


def test_socket_client_timeout_then_recovers(tcp_server):
    with RelstSocketClient('127.0.0.1', tcp_server.port, timeout=0.2) as client:
        with pytest.raises(OSError):
            client._handle_request('slow', seconds=1.5)

        assert client._handle_request('echo', prefix='a', text='b') == 'ab'


def test_http_binary_requests_do_not_repeat_the_method_name(http_server):
    with RelstFlaskClient('127.0.0.1', http_server.port, protocol='binary') as client:
        client.echo('a', 'b')

    entry = [entry for entry in http_server.traces.entries() if entry['method'] == 'echo'][-1]
    # header byte, empty name (size 0), payload size...
    assert entry['request']['text'].startswith('0400')


def test_socket_requests_carry_the_method_name(tcp_server, tcp_client):
    tcp_client.echo('a', 'b')
    assert tcp_server.traces.entries()[-1]['request']['text'].startswith('0404' + b'echo'.hex())


def test_clients_work_after_close_and_reuse(http_server):
    client = RelstFlaskClient('127.0.0.1', http_server.port)
    client.UPDATE_METHODS()
    client.close()
    assert client.echo('a', 'b') == 'ab'
    client.close()


def test_https_prefix_is_used():
    with pytest.raises(requests.exceptions.RequestException):
        RelstFlaskClient('127.0.0.1', 1, is_https=True, timeout=0.5)._handle_request('x')


def test_binary_server_with_custom_host_and_unbound_port_reuse(handler):
    first = RelstBinaryServer(0, handler).start()
    second = RelstBinaryServer(0, handler).start()

    try:
        assert first.port != second.port
        with RelstSocketClient('127.0.0.1', first.port) as one, RelstSocketClient('127.0.0.1', second.port) as two:
            assert one.echo('a', 'b') == two.echo('a', 'b') == 'ab'
    finally:
        first.stop()
        second.stop()


def test_stopping_twice_and_restarting_the_same_instance(handler):
    server = RelstTextualServer(0, handler)
    server.start()
    server.stop()
    server.stop()
    server.start()

    try:
        assert requests.get(f'http://127.0.0.1:{server.port}/counter').status_code == 200
    finally:
        server.stop()
