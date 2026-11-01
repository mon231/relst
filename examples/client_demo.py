"""Talks to server_demo.py in every protocol"""

from relst.client import RelstFlaskClient, RelstSocketClient
from relst.protocol import RelstRemoteError


ADDRESS = '127.0.0.1'
HTTP_PORT = 1736
TCP_PORT = 1737


def exercise(client, title: str):
    print(f'--- {title}')
    print('echo     ', client.echo(prefix='pre', text='txt'))
    print('add      ', client.add(1), client.add(1, b=2))
    print('mirror   ', client.mirror({'x': 1, 'y': 2}))
    print('sensor   ', client.sensor())
    print('checksum ', client.checksum(b'\x01\x02\xff'))
    print('length   ', client.get_length('שלום'))

    try:
        client.fail()
    except RelstRemoteError as err:
        print('fail     ', err.code, err.message)

    try:
        client.add()
    except RelstRemoteError as err:
        print('bad call ', err.code, err.message)


def main():
    for protocol in ('json', 'xml', 'binary'):
        # `with` fetches the server's method list, every method becomes a python method
        with RelstFlaskClient(ADDRESS, HTTP_PORT, protocol=protocol) as client:
            exercise(client, f'http / {protocol}')

    with RelstSocketClient(ADDRESS, TCP_PORT) as client:
        exercise(client, 'tcp / binary')

        print('--- introspection')
        print('class    ', client.CLASS_NAME())
        print('help     ', client.CLASS_HELP().splitlines()[0])
        print('add help ', client.METHOD_HELP('add'))


if __name__ == "__main__":
    main()
