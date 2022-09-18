from relst.client import RelstFlaskClient


SERVER_PORT = 1736
SERVER_ADDRESS = '127.0.0.1'


def main():
    client = RelstFlaskClient(SERVER_ADDRESS, SERVER_PORT)
    print(client._handle_request('asnissim'))
    print(client._handle_request('echo', prefix='pre', text='txt'))


if __name__ == "__main__":
    main()
