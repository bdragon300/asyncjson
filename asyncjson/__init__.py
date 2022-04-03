__all__ = ['dumps', 'dumpgen']
from typing import Any, AsyncGenerator

from .encoder import JSONEncoder


async def dumps(o: Any, **kwargs) -> str:
    return await JSONEncoder(**kwargs). encode(o)


async def dumpgen(o: Any, **kwargs) -> AsyncGenerator[str, None]:
    return await JSONEncoder(**kwargs).iterencode(o)
