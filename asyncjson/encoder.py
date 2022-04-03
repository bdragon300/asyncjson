__all__ = ['encoder', 'JSONEncoder', 'ObjType', 'OBJTYPE_STRING', 'OBJTYPE_DICT', 'OBJTYPE_SEQUENCE', 'OBJTYPE_ASYNC_GENERATOR']
import inspect
import re
import types
from typing import (
    AsyncGenerator,
    Any,
    Tuple,
    Union,
    Generator,
    Iterable,
    Mapping,
    AsyncIterable,
    Callable,
    Awaitable,
    Optional,
    Final,
    Type,
    Dict
)

ObjType: Final[Type[int]] = int

SENTINEL: Final[object] = object()
INFINITY: Final[float] = float('inf')
ESCAPE: Final[re.Pattern] = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t]')
ESCAPE_ASCII: Final[re.Pattern] = re.compile(r'([\\"]|[^\ -~])')
ESCAPE_DCT: Dict[str, str] = {
    '\\': '\\\\',
    '"': '\\"',
    '\b': '\\b',
    '\f': '\\f',
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
}
for i in range(0x20):
    ESCAPE_DCT.setdefault(chr(i), '\\u{0:04x}'.format(i))

OBJTYPE_STRING: ObjType = 0
OBJTYPE_DICT: ObjType = 2
OBJTYPE_SEQUENCE: ObjType = 1
OBJTYPE_ASYNC_GENERATOR: ObjType = 3


async def floatstr(o: float, allow_nan: bool = True,
                   _repr=float.__repr__, _inf=INFINITY, _neginf=-INFINITY):
    # Check for specials.  Note that this type of test is processor
    # and/or platform-specific, so do tests which don't depend on the
    # internals.

    if o != o:
        text = 'NaN'
    elif o == _inf:
        text = 'Infinity'
    elif o == _neginf:
        text = '-Infinity'
    else:
        return _repr(o)

    if not allow_nan:
        raise ValueError(
            "Out of range float values are not JSON compliant: " +
            repr(o))

    return text


async def py_encode_basestring(s: str):
    """Return a JSON representation of a Python string

    """
    def replace(match):
        return ESCAPE_DCT[match.group(0)]
    return '"' + ESCAPE.sub(replace, s) + '"'


async def py_encode_basestring_ascii(s: str):
    """Return an ASCII-only JSON representation of a Python string"""
    def replace(match):
        s = match.group(0)
        try:
            return ESCAPE_DCT[s]
        except KeyError:
            n = ord(s)
            if n < 0x10000:
                return '\\u{0:04x}'.format(n)
            else:
                # surrogate pair
                n -= 0x10000
                s1 = 0xd800 | ((n >> 10) & 0x3ff)
                s2 = 0xdc00 | (n & 0x3ff)
                return '\\u{0:04x}\\u{1:04x}'.format(s1, s2)
    return '"' + ESCAPE_ASCII.sub(replace, s) + '"'


async def join_iterable(obj_type: ObjType, obj: Union[Iterable, AsyncIterable]) -> str:
    """Encode a dict key if it's a sequence or generator"""
    if obj_type == OBJTYPE_SEQUENCE:
        return ''.join(str(x) for x in obj)
    elif obj_type == OBJTYPE_ASYNC_GENERATOR:
        k = ""
        async for x in obj:
            k += str(x)
        return k
    else:
        raise TypeError(f"Cannot encode dict key of type '{type(obj)}', "
                        f"allowed are Iterable, AsyncIterable")  # FIXME: msg


class JSONEncoder:
    encode_dictkey: Optional[
        Callable[[ObjType, Union[Iterable, AsyncIterable]], Awaitable[str]]
    ] = None
    encode_string: Optional[Callable[[str], Awaitable[str]]] = None
    encode_float: Optional[Callable[[float, bool], Awaitable[str]]] = None
    encode_int: Optional[Callable[[int], Awaitable[str]]] = None

    def __init__(
            self,
            *,
            pretty: bool = True,
            sort_keys: bool = False,
            ensure_ascii: bool = True,
            allow_nan: bool = True,
            indent: int = 1,
            separators: Tuple[str, str] = (', ', ': '),
            **_
    ):
        self.pretty = pretty
        self.sort_keys = sort_keys
        self.ensure_ascii = ensure_ascii
        self.allow_nan = allow_nan
        self.indent = indent
        self.item_separator, self.key_separator = separators

        if self.encode_string is None:
            self.encode_string = py_encode_basestring_ascii if ensure_ascii else py_encode_basestring
        if self.encode_dictkey is None:
            self.encode_dictkey = join_iterable

        # Subclasses of int/float may override __repr__, but we still
        # want to encode them as integers/floats in JSON. One example
        # within the standard library is IntEnum.
        if self.encode_float is None:
            self.encode_float = floatstr
        if self.encode_int is None:
            async def encode_int(o) -> str:
                return int.__repr__(o)

            self.encode_int = encode_int

    async def default(self, obj: Any):
        raise TypeError(f"No encoder for type {type(obj)}, you can specify your own custom encoder "
                        f"by 'default' parameter")

    async def encode(self, o: Any) -> str:
        return ''.join([x async for x in await self.iterencode(o)])

    async def iterencode(self, o: Any) -> AsyncGenerator[str, None]:
        return encoder(
            o,
            pretty=self.pretty,
            sort_keys=self.sort_keys,
            allow_nan=self.allow_nan,
            indent=self.indent,
            item_separator=self.item_separator,
            key_separator=self.key_separator,
            encode_dictkey=self.encode_dictkey,
            encode_string=self.encode_string,
            encode_float=self.encode_float,
            encode_int=self.encode_int,
            default=self.default
        )


