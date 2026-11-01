import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from relst.client import RelstFlaskClient, RelstSocketClient
from relst.server import RelstBinaryServer, RelstTextualServer
from tests.conftest import Handler
from tests.test_codecs import STRATEGIES, canon


@pytest.fixture(scope='module')
def servers():
    with RelstTextualServer(0, Handler()) as http_server, RelstBinaryServer(0, Handler()) as tcp_server:
        yield http_server, tcp_server


@pytest.fixture(scope='module')
def clients(servers):
    http_server, tcp_server = servers
    clients = {protocol: RelstFlaskClient('127.0.0.1', http_server.port, protocol=protocol) for protocol in ('json', 'xml', 'binary')}
    clients['tcp'] = RelstSocketClient('127.0.0.1', tcp_server.port)

    for client in clients.values():
        client.UPDATE_METHODS()

    yield clients

    for client in clients.values():
        client.close()


@pytest.mark.parametrize('transport', ['json', 'xml', 'binary', 'tcp'])
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_identity_through_the_whole_stack(clients, transport, data):
    """client -> codec -> http/tcp -> server -> handler -> codec -> client keeps every value"""

    strategy = STRATEGIES['json' if transport == 'json' else 'binary' if transport == 'tcp' else transport]
    value = data.draw(strategy)

    assert canon(clients[transport]._handle_request('identity', value=value)) == canon(value)


@pytest.mark.parametrize('transport', ['json', 'xml', 'binary', 'tcp'])
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(first=st.integers(-2 ** 62, 2 ** 62), second=st.integers(-2 ** 62, 2 ** 62))
def test_arithmetic_through_the_whole_stack(clients, transport, first, second):
    assert clients[transport].add(first, second) == first + second
