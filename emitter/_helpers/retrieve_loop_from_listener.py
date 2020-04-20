# Internal
import typing as T
from asyncio import AbstractEventLoop
from weakref import ReferenceType

# Project
from ..errors import ListenerMissingEventLoopError


def retrieve_loop_from_listener(
    listener: T.Any, loop: T.Optional["AbstractEventLoop"] = None
) -> T.Optional["AbstractEventLoop"]:
    loop_ref: T.Union[
        None, AbstractEventLoop, "ReferenceType[T.Optional[AbstractEventLoop]]"
    ] = getattr(listener, "__loop__", None)
    if isinstance(loop_ref, ReferenceType):
        loop = loop_ref()
        if loop is None:
            # The attached loop was garbage collected
            raise ListenerMissingEventLoopError(
                "Attempted execution of a listener which was "
                "bound to a garbage collected event loop",
                listener,
            )
    elif loop_ref is None and loop is not None:
        try:
            setattr(listener, "__loop__", ReferenceType(loop))
        except AttributeError:  # not all objects are writable
            raise AttributeError(
                "Failed to assign listener's loop. "
                f"{type(listener).__qualname__} attributes aren't writable"
            ) from None
    else:
        loop = loop_ref

    # This check is mostly redundant. However, the above else clause, may bring user data that may
    # not be an event loop, so check anyway.
    if isinstance(loop, AbstractEventLoop) or loop is None:
        return loop

    raise ValueError("__loop__ attribute isn't an asyncio loop")
