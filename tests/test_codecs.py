import math
import pytest
from hypothesis import given, settings, strategies as st
from relst.protocol import (
    CODECS, BinaryCodec, JsonCodec, XmlCodec, RelstProtocolError, RelstRemoteError,
    codec_from_content_type, get_codec,
)
from relst.protocol.binary_codec import MAX_DEPTH, Frame, encode_value, decode_value


ANY_CHAR = st.characters(min_codepoint=0, max_codepoint=0x10ffff, exclude_categories=())
keys = st.one_of(st.text(ANY_CHAR, max_size=8), st.integers(-10 ** 12, 10 ** 12), st.binary(max_size=4))

leaves = st.one_of(
    st.none(), st.booleans(),
    st.integers(min_value=-2 ** 300, max_value=2 ** 300),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(ANY_CHAR, max_size=24), st.binary(max_size=24),
)


def values(dict_keys):
    return st.recursive(
        leaves,
        lambda children: st.one_of(
            st.lists(children, max_size=4),
            st.dictionaries(dict_keys, children, max_size=4),
        ),
        max_leaves=15,
    )


def canon(value):
    """equality that tells 1 / True / 1.0 apart and nan == nan"""
    if isinstance(value, float):
        return ('float', 'nan' if math.isnan(value) else repr(value))
    if isinstance(value, list):
        return ('list', [canon(element) for element in value])
    if isinstance(value, dict):
        return ('dict', sorted(((canon(k), canon(v)) for k, v in value.items()), key=repr))
    return (type(value).__name__, value)


TEXT_KEYS = st.text(ANY_CHAR, max_size=8)
STRATEGIES = {'json': values(TEXT_KEYS), 'xml': values(keys), 'binary': values(keys)}


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
@settings(max_examples=300, deadline=None)
@given(data=st.data())
def test_roundtrip_any_plain_value(protocol, data):
    codec = get_codec(protocol)
    value = data.draw(STRATEGIES[protocol])

    assert canon(codec.decode_response(codec.encode_response(value))) == canon(value)

    _, kwargs = codec.decode_request(codec.encode_request('m', {'arg': value}))
    assert canon(kwargs) == canon({'arg': value})


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
@given(garbage=st.binary(max_size=200))
@settings(max_examples=300, deadline=None)
def test_decoders_never_crash_on_garbage(protocol, garbage):
    codec = get_codec(protocol)

    for decode in (codec.decode_request, codec.decode_response):
        try:
            decode(garbage)
        except (RelstProtocolError, RelstRemoteError):
            pass


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
@given(data=st.data())
@settings(max_examples=200, deadline=None)
def test_decoders_never_crash_on_mutated_payloads(protocol, data):
    codec = get_codec(protocol)
    payload = bytearray(codec.encode_request('m', {'a': [1, 'two', b'3', {'k': 4.5}], 'b': None}))

    for _ in range(data.draw(st.integers(1, 4))):
        position = data.draw(st.integers(0, len(payload) - 1))
        payload[position] = data.draw(st.integers(0, 255))

    try:
        codec.decode_request(bytes(payload))
    except RelstProtocolError:
        pass


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
def test_special_floats_and_signed_zero(protocol):
    codec = get_codec(protocol)
    result = codec.decode_response(codec.encode_response([math.inf, -math.inf, math.nan, -0.0, 5e-324, 1.7976931348623157e308]))

    assert result[0] == math.inf and result[1] == -math.inf and math.isnan(result[2])
    assert math.copysign(1, result[3]) == -1
    assert result[4:] == [5e-324, 1.7976931348623157e308]


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
@pytest.mark.parametrize('text', [
    '', ' ', '  lead and trail  ', 'a\r\nb', '\r', '\n\n', '\t', '\x00', '\x01\x02', '￾￿', '\ud800',
    '\U0001f600 emoji', '<tag attr="1">&amp;</tag>', ']]>', '<![CDATA[x]]>', '$bytes', 'null', '‮ rtl', 'x' * 100_000,
], ids=lambda text: repr(text)[:20])
def test_nasty_strings(protocol, text):
    codec = get_codec(protocol)
    assert codec.decode_response(codec.encode_response(text)) == text
    assert codec.decode_request(codec.encode_request('m', {'k': text}))[1] == {'k': text}


@pytest.mark.parametrize('name', ['\x00', 'a\x01b', '￾'])
def test_xml_rejects_unprintable_names(name):
    with pytest.raises(RelstProtocolError):
        XmlCodec().encode_request('m', {name: 1})

    with pytest.raises(RelstProtocolError):
        XmlCodec().encode_request(name, {})


@pytest.mark.parametrize('name', ['a b', 'new\nline', 'tab\t', 'q"uote', "ap'os", '<&>', 'ünï', ''])
def test_xml_names_roundtrip(name):
    assert XmlCodec().decode_request(XmlCodec().encode_request(name, {name: 1})) == (name, {name: 1})


