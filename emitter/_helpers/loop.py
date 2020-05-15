# Internal
import typing as T
from asyncio import AbstractEventLoop

# Project
from ..error import ListenerStoppedEventLoopError
from .._types import ListenerCb

# Type generics
K = T.TypeVar("K")

try:
    from asyncio import get_running_loop
except ImportError:
    from asyncio import AbstractEventLoop, _get_running_loop

    # Polyfill of get_running_loop for cpython 3.6
    def get_running_loop() -> AbstractEventLoop:
        loop = _get_running_loop()
        if loop:
            return loop
        raise RuntimeError("no running event loop")


class BoundLoopListenerWrapper(T.Generic[K]):
    def __init__(self, loop: AbstractEventLoop, listener: ListenerCb[K]):
        self.__loop__ = loop
        self._listener = listener

    def __call__(self, __event_data: K) -> T.Optional[T.Awaitable[None]]:
        return self._listener(__event_data)


def bound_loop_to_listener(listener: ListenerCb[K], loop: AbstractEventLoop) -> ListenerCb[K]:
    if hasattr(listener, "__loop__"):
        listener_loop: T.Any = getattr(listener, "__loop__")
        if isinstance(listener_loop, AbstractEventLoop):
            if listener_loop is not loop:
                raise ValueError(
                    "The listener belongs to a different loop than the one specified as the loop "
                    "argument "
                )

            return listener
    else:
        try:
            setattr(listener, "__loop__", loop)
        except AttributeError:
            pass  # not all objects are writable
        else:
            return listener

    return BoundLoopListenerWrapper(loop, listener)


def retrieve_loop_from_listener(listener: ListenerCb[T.Any]) -> T.Optional[AbstractEventLoop]:
    loop: T.Any = getattr(listener, "__loop__", None)

    # This check is mostly redundant. However, the above else clause, may bring user data that may
    # not be an event loop, so check anyway.
    if isinstance(loop, AbstractEventLoop):
        if loop.is_running():
            return loop

        # A stopped event loop means this listener got stale
        raise ListenerStoppedEventLoopError(
            "Attempting to execute a listener bounded to a stopped event loop", loop, listener
        )
    if loop is None:
        return loop

    raise ValueError("__loop__ attribute isn't an T.Optional[AbstractEventLoop]")
