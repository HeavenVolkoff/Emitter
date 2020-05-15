# Internal
import typing as T

# Project
from ._on import on
from ._remove import remove
from ._helpers import get_running_loop, retrieve_listeners_from_namespace

# Type generics
K = T.TypeVar("K")

if T.TYPE_CHECKING:
    # Internal
    from asyncio import Future


async def wait(event: T.Union[str, T.Type[K]], namespace: object) -> K:
    """This is a helper function that awaits for the first execution of a given
    event or scope namespace and return its value.

    Args:

        event: Event type or scope namespace.

        namespace: Specify the namespace in which to wait for the event emission.

    Returns:

        Emitted event instance.

    """

    # Retrieve listeners
    loop = get_running_loop()
    result: "Future[K]" = loop.create_future()
    listeners = retrieve_listeners_from_namespace(namespace)

    # Don't keep namespace reference
    del namespace

    on(event, listeners, result.set_result, once=True)

    try:
        return await result
    finally:
        if result.exception():
            # An exception occurred. It is probable that the listeners didn't execute,
            # so remove it.
            remove(event, listeners, result.set_result)
