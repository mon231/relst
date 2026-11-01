import enum
import pathlib
import pytest
from dataclasses import dataclass, field
from inspect import signature
from relst.protocol import CODECS, RelstProtocolError, to_plain
from relst.protocol.values import text_keys
from tests.conftest import Color, Point


class Perm(enum.IntFlag):
    READ = 1
    WRITE = 2


class Name(str, enum.Enum):
    A = 'alpha'


class FancyInt(int):
    def __str__(self):
        return 'fancy'


class FancyFloat(float):
    def __repr__(self):
        return 'fancy'


class FancyStr(str):
    def __str__(self):
        return 'fancy'


@dataclass
class Inner:
    numbers: list = field(default_factory=lambda: [1, 2])


@dataclass
class Outer:
    inner: Inner
    label: str = 'x'


def test_primitive_subclasses_become_exact_types():
    # python 3.10 formats IntEnum as 'Color.BLUE' in str(), codecs must never see the subclass
    for value, expected in [(Color.BLUE, 2), (Perm.READ | Perm.WRITE, 3), (Name.A, 'alpha'), (FancyInt(5), 5), (FancyFloat(1.5), 1.5), (FancyStr('s'), 's')]:
        plain = to_plain(value)
        assert plain == expected and type(plain) in (int, float, str)


def test_exact_types_everywhere_in_containers():
    plain = to_plain({'k': [Color.RED, (FancyInt(1),), {Perm.WRITE}]})
    assert type(plain['k'][0]) is int and type(plain['k'][1][0]) is int and type(plain['k'][2][0]) is int


@pytest.mark.parametrize('protocol', ['json', 'xml', 'binary'])
def test_enum_values_roundtrip_in_every_protocol(protocol):
    codec = CODECS[protocol]
    value = {'color': Color.BLUE, 'perm': Perm.READ | Perm.WRITE, 'name': Name.A, 'list': [Color.RED, FancyInt(7), FancyFloat(2.5), FancyStr('s')]}

    assert codec.decode_response(codec.encode_response(value)) == {'color': 2, 'perm': 3, 'name': 'alpha', 'list': [1, 7, 2.5, 's']}


@pytest.mark.parametrize('protocol', ['xml', 'binary'])
def test_enum_dict_keys(protocol):
    codec = CODECS[protocol]
    assert codec.decode_response(codec.encode_response({Color.RED: 'a', Perm.WRITE: 'b'})) == {1: 'a', 2: 'b'}


def test_bool_stays_bool_and_is_not_confused_with_int():
    assert to_plain(True) is True and to_plain(False) is False
    assert to_plain([True, 1]) == [True, 1] and type(to_plain([True, 1])[1]) is int


def test_nested_dataclasses_and_firstclass():
    assert to_plain(Outer(Inner())) == {'inner': {'numbers': [1, 2]}, 'label': 'x'}
    assert to_plain([Point(1, 2), Point(3, 4)]) == [{'x': 1, 'y': 2}, {'x': 3, 'y': 4}]


def test_dataclass_type_itself_is_not_serialized_as_instance():
    assert to_plain(Outer) == 'Outer'


def test_bytes_like_become_bytes():
    assert to_plain(bytearray(b'ab')) == b'ab' and type(to_plain(bytearray(b'ab'))) is bytes
    assert to_plain(memoryview(b'ab')) == b'ab'


def test_collections_and_misc_objects():
    assert to_plain((1, 2)) == [1, 2]
    assert sorted(to_plain({3, 1, 2})) == [1, 2, 3]
    assert to_plain(frozenset([1])) == [1]
    assert to_plain(pathlib.PurePosixPath('/a/b')) == '/a/b'
    assert to_plain(object).startswith('object') and to_plain(complex(1, 2)) == '(1+2j)'


def test_signature_serialization():
    def method(a: int, b: str = 'x', *args, c: float = 1.5, **kwargs) -> bool:
        pass

    plain = to_plain(signature(method))
    assert plain['return'] == 'bool'
    assert [(param['name'], param['kind']) for param in plain['params']] == [
        ('a', 'POSITIONAL_OR_KEYWORD'), ('b', 'POSITIONAL_OR_KEYWORD'), ('args', 'VAR_POSITIONAL'), ('c', 'KEYWORD_ONLY'), ('kwargs', 'VAR_KEYWORD'),
    ]
    assert plain['params'][1]['default'] == 'x' and plain['params'][3]['default'] == 1.5 and 'default' not in plain['params'][0]


def test_depth_limit_for_self_referencing_structures():
    loop = []
    loop.append(loop)

    with pytest.raises(RelstProtocolError):
        to_plain(loop)

    recursive = {}
    recursive['self'] = recursive

    with pytest.raises(RelstProtocolError):
        to_plain(recursive)


def test_text_keys_covers_every_key_type():
    assert text_keys({True: 'c', 'k': 'v'}) == {'true': 'c', 'k': 'v'}
    assert text_keys({'k': {3: [{4: 5}]}}) == {'k': {'3': [{'4': 5}]}}
    assert text_keys({None: 1, 1.5: 2, b'\xff': 3}) == {'null': 1, '1.5': 2, 'ff': 3}
