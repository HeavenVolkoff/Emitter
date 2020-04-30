# Internal
import typing as T

# Project
from ._on import on
from ._helpers import get_running_loop

# Type generics
K = T.TypeVar("K")

if T.TYPE_CHECKING:
    # Internal
    from asyncio import Future


async def wait(event: T.Union[str, T.Type[K]], namespace: object) -> K:
    # Retrieve listeners
    loop = get_running_loop()
    result: "Future[K]" = loop.create_future()

    on(event, namespace, result.set_result, once=True)

    # Don't keep reference
    del namespace

    return await result
