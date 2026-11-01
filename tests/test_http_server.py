import json
import time
import pytest
import requests
from concurrent.futures import ThreadPoolExecutor
from relst.client import RelstFlaskClient
from relst.protocol import RelstRemoteError, CODECS
from relst.server import RelstTextualServer
from tests.conftest import Handler, Point, PROTOCOLS


def test_every_method_kind_over_every_protocol(http_client):
    assert http_client.echo('a', 'b') == 'ab'
    assert http_client.echo(prefix='a', text='b') == 'ab'
    assert http_client.async_echo('x') == 'x'
    assert http_client.static_double(21) == 42
    assert http_client.class_name() == 'Handler'
    assert http_client.add(1) == 11
    assert http_client.add(1, b=2) == 3
    assert http_client.nothing() is None


def test_private_and_unknown_methods_are_not_exposed(http_client):
    assert not hasattr(http_client, '_private')

    for name in ('_private', '__init__', '__class__', 'nope', '__get_nothing'):
        with pytest.raises(RelstRemoteError) as caught:
            http_client._handle_request(name)

        assert caught.value.code == 404


def test_relst_introspection_methods(http_client):
    assert http_client.CLASS_NAME() == 'Handler'
    assert http_client.CLASS_HELP() == 'Test handler\nsecond line'
    assert http_client.METHOD_HELP('echo') == 'Concatenates'

    with pytest.raises(RelstRemoteError) as caught:
        http_client.METHOD_HELP('nope')

    assert caught.value.code == 404


def test_methods_list_describes_signatures(http_server):
    with RelstFlaskClient('127.0.0.1', http_server.port) as client:
        methods = client._handle_request('__get_methods_list')

    assert '_private' not in methods and '__get_methods_list' not in methods
    assert methods['add']['params'] == [
        {'name': 'a', 'type': 'int', 'kind': 'POSITIONAL_OR_KEYWORD'},
        {'name': 'b', 'type': 'int', 'kind': 'POSITIONAL_OR_KEYWORD', 'default': 10},
    ]
    assert methods['add']['return'] == 'int'
    assert methods['echo']['doc'] == 'Concatenates'
    assert methods['identity']['params'][0]['type'] == 'any'


def test_dynamic_methods_follow_server_updates(handler, http_server):
    with RelstFlaskClient('127.0.0.1', http_server.port) as client:
        assert not hasattr(client, 'brand_new')

        handler.brand_new = lambda: 'new'
        client.UPDATE_SERVER()
        client.UPDATE_METHODS()
        assert client.brand_new() == 'new'

        del handler.brand_new
        client.UPDATE_SERVER()
        client.UPDATE_METHODS()
        assert not hasattr(client, 'brand_new')
        assert client.echo('still', 'works') == 'stillworks'


def test_server_cannot_shadow_client_internals(handler, http_server):
    handler.UPDATE_METHODS = lambda: 'evil'
    handler.close = lambda: 'evil'
    http_server.dispatch('__update_server', {})

    with RelstFlaskClient('127.0.0.1', http_server.port) as client:
        assert client.UPDATE_METHODS() is None
        assert client.close() is None


def test_value_fidelity(http_client):
    for value in [None, True, False, 0, -1, 2 ** 100, 1.5, '', 'text שלום \U0001f600', [], {}, [1, [2, [3]]], {'a': {'b': [None]}}]:
        assert http_client.identity(value) == value


def test_bytes_nan_and_inf_survive_every_protocol(http_client):
    assert http_client.identity(b'\x00\xff\x10') == b'\x00\xff\x10'
    assert http_client.identity(float('inf')) == float('inf')
    assert http_client.length(b'123') == 3


def test_type_coercion_from_signature(http_client):
    assert http_client.halve(5) == 2.5
    assert http_client.swap({'x': 1, 'y': 2}) == {'x': 2, 'y': 1}
    assert http_client.tagged() == {'kind': 7, 'name': 'abc', 'origin': {'x': 1, 'y': 2}}
    assert http_client.color() == 2
    assert http_client.tuple_and_set() == [[1, 2], [3]]


def test_bad_values_for_firstclass_params_are_400(http_client):
    for bad in ({'x': 1}, {'x': 70000, 'y': 1}, {'x': 'a', 'y': 1}, {'x': 1, 'y': 2, 'z': 3}):
        with pytest.raises(RelstRemoteError) as caught:
            http_client.swap(bad)

        assert caught.value.code == 400


def test_argument_binding_errors_are_400(http_client):
    for kwargs in ({}, {'prefix': 'a'}, {'prefix': 'a', 'text': 'b', 'extra': 1}):
        with pytest.raises(RelstRemoteError) as caught:
            http_client._handle_request('echo', **kwargs)

        assert caught.value.code == 400


