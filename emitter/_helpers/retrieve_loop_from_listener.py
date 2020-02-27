# Internal
import typing as T
from weakref import ReferenceType

# Project
from .._types import ListenerCb
from ..errors import ListenerMissingEventLoopError

if T.TYPE_CHECKING:
    from asyncio import AbstractEventLoop


def retrieve_loop_from_listener(
    listener: ListenerCb[T.Any], loop: T.Optional["AbstractEventLoop"] = None
) -> T.Optional["AbstractEventLoop"]:
    try:
        cache = listener.__dict__
    except AttributeError:  # not all objects have __dict__ (e.g. class defines slots)
        return None

    loop_ref: "ReferenceType[AbstractEventLoop]" = cache.get("__loop__", None)
    if loop_ref is None:
        if loop is not None:
            cache["__loop__"] = ReferenceType(loop)
    else:
        loop = loop_ref()
        if loop is None:
            # The attached loop was garbage collected
            raise ListenerMissingEventLoopError(
                "Attempted execution of a listener which was "
                "bound to a garbage collected event loop",
                listener,
            )

    return loop