async def encoder(
        vobj,
        *,
        pretty: bool,
        sort_keys: bool,
        allow_nan: bool,
        indent: int,
        item_separator: str,
        key_separator: str,
        encode_dictkey: Callable[[ObjType, Union[Iterable, AsyncIterable]], Awaitable[str]],
        encode_string: Callable[[str], Awaitable[str]],
        encode_float: Callable[[float, bool], Awaitable[str]],
        encode_int: Callable[[int], Awaitable[str]],
        default: Callable[[Any], Awaitable[str]],
        **_
) -> AsyncGenerator[str, None]:
    stack = []
    indent_space = ' ' * indent

    async def close_encoder(gen):
        try:
            await gen.asend(SENTINEL)
        except StopAsyncIteration:
            pass

    enc = value_encoder(allow_nan=allow_nan, encode_string=encode_string, encode_float=encode_float,
                        encode_int=encode_int, default=default)
    await enc.asend(None)

    ittyp, vobj = await enc.asend(vobj)
    it = None
    if ittyp == OBJTYPE_DICT:
        yield '{'
        it = iter(vobj.items())
    elif ittyp == OBJTYPE_SEQUENCE:
        yield '['
        it = iter(vobj)
    elif ittyp == OBJTYPE_ASYNC_GENERATOR:
        yield '['
        it = vobj.__aiter__()
    elif ittyp == OBJTYPE_STRING:
        yield vobj
        await close_encoder(enc)
        return

    stack.append((ittyp, it))
    begun = False
    while stack:
        if ittyp == OBJTYPE_SEQUENCE or ittyp == OBJTYPE_ASYNC_GENERATOR:
            while True:
                try:
                    value = await it.__anext__() if ittyp == OBJTYPE_ASYNC_GENERATOR else next(it)
                    if begun:
                        yield item_separator
                    if pretty:
                        yield '\n'
                    begun = True
                except (StopIteration, StopAsyncIteration):
                    stack.pop()
                    if pretty and begun:
                        yield '\n' + indent_space * len(stack)
                    yield ']'
                    if stack:
                        ittyp, it = stack[-1]
                    begun = True
                    break

                vtyp, vobj = await enc.asend(value)
                if pretty:
                    yield indent_space * len(stack)

                if vtyp != OBJTYPE_STRING:
                    ittyp, vobj = vtyp, vobj
                    if ittyp == OBJTYPE_DICT:
                        yield '{'
                        it = iter(sorted(vobj.items()) if sort_keys else vobj.items())
                    elif ittyp == OBJTYPE_SEQUENCE:
                        yield '['
                        it = iter(vobj)
                    elif ittyp == OBJTYPE_ASYNC_GENERATOR:
                        yield '['
                        it = vobj.__aiter__()
                    stack.append((ittyp, it))
                    begun = False
                    break

                yield vobj

        elif ittyp == OBJTYPE_DICT:
            while True:
                try:
                    key, value = await it.__anext__() if ittyp == OBJTYPE_ASYNC_GENERATOR else next(it)
                    if begun:
                        yield item_separator
                    if pretty:
                        yield '\n'
                    begun = True
                except (StopIteration, StopAsyncIteration):
                    stack.pop()
                    if pretty and begun:
                        yield '\n' + indent_space * len(stack)
                    yield '}'
                    if stack:
                        ittyp, it = stack[-1]
                    begun = True
                    break

                if pretty:
                    yield indent_space * len(stack)

                # KEY
                ktyp, kobj = await enc.asend(key)
                if ktyp == OBJTYPE_STRING:
                    yield kobj
                else:
                    yield await encode_string(await encode_dictkey(ktyp, kobj))
                yield key_separator

                # VALUE
                vtyp, vobj = await enc.asend(value)
                if vtyp != OBJTYPE_STRING:
                    ittyp, vobj = vtyp, vobj
                    if ittyp == OBJTYPE_DICT:
                        yield '{'
                        it = iter(sorted(vobj.items()) if sort_keys else vobj.items())
                    elif ittyp == OBJTYPE_SEQUENCE:
                        yield '['
                        it = iter(vobj)
                    elif ittyp == OBJTYPE_ASYNC_GENERATOR:
                        yield '['
                        it = vobj.__aiter__()
                    stack.append((ittyp, it))
                    begun = False
                    break

                yield vobj

    await close_encoder(enc)


async def value_encoder(
        allow_nan, encode_string, encode_float, encode_int, default
) -> AsyncGenerator[Tuple[ObjType, Union[str, Iterable, Mapping, Generator, AsyncGenerator]], Any]:
    typ, obj = None, None

    while True:
        item = yield typ, obj
        if item is SENTINEL:
            break

        if inspect.isawaitable(item):
            item = await item

        if isinstance(item, str):
            typ, obj = OBJTYPE_STRING, await encode_string(item)
        elif item is None:
            typ, obj = OBJTYPE_STRING, 'null'
        elif item is True:
            typ, obj = OBJTYPE_STRING, 'true'
        elif item is False:
            typ, obj = OBJTYPE_STRING, 'false'
        elif isinstance(item, int):
            typ, obj = OBJTYPE_STRING, await encode_int(item)
        elif isinstance(item, float):
            typ, obj = OBJTYPE_STRING, await encode_float(item, allow_nan)
        elif isinstance(item, (list, tuple)):
            typ, obj = OBJTYPE_SEQUENCE, item
        elif isinstance(item, dict):
            typ, obj = OBJTYPE_DICT, item
        elif isinstance(item, types.GeneratorType):
            typ, obj = OBJTYPE_SEQUENCE, item
        elif isinstance(item, types.AsyncGeneratorType):
            typ, obj = OBJTYPE_ASYNC_GENERATOR, item
        else:
            typ, obj = OBJTYPE_STRING, await default(item)