@pytest.mark.parametrize('protocol', ['json', 'xml'])
def test_marker_lookalikes_survive(protocol):
    codec = get_codec(protocol)
    lookalikes = [{'$bytes': 'zz'}, {'$bytes': '00'}, {'$float': 'nan'}, {'$dict': {'a': 1}}, {'$x': 1, 'b': 2}, {'$bytes': b'\x01'}]

    for value in lookalikes:
        assert codec.decode_response(codec.encode_response(value)) == value


def test_json_rejects_non_standard_constants():
    for payload in (b'NaN', b'Infinity', b'-Infinity'):
        with pytest.raises(RelstProtocolError):
            JsonCodec().decode_response(payload)


@pytest.mark.parametrize('payload', [b'{', b'[1,2', b'\xff\xfe', b'{"a": }', b'{"a": 1} trailing', b'tru'])
def test_json_malformed(payload):
    with pytest.raises(RelstProtocolError):
        JsonCodec().decode_request(payload)


def test_json_request_must_be_object():
    for payload in (b'[1]', b'1', b'"s"', b'null'):
        with pytest.raises(RelstProtocolError):
            JsonCodec().decode_request(payload)


def test_json_bad_marker_payloads():
    for payload in (b'{"$bytes": "xyz"}', b'{"$bytes": 5}', b'{"$float": "banana"}'):
        with pytest.raises(RelstProtocolError):
            JsonCodec().decode_response(payload)


def test_deep_nesting_is_refused_everywhere():
    deep = []
    for _ in range(1000):
        deep = [deep]

    for codec in CODECS.values():
        with pytest.raises(RelstProtocolError):
            codec.encode_response(deep)

    with pytest.raises(RelstProtocolError):
        JsonCodec().decode_response(b'[' * 100_000 + b']' * 100_000)

    with pytest.raises(RelstProtocolError):
        XmlCodec().decode_response(b'<response>' + b'<value type="list">' * 5000 + b'</value>' * 5000 + b'</response>')

    with pytest.raises(RelstProtocolError):
        decode_value(b'\x07\x00\x00\x00\x01' * 5000)


def test_nesting_at_the_limit_works():
    value = []
    for _ in range(MAX_DEPTH - 2):
        value = [value]

    for codec in CODECS.values():
        assert codec.decode_response(codec.encode_response(value)) == value


@pytest.mark.parametrize('attack', [
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;">]><response><value>&lol2;</value></response>',
    b'<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><response><value>&xxe;</value></response>',
    b'<!doctype x><response/>',
    b'<!DOCTYPE\nx [<!ENTITY e "x">]><response><value>&e;</value></response>',
    '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE x [<!ENTITY e "x">]><response><value>&e;</value></response>'.encode('utf-16'),
    '<!DOCTYPE x [<!ENTITY e "x">]><response><value>&e;</value></response>'.encode('utf-16-le'),
])
def test_xml_entity_attacks_rejected(attack):
    with pytest.raises(RelstProtocolError):
        XmlCodec().decode_response(attack)

    with pytest.raises(RelstProtocolError):
        XmlCodec().decode_request(attack)


def test_xml_undefined_entity_and_unknown_encoding_are_protocol_errors():
    for payload in (b'<response><value>&nope;</value></response>', b'<?xml version="1.0" encoding="no-such-enc"?><response/>'):
        with pytest.raises(RelstProtocolError):
            XmlCodec().decode_response(payload)


@pytest.mark.parametrize('payload', [
    b'<', b'<request', b'<request><arg/></request>', b'<request><arg name="a"/></request>',
    b'<request><arg name="a"><value type="int">x</value></arg></request>',
    b'<request><arg name="a"><value type="int"></value></arg></request>',
    b'<request><arg name="a"><value type="bool">yes</value></arg></request>',
    b'<request><arg name="a"><value type="wat"/></arg></request>',
    b'<request><arg name="a"><value/></arg><arg name="a"><value/></arg></request>',
    b'<request><arg name="a"><value type="bytes">zz</value></arg></request>',
    b'<request><arg name="a"><value type="str" encoding="base64">!!!</value></arg></request>',
    b'<request><arg name="a"><value type="dict"><entry><value/></entry></value></arg></request>',
    b'<request><arg name="a"><value type="dict"><entry><value type="list"/><value/></entry></value></arg></request>',
    b'<other/>', b'<request><bogus/></request>', b'\xff\xfe<request/>',
])
def test_xml_malformed_requests(payload):
    with pytest.raises(RelstProtocolError):
        XmlCodec().decode_request(payload)


def test_empty_bodies_mean_no_arguments():
    assert XmlCodec().decode_request(b'') == (None, {})
    assert JsonCodec().decode_request(b'  ') == (None, {})
    assert BinaryCodec().decode_request(b'') == (None, {})


def test_xml_untyped_value_is_string_and_method_attribute_is_read():
    method, kwargs = XmlCodec().decode_request(b'<request method="echo"><arg name="text"><value>hi</value></arg></request>')
    assert (method, kwargs) == ('echo', {'text': 'hi'})


