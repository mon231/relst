"""Prints the same request in every protocol, no server needed"""

from relst.protocol import CODECS


METHOD = 'echo'
ARGUMENTS = {'prefix': 'pre', 'text': 'txt', 'count': 3, 'flag': True, 'blob': b'\x00\x01'}


def main():
    for name, codec in CODECS.items():
        # over http the method is the url, binary frames can drop it
        payload = codec.encode_request(METHOD, ARGUMENTS, embed_method=False)

        print(f'== {name}: {len(payload)} bytes ({codec.content_type})')
        print(payload.hex(' ') if codec.is_binary else payload.decode())
        print()

    binary = CODECS['binary']
    print('== binary frames')
    print('request  ', binary.encode_request(METHOD, ARGUMENTS).hex(' '))
    print('response ', binary.encode_response('abc').hex(' '))
    print('error    ', binary.encode_error(404, 'Method x does not exist').hex(' '))


if __name__ == "__main__":
    main()
