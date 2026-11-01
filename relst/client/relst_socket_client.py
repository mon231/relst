import socket
import threading
from typing import Tuple
from .relst_client import RelstClient
from ..protocol import FRAME_HEADER_SIZE, Frame, RelstProtocolError


class RelstSocketClient(RelstClient):
    """Client of RelstBinaryServer, keeps one tcp connection (thread-safe, calls are serialized)"""

    def __init__(self, server_address: str, server_port: int, timeout: float = 30):
        super().__init__('binary')

        self.__address = (server_address, server_port)
        self.__timeout = timeout
        self.__socket = None
        self.__lock = threading.Lock()

    def _send(self, method_name: str, request: bytes) -> Tuple[int, bytes]:
        with self.__lock:
            try:
                connection = self.__connection()
                connection.sendall(request)

                header_bytes = self.__read(connection, FRAME_HEADER_SIZE)
                header = Frame.parse_header(header_bytes)
                body = self.__read(connection, header.name_length + header.payload_length)
            except (OSError, RelstProtocolError):
                self.__disconnect()
                raise

        # NOTE: binary frames carry their own kind, status is only informative
        return 200, header_bytes + body

    def close(self):
        with self.__lock:
            self.__disconnect()

    def __connection(self) -> socket.socket:
        if self.__socket is None:
            self.__socket = socket.create_connection(self.__address, timeout=self.__timeout)

        return self.__socket

    def __disconnect(self):
        if self.__socket is not None:
            self.__socket.close()
            self.__socket = None

    @staticmethod
    def __read(connection: socket.socket, size: int) -> bytes:
        chunks = []

        while size > 0:
            chunk = connection.recv(size)

            if not chunk:
                raise ConnectionError('server closed the connection')

            chunks.append(chunk)
            size -= len(chunk)

        return b''.join(chunks)
