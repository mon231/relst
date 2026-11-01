import socket
import struct
import time
import pytest
from concurrent.futures import ThreadPoolExecutor
from relst.client import RelstSocketClient
from relst.protocol import BinaryCodec, Frame, FrameKind, RelstRemoteError
from relst.protocol.binary_codec import decode_value, encode_value, encode_varint
from relst.server import RelstBinaryServer
from relst.server.binary_server import MAX_FRAME_BYTES


CODEC = BinaryCodec()


def connect(server) -> socket.socket:
    return socket.create_connection(('127.0.0.1', server.port), timeout=5)


def read_frame(connection: socket.socket) -> Frame:
    def read(size):
        data = b''
        while len(data) < size:
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise EOFError
            data += chunk
        return data

    return Frame.read(read)[0]


def test_client_calls(tcp_client):
    assert tcp_client.echo('a', 'b') == 'ab'
    assert tcp_client.async_echo('x') == 'x'
    assert tcp_client.static_double(4) == 8
    assert tcp_client.identity({'k': [b'\x00', None, 2 ** 70]}) == {'k': [b'\x00', None, 2 ** 70]}
    assert tcp_client.swap({'x': 1, 'y': 2}) == {'x': 2, 'y': 1}
    assert tcp_client.CLASS_NAME() == 'Handler'


def test_errors_keep_the_connection_usable(tcp_client):
    with pytest.raises(RelstRemoteError) as caught:
        tcp_client.raising()

    assert caught.value.code == 500 and 'SECRET' not in caught.value.message

    with pytest.raises(RelstRemoteError) as caught:
        tcp_client._handle_request('nope')

    assert caught.value.code == 404

    with pytest.raises(RelstRemoteError) as caught:
        tcp_client._handle_request('echo', prefix='only')

    assert caught.value.code == 400
    assert tcp_client.echo('still', 'works') == 'stillworks'


def test_pipelined_requests_get_ordered_responses(tcp_server):
    with connect(tcp_server) as connection:
        connection.sendall(b''.join(CODEC.encode_request('add', {'a': number}) for number in range(50)))
        results = [decode_value(read_frame(connection).payload) for _ in range(50)]

    assert results == [number + 10 for number in range(50)]


def test_request_split_into_single_bytes(tcp_server):
    request = CODEC.encode_request('echo', {'prefix': 'a', 'text': 'b'})

    with connect(tcp_server) as connection:
        for index in range(len(request)):
            connection.sendall(request[index:index + 1])

        assert decode_value(read_frame(connection).payload) == 'ab'


def test_garbage_gets_error_frame_then_disconnect(tcp_server):
    with connect(tcp_server) as connection:
        connection.sendall(b'GET / HTTP/1.1\r\nHost: x\r\n\r\n')
        frame = read_frame(connection)
        assert frame.kind == FrameKind.ERROR
        assert decode_value(frame.payload)[0] == 400

        with pytest.raises(EOFError):
            read_frame(connection)


def test_oversized_frame_is_refused_without_reading_body(tcp_server):
    header = Frame(FrameKind.REQUEST, 'echo', b'').to_bytes()[:-1] + encode_varint(MAX_FRAME_BYTES + 1)

    with connect(tcp_server) as connection:
        connection.sendall(header)
        frame = read_frame(connection)

    assert frame.kind == FrameKind.ERROR and 'exceeds limit' in decode_value(frame.payload)[1]


def test_truncated_frame_then_close_does_not_hurt_server(tcp_server):
    request = CODEC.encode_request('echo', {'prefix': 'a', 'text': 'b'})

    for cut in (1, 2, 5, len(request) - 1):
        connection = connect(tcp_server)
        connection.sendall(request[:cut])
        connection.shutdown(socket.SHUT_WR)
        connection.close()

    with connect(tcp_server) as connection:
        connection.sendall(request)
        assert decode_value(read_frame(connection).payload) == 'ab'


def test_valid_frame_with_bad_payload_keeps_connection(tcp_server):
    bad_payload = Frame(FrameKind.REQUEST, 'echo', b'\xee\xee').to_bytes()
    good = CODEC.encode_request('echo', {'prefix': 'a', 'text': 'b'})

    with connect(tcp_server) as connection:
        connection.sendall(bad_payload + good)
        assert read_frame(connection).kind == FrameKind.ERROR
        assert read_frame(connection).kind == FrameKind.RESPONSE


def test_frame_without_method_name(tcp_server):
    with connect(tcp_server) as connection:
        connection.sendall(Frame(FrameKind.REQUEST, '', encode_value({'a': 1})).to_bytes())
        frame = read_frame(connection)

    assert frame.kind == FrameKind.ERROR and decode_value(frame.payload)[0] == 400


def test_response_frame_sent_as_request_is_rejected(tcp_server):
    with connect(tcp_server) as connection:
        connection.sendall(Frame(FrameKind.RESPONSE, 'echo', encode_value({})).to_bytes())
        assert read_frame(connection).kind == FrameKind.ERROR


def test_many_connections_in_parallel(tcp_server):
    def worker(index):
        with RelstSocketClient('127.0.0.1', tcp_server.port) as client:
            return [client.add(index, call) for call in range(25)]

    with ThreadPoolExecutor(20) as pool:
        results = list(pool.map(worker, range(40)))

    assert results == [[index + call for call in range(25)] for index in range(40)]


def test_client_shared_between_threads(tcp_client):
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda number: tcp_client.static_double(number), range(200)))

    assert results == [number * 2 for number in range(200)]


def test_client_reconnects_after_server_restart(handler):
    server = RelstBinaryServer(0, handler).start()
    port = server.port
    client = RelstSocketClient('127.0.0.1', port)
    assert client.echo if hasattr(client, 'echo') else True
    assert client._handle_request('echo', prefix='a', text='b') == 'ab'
    server.stop()

    with pytest.raises(OSError):
        client._handle_request('echo', prefix='a', text='b')

    restarted = RelstBinaryServer(port, handler).start()

    try:
        assert client._handle_request('echo', prefix='a', text='b') == 'ab'
    finally:
        client.close()
        restarted.stop()


def test_traces_record_tcp_calls(tcp_server, tcp_client):
    tcp_client.echo('a', 'b')
    entry = tcp_server.traces.entries()[-1]

    assert (entry['transport'], entry['protocol'], entry['method'], entry['status']) == ('tcp', 'binary', 'echo', 200)
    assert entry['request']['text'].startswith('04')


def test_server_stop_releases_the_port(handler):
    server = RelstBinaryServer(0, handler).start()
    port = server.port
    server.stop()

    probe = socket.socket()
    probe.bind(('127.0.0.1', port))
    probe.close()
