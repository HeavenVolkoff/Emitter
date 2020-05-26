# Standard
import typing as T


class EmitterError(Exception):
    """Base exception for Emitter related errors."""


class ListenerEventLoopError(EmitterError, RuntimeError):
    """Attempt to execute a listener bounded to a stopped event loop."""


class ListenerStoppedEventLoopError(ListenerEventLoopError):
    """Attempt to execute a listener bounded to a stopped event loop."""


__all__ = ("EmitterError", "ListenerEventLoopError", "ListenerStoppedEventLoopError")