def test_handler_exceptions_do_not_leak_details(http_client):
    with pytest.raises(RelstRemoteError) as caught:
        http_client.raising()

    assert caught.value.code == 500
    assert 'SECRET' not in caught.value.message
    assert http_client.echo('still', 'alive') == 'stillalive'


@pytest.mark.parametrize('protocol', PROTOCOLS)
def test_raw_http_status_codes(base_url, protocol):
    codec = CODECS[protocol]
    headers = {'Content-Type': codec.content_type}

    ok = requests.post(f'{base_url}/echo', data=codec.encode_request('echo', {'prefix': 'a', 'text': 'b'}), headers=headers)
    assert ok.status_code == 200 and ok.headers['Content-Type'].startswith(codec.content_type)
    assert codec.decode_response(ok.content) == 'ab'

    assert requests.post(f'{base_url}/missing', data=codec.encode_request('missing', {}), headers=headers).status_code == 404
    assert requests.post(f'{base_url}/echo', data=b'\xff\xfe garbage', headers=headers).status_code == 400
    assert requests.post(f'{base_url}/echo', data=b'', headers=headers).status_code == 400


def test_method_name_mismatch_between_url_and_payload_is_rejected(base_url):
    for protocol in ('xml', 'binary'):
        codec = CODECS[protocol]
        response = requests.post(f'{base_url}/echo', data=codec.encode_request('add', {'a': 1}), headers={'Content-Type': codec.content_type})
        assert response.status_code == 400


def test_unsupported_content_type_is_415(base_url):
    response = requests.post(f'{base_url}/echo', data='x', headers={'Content-Type': 'text/html'})
    assert response.status_code == 415
    assert json.loads(response.content)['error']['code'] == 415


def test_oversized_body_is_413_and_server_survives(base_url):
    response = requests.post(f'{base_url}/echo', data=b'x' * (2 * 1024 * 1024), headers={'Content-Type': 'application/json'})
    assert response.status_code == 413
    assert requests.post(f'{base_url}/nothing', json={}).status_code == 200


def test_get_requests_work_without_body(base_url):
    response = requests.get(f'{base_url}/nothing')
    assert response.status_code == 200 and response.json() is None


def test_wrong_http_verbs_and_paths(base_url):
    assert requests.put(f'{base_url}/echo').status_code == 405
    assert requests.get(f'{base_url}/a/b/c').status_code == 404
    assert requests.get(f'{base_url}/').status_code == 404


def test_default_content_type_is_json_for_legacy_clients(base_url):
    response = requests.post(f'{base_url}/echo', data=json.dumps({'prefix': 'a', 'text': 'b'}))
    assert response.json() == 'ab'


def test_accept_header_converts_response_protocol(base_url):
    response = requests.post(f'{base_url}/add', json={'a': 1}, headers={'Accept': 'application/xml'})
    assert response.headers['Content-Type'].startswith('application/xml')
    assert CODECS['xml'].decode_response(response.content) == 11


def test_error_uses_requested_protocol(base_url):
    for protocol in ('xml', 'binary'):
        codec = CODECS[protocol]
        response = requests.post(f'{base_url}/missing', data=codec.encode_request('missing', {}), headers={'Content-Type': codec.content_type})

        with pytest.raises(RelstRemoteError):
            codec.decode_response(response.content, response.status_code)


def test_many_concurrent_clients(http_server):
    def worker(index):
        protocol = PROTOCOLS[index % 3]

        with RelstFlaskClient('127.0.0.1', http_server.port, protocol=protocol) as client:
            return [client.echo(str(index), str(call)) for call in range(20)]

    with ThreadPoolExecutor(16) as pool:
        results = list(pool.map(worker, range(48)))

    assert results == [[f'{index}{call}' for call in range(20)] for index in range(48)]


def test_slow_call_does_not_block_others(http_server):
    with ThreadPoolExecutor(2) as pool:
        with RelstFlaskClient('127.0.0.1', http_server.port) as slow_client, RelstFlaskClient('127.0.0.1', http_server.port) as fast_client:
            slow = pool.submit(slow_client._handle_request, 'slow', seconds=0.6)
            time.sleep(0.1)
            started = time.perf_counter()
            assert fast_client.echo('a', 'b') == 'ab'
            assert time.perf_counter() - started < 0.5
            assert slow.result() == 0.6


def test_large_payload_roundtrip(http_client):
    big = {'items': [{'n': index, 's': 'x' * 20} for index in range(5000)]}
    assert http_client.identity(big) == big


def test_server_lifecycle(handler):
    server = RelstTextualServer(0, handler).start()
    port = server.port
    assert port != 0
    assert requests.get(f'http://127.0.0.1:{port}/nothing').status_code == 200

    server.stop()

    with pytest.raises(requests.ConnectionError):
        requests.get(f'http://127.0.0.1:{port}/nothing', timeout=2)

    server.stop()


def test_server_binds_localhost_by_default(http_server):
    assert http_server._host == '127.0.0.1'
