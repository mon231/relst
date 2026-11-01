import socket
import threading
import socketserver
from typing import Type
from .relst_server import RelstServer
from ..protocol import CODECS, Frame, RelstProtocolError


MAX_FRAME_BYTES = 1024 * 1024
SOCKET_TIMEOUT_SECONDS = 30


class RelstBinaryServer(RelstServer):
    """
    Relst over raw sockets: a stream of binary frames (see protocol/binary_codec.py),
    each request frame is answered by one response / error frame. Connections may be reused.
    """

    def __init__(self, server_port: int, request_handler, host: str = '127.0.0.1',
                 server_type: Type[socketserver.TCPServer] = socketserver.ThreadingTCPServer, trace_limit: int = 500):
        super().__init__(server_port, request_handler, trace_limit)

        self._host = host
        self.__server_type = server_type
        self.__socket_server = None
        self.__connections = set()
        self.__connections_lock = threading.Lock()

    def _bind(self):
        relst_server = self

        class FrameHandler(socketserver.StreamRequestHandler):
            timeout = SOCKET_TIMEOUT_SECONDS

            def handle(self):
                relst_server._track_connection(self.request, True)

                try:
                    relst_server._serve_connection(self.rfile, self.wfile)
                finally:
                    relst_server._track_connection(self.request, False)

        # NOTE: subclass instead of patching the (shared) stdlib class
        server_type = type('RelstSocketServer', (self.__server_type,), {'allow_reuse_address': True, 'daemon_threads': True})
        self.__socket_server = server_type((self._host, self._server_port), FrameHandler)
        self._server_port = self.__socket_server.server_address[1]

    def _run(self):
        self.__socket_server.serve_forever(poll_interval=0.05)

    def _close(self):
        if self.__socket_server:
            self.__socket_server.shutdown()
            self.__socket_server.server_close()
            self.__socket_server = None

        # NOTE: idle keep-alive connections would otherwise outlive the server
        with self.__connections_lock:
            open_connections = list(self.__connections)

        for connection in open_connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _track_connection(self, connection: socket.socket, is_open: bool):
        with self.__connections_lock:
            (self.__connections.add if is_open else self.__connections.discard)(connection)

    def _serve_connection(self, reader, writer):
        codec = CODECS['binary']

        def read_exact(size: int) -> bytes:
            data = reader.read(size)

            if len(data) != size:
                raise RelstProtocolError('connection closed in the middle of a frame')

            return data

        try:
            while first_byte := reader.read(1):
                pending = [first_byte]

                def read_next(size: int) -> bytes:
                    return pending.pop() + read_exact(size - 1) if pending else read_exact(size)

                # NOTE: oversized frames are refused by their header, before their body is read
                _, raw_frame = Frame.read(read_next, MAX_FRAME_BYTES)
                _, response = self.handle(codec, None, raw_frame, 'tcp')
                writer.write(response)
                writer.flush()
        except RelstProtocolError as err:
            # NOTE: stream is desynchronized, report and drop the connection
            self.__try_write(writer, codec.encode_error(400, str(err)))
        except (OSError, TimeoutError):
            pass

    @staticmethod
    def __try_write(writer, data: bytes):
        try:
            writer.write(data)
            writer.flush()
        except OSError:
            pass
