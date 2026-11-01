import json
import pytest
import requests
from relst.client import RelstFlaskClient
from relst.protocol import CODECS
from relst.server import RelstTextualServer, TraceLog
from relst.server.tracing import MAX_STORED_BODY


def post_try(base_url, **spec):
    response = requests.post(f'{base_url}/_relst/try', json=spec)
    return response.json()


def test_ui_page_is_served(base_url):
    response = requests.get(f'{base_url}/_relst/ui')
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/html')
    assert 'Relst Console' in response.text


def test_ui_can_be_disabled(handler):
    with RelstTextualServer(0, handler, enable_ui=False) as server:
        assert requests.get(f'http://127.0.0.1:{server.port}/_relst/ui').status_code == 404


def test_info_describes_the_api(base_url):
    info = requests.get(f'{base_url}/_relst/info').json()

    assert info['name'] == 'Handler' and info['help'].startswith('Test handler')
    assert set(info['protocols']) == {'json', 'xml', 'binary'}
    assert 'echo' in info['methods'] and '_private' not in info['methods']


def test_info_does_not_pollute_traces(http_server, base_url):
    requests.get(f'{base_url}/_relst/info')
    assert http_server.traces.entries() == []


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
def test_try_generates_requests_without_sending(http_server, base_url, protocol):
    result = post_try(base_url, method='echo', protocol=protocol, args={'prefix': 'a', 'text': 'b'}, send=False)

    assert 'status' not in result and result['binary'] == (protocol == 'binary')
    assert http_server.traces.entries() == []

    raw = bytes.fromhex(result['request']) if result['binary'] else result['request'].encode()
    assert CODECS[protocol].decode_request(raw)[1] == {'prefix': 'a', 'text': 'b'}


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
def test_try_sends_and_decodes(base_url, protocol):
    result = post_try(base_url, method='echo', protocol=protocol, args={'prefix': 'a', 'text': 'b'})

    assert result['status'] == 200 and result['decoded'] == 'ab'


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
def test_generated_request_can_be_edited_and_resent(base_url, protocol):
    generated = post_try(base_url, method='add', protocol=protocol, args={'a': 1, 'b': 2}, send=False)
    raw_encoding = 'hex' if generated['binary'] else 'text'

    original = post_try(base_url, method='add', protocol=protocol, raw=generated['request'], raw_encoding=raw_encoding)
    assert original['decoded'] == 3

    edited_args = {'a': 40, 'b': 2}
    edited = post_try(base_url, method='add', protocol=protocol, args=edited_args, send=False)
    assert post_try(base_url, method='add', protocol=protocol, raw=edited['request'], raw_encoding=raw_encoding)['decoded'] == 42


def test_try_raw_with_broken_payloads_reports_errors(base_url):
    result = post_try(base_url, method='add', protocol='json', raw='{nope')
    assert result['status'] == 400 and result['decoded']['error']['code'] == 400

    result = post_try(base_url, method='add', protocol='binary', raw='deadbeef', raw_encoding='hex')
    assert result['status'] == 400

    assert 'error' in post_try(base_url, method='add', protocol='binary', raw='zz', raw_encoding='hex')


def test_try_reports_bad_specs_without_crashing(base_url):
    assert 'error' in post_try(base_url, protocol='json')
    assert 'error' in post_try(base_url, method='echo', protocol='yaml')
    assert 'error' in post_try(base_url, method='echo', args=[1])
    assert 'error' in post_try(base_url, method='echo', raw=5)
    assert requests.post(f'{base_url}/_relst/try', json=[1, 2]).json()['error']
    assert requests.post(f'{base_url}/_relst/try', data='not json', headers={'Content-Type': 'application/json'}).json()['error']


def test_try_unknown_method_and_server_error(base_url):
    assert post_try(base_url, method='nope', protocol='json', args={})['status'] == 404

    result = post_try(base_url, method='raising', protocol='xml', args={})
    assert result['status'] == 500 and 'SECRET' not in result['response']


