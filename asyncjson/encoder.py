__all__ = ['encode']
import inspect
import re
import types
import json
from typing import AsyncGenerator, Any, Tuple, List, Union, Generator, Iterator, Iterable, Mapping, \
    AsyncIterator, AsyncIterable, Callable, Coroutine, Awaitable, Optional

ObjType = int

SENTINEL = object()
INFINITY = float('inf')
ESCAPE = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t]')
ESCAPE_ASCII = re.compile(r'([\\"]|[^\ -~])')
ESCAPE_DCT = {
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


def floatstr(o, allow_nan=True,
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


async def py_encode_basestring(s):
    """Return a JSON representation of a Python string

    """
    def replace(match):
        return ESCAPE_DCT[match.group(0)]
    return '"' + ESCAPE.sub(replace, s) + '"'


async def py_encode_basestring_ascii(s):
    """Return an ASCII-only JSON representation of a Python string

    """
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


async def join_dictkey(item_type: ObjType, item: Union[Iterable, AsyncIterable]) -> str:
    """Encode a dict key if it's a sequence or generator"""
    if item_type == OBJTYPE_SEQUENCE:
        return ''.join(str(x) for x in item)
    elif item_type == OBJTYPE_ASYNC_GENERATOR:
        k = ""
        async for x in item:
            k += str(x)
        return k
    else:
        raise TypeError(f"Cannot encode dict key of type '{type(item)}', "
                        f"allowed are Iterable, AsyncIterable") # FIXME: msg


async def wrong_type(obj: Any) -> str:
    raise TypeError(f"No encoder for type {type(obj)}, you can specify your own custom encoder "
                    f"by 'default' parameter")


async def encode(
        vobj,
        *,
        pretty: bool = True,
        sort_keys: bool = False,
        ensure_ascii: bool = True,
        allow_nan: bool = True,
        indent: int = 1,
        separators: Tuple[str, str] = (', ', ': '),
        encode_dictkey: Optional[Callable[[ObjType, Union[Iterable, AsyncIterable]], Awaitable[str]]] = None,
        default: Optional[Callable[[Any], Awaitable[str]]] = None,
        **_
) -> AsyncGenerator[str, None]:
    stack = []
    item_separator, key_separator = separators
    indent_space = ' ' * indent
    string_encoder = py_encode_basestring_ascii if ensure_ascii else py_encode_basestring
    if encode_dictkey is None:
        encode_dictkey = join_dictkey
    if default is None:
        default = wrong_type

    enc = value_encoder(string_encoder=string_encoder, allow_nan=allow_nan, default=default)
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

    if pretty:
        yield '\n'

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
                    yield await string_encoder(await encode_dictkey(ktyp, kobj))
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


async def close_encoder(gen):
    try:
        await gen.asend(SENTINEL)
    except StopAsyncIteration:
        pass


async def value_encoder(
        string_encoder, allow_nan, default
) -> AsyncGenerator[Tuple[ObjType, Union[str, Iterable, Mapping, Generator, AsyncGenerator]], Any]:
    typ, obj = None, None
    intstr = int.__repr__

    while True:
        item = yield typ, obj
        if item is SENTINEL:
            break

        if inspect.isawaitable(item):
            item = await item

        if isinstance(item, str):
            typ, obj = OBJTYPE_STRING, await string_encoder(item)
        elif item is None:
            typ, obj = OBJTYPE_STRING, 'null'
        elif item is True:
            typ, obj = OBJTYPE_STRING, 'true'
        elif item is False:
            typ, obj = OBJTYPE_STRING, 'false'
        elif isinstance(item, int):
            # Subclasses of int/float may override __repr__, but we still
            # want to encode them as integers/floats in JSON. One example
            # within the standard library is IntEnum.
            typ, obj = OBJTYPE_STRING, intstr(item)
        elif isinstance(item, float):
            # see comment above for int
            typ, obj = OBJTYPE_STRING, floatstr(item, allow_nan)
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
