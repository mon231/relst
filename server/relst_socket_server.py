import socketserver
from typing import Callable
from .relst_server import RelstServer


class RelstSocketServer(RelstServer):
    def __init__(self, server_port: int, server_type: socketserver.BaseServer, request_hanlder):
        super().__init__(server_port, request_hanlder)
        self.__server_type = server_type

    def serve(self):
        raise NotImplementedError("This method is currently unsupported for this type")

        socket_handler_class = None # TODO: implement socket-handler class
        with self.__server_type(('', self._server_port), socket_handler_class) as server:
            server.serve_forever()

    def _register_callable(self, callable: Callable, name: str):
        raise NotImplementedError("This method is currently unsupported for this type")