def test_try_endpoint_refuses_cross_site_style_posts(base_url, http_server):
    # a browser page can only send these without a cors preflight
    for content_type in ('text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data; boundary=x'):
        response = requests.post(f'{base_url}/_relst/try', data=json.dumps({'method': 'counter'}), headers={'Content-Type': content_type})
        assert response.status_code == 415

    assert http_server.traces.entries() == []


def test_traces_capture_real_traffic_of_all_protocols(http_server):
    for protocol in ('json', 'xml', 'binary'):
        with RelstFlaskClient('127.0.0.1', http_server.port, protocol=protocol) as client:
            client.echo('a', 'b')

    entries = [entry for entry in http_server.traces.entries() if entry['method'] == 'echo']
    assert [(entry['protocol'], entry['method'], entry['status'], entry['transport']) for entry in entries] == [
        ('json', 'echo', 200, 'http'), ('xml', 'echo', 200, 'http'), ('binary', 'echo', 200, 'http'),
    ]
    assert '"prefix"' in entries[0]['request']['text'] and '"ab"' in entries[0]['response']['text']
    assert '<arg name="prefix">' in entries[1]['request']['text']
    assert entries[2]['request']['text'].startswith('524c5354')
    assert all(entry['duration_ms'] >= 0 for entry in entries)


def test_traces_record_failures_and_conversions(http_server, base_url):
    requests.post(f'{base_url}/nope', json={})
    requests.post(f'{base_url}/add', json={'a': 1}, headers={'Accept': 'application/xml'})

    statuses = [(entry['method'], entry['status'], entry['protocol']) for entry in http_server.traces.entries()]
    assert statuses == [('nope', 404, 'json'), ('add', 200, 'json->xml')]


def test_traces_endpoint_pagination_and_clear(http_server, base_url):
    for number in range(5):
        requests.post(f'{base_url}/add', json={'a': number})

    entries = requests.get(f'{base_url}/_relst/traces').json()
    assert [entry['id'] for entry in entries] == [1, 2, 3, 4, 5]
    assert [entry['id'] for entry in requests.get(f'{base_url}/_relst/traces', params={'after': 3}).json()] == [4, 5]
    assert requests.get(f'{base_url}/_relst/traces', params={'after': 'junk'}).json() == entries

    assert requests.delete(f'{base_url}/_relst/traces').json() == {'cleared': True}
    assert requests.get(f'{base_url}/_relst/traces').json() == []

    requests.post(f'{base_url}/add', json={'a': 1})
    assert requests.get(f'{base_url}/_relst/traces').json()[0]['id'] == 6


def test_trace_ring_buffer_drops_oldest(handler):
    with RelstTextualServer(0, handler, trace_limit=3) as server:
        for number in range(10):
            requests.post(f'http://127.0.0.1:{server.port}/add', json={'a': number})

        assert [entry['id'] for entry in server.traces.entries()] == [8, 9, 10]


def test_trace_bodies_are_truncated(http_server, base_url):
    requests.post(f'{base_url}/identity', json={'value': 'x' * (MAX_STORED_BODY * 3)})
    entry = http_server.traces.entries()[0]

    assert entry['request']['truncated'] and len(entry['request']['text']) == MAX_STORED_BODY
    assert entry['request']['size'] > MAX_STORED_BODY


def test_trace_log_is_thread_safe():
    from concurrent.futures import ThreadPoolExecutor
    log = TraceLog(limit=100000)

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(lambda number: log.record(n=number), range(5000)))

    assert sorted(entry['id'] for entry in log.entries()) == list(range(1, 5001))


def test_binary_traces_are_hex_text_traces_are_utf8(http_server, base_url):
    requests.post(f'{base_url}/identity', json={'value': 'שלום'})
    assert '"\\u05e9' in http_server.traces.entries()[0]['request']['text'] or 'ש' in http_server.traces.entries()[0]['request']['text']
