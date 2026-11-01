"""
Relst "plain" value model: None, bool, int, float, str, bytes, list, dict.
Every codec encodes and decodes exactly this model, `to_plain` maps rich python objects onto it.
"""

import math
from enum import Enum
from pathlib import PurePath
from inspect import Signature
from dataclasses import is_dataclass, fields
from .errors import RelstProtocolError


MAX_DEPTH = 64


def to_plain(obj, _depth: int = 0):
    if _depth > MAX_DEPTH:
        raise RelstProtocolError(f'value nested deeper than {MAX_DEPTH}')

    next_depth = _depth + 1

    if isinstance(obj, Enum):
        # NOTE: before the primitives check, IntEnum / StrEnum are ints / strs too
        return to_plain(obj.value, next_depth)

    if obj is None or isinstance(obj, (bool, int, float, str, bytes)):
        return exact_primitive(obj)

    if isinstance(obj, (bytearray, memoryview)):
        return bytes(obj)

    if hasattr(obj, 'to_dict') and hasattr(type(obj), 'from_dict'):
        # firstclass objects
        return to_plain(obj.to_dict(), next_depth)

    if is_dataclass(obj) and not isinstance(obj, type):
        return {field.name: to_plain(getattr(obj, field.name), next_depth) for field in fields(obj)}

    if isinstance(obj, dict):
        return {to_plain_key(key): to_plain(value, next_depth) for key, value in obj.items()}

    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_plain(element, next_depth) for element in obj]

    if isinstance(obj, Signature):
        return _signature_to_plain(obj)

    if isinstance(obj, type):
        return obj.__name__

    if isinstance(obj, PurePath):
        return str(obj)

    return str(obj)


def exact_primitive(obj):
    """
    :brief: maps subclasses of the primitives (IntEnum, IntFlag, str-mixins, numpy-like floats) onto the exact type,
            their str() / repr() differ between python versions (3.10: str(IntEnum) == 'Color.BLUE')
    """

    if obj is None or type(obj) in (bool, int, float, str, bytes):
        return obj

    if isinstance(obj, int):
        return int(obj)

    if isinstance(obj, float):
        return float(obj)

    if isinstance(obj, str):
        return str.__str__(obj)

    return bytes(obj)


def to_plain_key(key):
    if isinstance(key, Enum):
        return to_plain_key(key.value)

    if isinstance(key, (str, int, bool, float, bytes)) or key is None:
        return exact_primitive(key)

    return str(key)


def text_keys(plain):
    """
    :brief: json and xml-friendly copy of plain-value where all dict-keys are strings
    """
    if isinstance(plain, dict):
        return {_key_to_text(key): text_keys(value) for key, value in plain.items()}

    if isinstance(plain, list):
        return [text_keys(element) for element in plain]

    return plain


def _key_to_text(key) -> str:
    if isinstance(key, str):
        return key

    if isinstance(key, bytes):
        return key.hex()

    if isinstance(key, bool):
        return 'true' if key else 'false'

    if key is None:
        return 'null'

    return repr(key) if isinstance(key, float) else str(key)


def annotation_name(annotation) -> str:
    if annotation is Signature.empty:
        return 'any'

    if isinstance(annotation, str):
        return annotation

    if isinstance(annotation, type):
        return annotation.__name__

    return str(annotation).replace('typing.', '')


def _signature_to_plain(signature: Signature) -> dict:
    params = []

    for param in signature.parameters.values():
        serialized = {
            'name': param.name,
            'type': annotation_name(param.annotation),
            'kind': param.kind.name,
        }

        if param.default is not Signature.empty:
            serialized['default'] = to_plain(param.default)

        params.append(serialized)

    return {'params': params, 'return': annotation_name(signature.return_annotation)}


def is_nan_or_inf(value) -> bool:
    return isinstance(value, float) and not math.isfinite(value)