def test_huge_ints_do_not_crash():
    with pytest.raises(RelstProtocolError):
        XmlCodec().decode_request(b'<request><arg name="a"><value type="int">' + b'9' * 100_000 + b'</value></arg></request>')

    with pytest.raises(RelstProtocolError):
        JsonCodec().decode_response(b'9' * 100_000)

    with pytest.raises(RelstProtocolError):
        JsonCodec().encode_response(10 ** 100_000)


def test_error_roundtrip_all_protocols():
    for codec in CODECS.values():
        with pytest.raises(RelstRemoteError) as caught:
            codec.decode_response(codec.encode_error(418, 'tea <&> \x00\r pot'), status=418)

        assert caught.value.code == 418
        assert caught.value.message.startswith('tea')


def test_binary_frame_layout_is_stable():
    frame = BinaryCodec().encode_request('echo', {})
    assert frame[:4] == b'RLST'
    assert frame[4] == 1 and frame[5] == 0
    assert int.from_bytes(frame[6:8], 'big') == 4
    assert int.from_bytes(frame[8:12], 'big') == len(frame) - 12 - 4
    assert frame[12:16] == b'echo'


@pytest.mark.parametrize('mutation', [
    lambda f: f[:-1], lambda f: f + b'\x00', lambda f: b'XXXX' + f[4:], lambda f: f[:4] + b'\x09' + f[5:],
    lambda f: f[:5] + b'\x07' + f[6:], lambda f: f[:11], lambda f: f[:8] + b'\xff\xff\xff\xff' + f[12:], lambda f: b'\x00',
])
def test_binary_frame_corruptions(mutation):
    frame = BinaryCodec().encode_response({'a': 1})

    with pytest.raises(RelstProtocolError):
        BinaryCodec().decode_response(mutation(frame))


def test_binary_forged_counts_fail_fast_without_allocating():
    for forged in (b'\x07\xff\xff\xff\xff', b'\x08\xff\xff\xff\xff', b'\x05\xff\xff\xff\xff', b'\x06\xff\xff\xff\xff', b'\x09\xff\xff\xff\xff'):
        with pytest.raises(RelstProtocolError):
            decode_value(forged)


def test_binary_trailing_bytes_and_bad_tags():
    for payload in (encode_value(1) + b'\x00', b'\xee', b'', b'\x05\x00\x00\x00\x02\xff\xfe', b'\x09\x00\x00\x00\x00',
                    b'\x08\x00\x00\x00\x01\x07\x00\x00\x00\x00\x00'):
        with pytest.raises(RelstProtocolError):
            decode_value(payload)


@pytest.mark.parametrize('number', [0, -1, 2 ** 63 - 1, 2 ** 63, -2 ** 63, -2 ** 63 - 1, 2 ** 64, 2 ** 1000, -2 ** 1000])
def test_binary_int_boundaries(number):
    assert decode_value(encode_value(number)) == number


def test_binary_request_requires_request_frame_and_dict_payload():
    codec = BinaryCodec()

    with pytest.raises(RelstProtocolError):
        codec.decode_request(codec.encode_response('x'))

    with pytest.raises(RelstProtocolError):
        codec.decode_request(Frame(0, 'm', encode_value([1, 2])).to_bytes())

    with pytest.raises(RelstProtocolError):
        codec.decode_request(Frame(0, 'm', encode_value({1: 2})).to_bytes())


def test_binary_long_method_name_limit():
    with pytest.raises(RelstProtocolError):
        BinaryCodec().encode_request('a' * 70_000, {})


def test_unicode_method_names_in_binary():
    name = 'métode_日本'
    assert BinaryCodec().decode_request(BinaryCodec().encode_request(name, {'x': 1})) == (name, {'x': 1})


def test_to_plain_handles_rich_objects():
    from tests.conftest import Point, Color, Tagged
    codec = JsonCodec()
    assert codec.decode_response(codec.encode_response(Point(1, 2))) == {'x': 1, 'y': 2}
    assert codec.decode_response(codec.encode_response(Color.RED)) == 1
    assert codec.decode_response(codec.encode_response((1, {2}))) == [1, [2]]
    assert codec.decode_response(codec.encode_response(Tagged(1, 'hi', Point(3, 4))))['origin'] == {'x': 3, 'y': 4}
    assert codec.decode_response(codec.encode_response({1: 'a', None: 'b', 2.5: 'c'})) == {'1': 'a', 'null': 'b', '2.5': 'c'}


def test_content_type_negotiation():
    assert codec_from_content_type(None).name == 'json'
    assert codec_from_content_type('application/json; charset=utf-8').name == 'json'
    assert codec_from_content_type('APPLICATION/XML').name == 'xml'
    assert codec_from_content_type('text/xml').name == 'xml'
    assert codec_from_content_type('application/octet-stream').name == 'binary'

    with pytest.raises(RelstProtocolError):
        codec_from_content_type('text/html')

    with pytest.raises(RelstProtocolError):
        get_codec('yaml')
