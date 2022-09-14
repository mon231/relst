from relst.server import RelstTextualServer


SERVER_PORT = 1736


class EchoMethodName:
    def nissim(self):
        return 'nissim'

    def malka(self):
        return 'malka'

    async def anissim(self):
        return 'anissim'

    async def amalka(self):
        return 'amalka'

    @staticmethod
    def snissim():
        return 'snissim'

    @staticmethod
    def smalka():
        return 'smalka'

    @staticmethod
    async def asnissim():
        return 'asnissim'

    @staticmethod
    async def asmalka():
        return 'asmalkas'

    def echo(self, prefix: str, text: str) -> str:
        return prefix + text


def main():
    request_handler = EchoMethodName()
    server = RelstTextualServer(SERVER_PORT, request_handler)
    server.serve()


if __name__ == "__main__":
    main()
