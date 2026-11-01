import re
import math
import base64
from typing import Optional, Tuple
from xml.etree import ElementTree
from .codec import Codec
from .values import to_plain
from .errors import RelstProtocolError, RelstRemoteError


MAX_DEPTH = 64
VALUE_TAG = 'value'
# chars xml 1.0 can't carry (or parsers would normalize), those strings travel as base64
UNSAFE_XML_CHARS = re.compile('[^ -퟿\u000a\u0009-�\U00010000-\U0010ffff]')
FORBIDDEN_DECLARATIONS = ('<!doctype', '<!entity', '<!element', '<!attlist')


class XmlCodec(Codec):
    """
    <request method="echo"><arg name="text"><value type="str">hi</value></arg></request>
    <response><value type="int">5</value></response>
    <error code="404">message</error>
    A <value> without type attribute is a string.
    """

    name = 'xml'
    content_type = 'application/xml'

    @property
    def is_binary(self) -> bool:
        return False

    def encode_request(self, method: str, kwargs: dict) -> bytes:
        _check_name(method)
        root = ElementTree.Element('request', {'method': method})

        for name, value in to_plain(kwargs).items():
            _check_name(name)

            argument = ElementTree.SubElement(root, 'arg', {'name': name})
            argument.append(self._to_element(value))

        return self._tostring(root)

    def decode_request(self, data: bytes) -> Tuple[Optional[str], dict]:
        if not data or not data.strip():
            return None, dict()

        root = self._parse(data)

        if root.tag != 'request':
            raise RelstProtocolError(f'expected <request> root, got <{root.tag}>')

        kwargs = dict()

        for argument in root:
            if argument.tag != 'arg' or 'name' not in argument.attrib or len(argument) != 1:
                raise RelstProtocolError('<request> children must be <arg name=".."><value/></arg>')

            if argument.attrib['name'] in kwargs:
                raise RelstProtocolError(f"duplicate argument {argument.attrib['name']}")

            kwargs[argument.attrib['name']] = self._from_element(argument[0])

        return root.attrib.get('method'), kwargs

    def encode_response(self, value) -> bytes:
        root = ElementTree.Element('response')
        root.append(self._to_element(to_plain(value)))
        return self._tostring(root)

    def encode_error(self, code: int, message: str) -> bytes:
        root = ElementTree.Element('error', {'code': str(code)})
        root.text = _printable(message)
        return self._tostring(root)

    def decode_response(self, data: bytes, status: int = 200):
        root = self._parse(data)

        if root.tag == 'error':
            try:
                code = int(root.attrib.get('code', status))
            except ValueError as err:
                raise RelstProtocolError('invalid error code') from err

            raise RelstRemoteError(code, root.text or '')

        if root.tag != 'response' or len(root) != 1:
            raise RelstProtocolError('expected <response><value/></response>')

        return self._from_element(root[0])

    @staticmethod
    def _tostring(root: ElementTree.Element) -> bytes:
        return ElementTree.tostring(root, encoding='utf-8', xml_declaration=True)

    @staticmethod
    def _parse(data: bytes) -> ElementTree.Element:
        # NOTE: expat expands entities (billion-laughs), relst payloads never need a DTD.
        # payload is decoded as utf8 first, so other encodings (utf16) can't hide a DTD from the check
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as err:
            raise RelstProtocolError('xml must be utf-8 encoded') from err

        if '\x00' in text:
            # NOTE: NUL bytes make expat auto-detect utf-16 and hide the DTD from the check below
            raise RelstProtocolError('xml must not contain NUL characters')

        lowered = text.lower()

        if any(marker in lowered for marker in FORBIDDEN_DECLARATIONS):
            raise RelstProtocolError('xml declarations (DOCTYPE/ENTITY) are not allowed')

        try:
            return ElementTree.fromstring(text)
        except (ElementTree.ParseError, ValueError, LookupError, RecursionError) as err:
            raise RelstProtocolError(f'invalid xml: {err}') from err

    def _to_element(self, value) -> ElementTree.Element:
        element = ElementTree.Element(VALUE_TAG)

        if value is None:
            element.set('type', 'none')
        elif isinstance(value, bool):
            element.set('type', 'bool')
            element.text = 'true' if value else 'false'
        elif isinstance(value, int):
            element.set('type', 'int')
            element.text = str(value)
        elif isinstance(value, float):
            element.set('type', 'float')
            element.text = _float_to_text(value)
        elif isinstance(value, str):
            element.set('type', 'str')

            if UNSAFE_XML_CHARS.search(value) or '\r' in value:
                element.set('encoding', 'base64')
                element.text = base64.b64encode(value.encode('utf-8', 'surrogatepass')).decode('ascii')
            else:
                element.text = value
        elif isinstance(value, bytes):
            element.set('type', 'bytes')
            element.text = value.hex()
        elif isinstance(value, list):
            element.set('type', 'list')
            element.extend(self._to_element(item) for item in value)
        elif isinstance(value, dict):
            element.set('type', 'dict')

            for key, item in value.items():
                entry = ElementTree.SubElement(element, 'entry')
                entry.append(self._to_element(key))
                entry.append(self._to_element(item))
        else:
            raise RelstProtocolError(f'unsupported value {type(value).__name__}')

        return element

    def _from_element(self, element: ElementTree.Element, depth: int = 0):
        if depth > MAX_DEPTH:
            raise RelstProtocolError(f'xml nested deeper than {MAX_DEPTH}')

        if element.tag != VALUE_TAG:
            raise RelstProtocolError(f'expected <value>, got <{element.tag}>')

        value_type = element.attrib.get('type', 'str')
        text = element.text or ''

        if value_type == 'none':
            return None

        if value_type == 'bool':
            if text.strip() not in ('true', 'false'):
                raise RelstProtocolError(f'invalid bool {text!r}')

            return text.strip() == 'true'

        if value_type == 'int':
            return self._parse_number(int, text)

        if value_type == 'float':
            return self._parse_number(float, text)

        if value_type == 'str':
            if element.attrib.get('encoding') == 'base64':
                try:
                    return base64.b64decode(text, validate=True).decode('utf-8', 'surrogatepass')
                except ValueError as err:
                    raise RelstProtocolError('invalid base64 string') from err

            return text

        if value_type == 'bytes':
            try:
                return bytes.fromhex(text.strip())
            except ValueError as err:
                raise RelstProtocolError('invalid bytes hex') from err

        if value_type == 'list':
            return [self._from_element(item, depth + 1) for item in element]

        if value_type == 'dict':
            result = dict()

            for entry in element:
                if entry.tag != 'entry' or len(entry) != 2:
                    raise RelstProtocolError('<dict> children must be <entry><value/><value/></entry>')

                key = self._from_element(entry[0], depth + 1)
                item = self._from_element(entry[1], depth + 1)

                try:
                    result[key] = item
                except TypeError as err:
                    raise RelstProtocolError('unhashable dict key') from err

            return result

        raise RelstProtocolError(f'unknown value type {value_type!r}')

    @staticmethod
    def _parse_number(number_type, text: str):
        try:
            return number_type(text.strip())
        except ValueError as err:
            raise RelstProtocolError(f'invalid {number_type.__name__} {text!r}') from err


def _check_name(name):
    if not isinstance(name, str) or UNSAFE_XML_CHARS.search(name):
        raise RelstProtocolError(f'names must be strings of xml-safe characters, got {name!r}')


def _float_to_text(value: float) -> str:
    if math.isfinite(value):
        return repr(value)

    return 'nan' if math.isnan(value) else ('inf' if value > 0 else '-inf')


def _printable(message: str) -> str:
    return UNSAFE_XML_CHARS.sub('?', message.replace('\r', ' '))
