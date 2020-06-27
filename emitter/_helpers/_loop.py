# Standard
from asyncio import AbstractEventLoop
import typing as T

# Project
from ..error import ListenerStoppedEventLoopError
from .._types import ListenerCb

try:
    from asyncio import get_running_loop
except ImportError:
    from asyncio import _get_running_loop

    # Polyfill of get_running_loop for cpython 3.6
    def get_running_loop() -> AbstractEventLoop:
        loop = _get_running_loop()
        if loop:
            return loop
        raise RuntimeError("no running event loop")


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
