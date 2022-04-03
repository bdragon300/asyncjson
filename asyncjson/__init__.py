from typing import Any, AsyncGenerator

from .encoder import encode


async def async_dumps(o: Any, pretty: bool = True) -> AsyncGenerator[str, None]:
    async for i in encode(o, pretty=pretty):
        yield i