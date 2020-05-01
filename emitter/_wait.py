# Internal
import typing as T

# Project
from ._on import on
from ._remove import remove
from ._helpers import get_running_loop, retrieve_loop_from_listener

# Type generics
K = T.TypeVar("K")

if T.TYPE_CHECKING:
    # Internal
    from asyncio import Future


async def wait(event: T.Union[str, T.Type[K]], namespace: object) -> K:
    # Retrieve listeners
    loop = get_running_loop()
    result: "Future[K]" = loop.create_future()
    listeners = retrieve_loop_from_listener(namespace)

    # Don't keep namespace reference
    del namespace

    on(event, listeners, result.set_result, once=True)

    try:
        return await result
    finally:
        if result.exception():
            # An exception occurred. Probably that the listeners didn't execute, so remove it.
            remove(event, listeners, result.set_result)
