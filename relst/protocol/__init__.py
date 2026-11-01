from .codec import Codec
from .json_codec import JsonCodec
from .xml_codec import XmlCodec
from .binary_codec import BinaryCodec, Frame, FrameHeader, FrameKind, ValueTag, FRAME_HEADER_SIZE
from .errors import RelstProtocolError, RelstRemoteError
from .values import to_plain


CODECS = {codec.name: codec for codec in (JsonCodec(), XmlCodec(), BinaryCodec())}
DEFAULT_PROTOCOL = 'json'


def get_codec(protocol: str) -> Codec:
    try:
        return CODECS[protocol.lower()]
    except (KeyError, AttributeError):
        raise RelstProtocolError(f'unknown protocol {protocol!r}, expected one of {sorted(CODECS)}') from None


def codec_from_content_type(content_type) -> Codec:
    """
    :brief: picks codec by http Content-Type (parameters like charset are ignored)
    :except: RelstProtocolError for unsupported types
    """

    media_type = (content_type or '').split(';')[0].strip().lower()

    if not media_type:
        return CODECS[DEFAULT_PROTOCOL]

    for codec in CODECS.values():
        if media_type == codec.content_type:
            return codec

    if media_type in ('text/xml', 'text/json'):
        return CODECS['xml' if media_type == 'text/xml' else 'json']

    raise RelstProtocolError(f'unsupported content-type {media_type!r}')
