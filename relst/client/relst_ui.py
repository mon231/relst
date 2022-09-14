import eel
from argparse import ArgumentParser
from relst_flask_client import RelstFlaskClient


def main(args):
    client = RelstFlaskClient(args.server_address, args.server_port)

    @eel.expose
    def handle_request(function_name, **function_args):
        return client.handle_request(function_name, **function_args)

    eel.init("frontend")
    eel.start()


if __name__ == "__main__":
    args_parser = ArgumentParser("GUI-Client for relst-api server")
    args_parser.add_argument("server_address", type=str, help='name or ip of relst-api server')
    args_parser.add_argument("server_port", type=int, help='port of relst-api server')

    main(args_parser.parse_args())
