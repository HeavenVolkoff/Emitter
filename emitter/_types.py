# Standard
from enum import Flag, auto, unique
from platform import python_implementation
from collections import OrderedDict, defaultdict
from contextvars import Context
import sys
import typing as T

if T.TYPE_CHECKING:
    # Standard
    from asyncio import AbstractEventLoop

    # Project
    from ._context import context

# Generic types
K = T.TypeVar("K", contravariant=True)

# Python 3.7+ dicts are ordered by default, and they are slightly faster than OrderedDicts
BestDict = (
    dict
    if (
        sys.version_info >= (3, 7)
        or (sys.version_info >= (3, 6) and python_implementation() == "CPython")
    )
    else OrderedDict
)


@unique
class ListenerOpts(Flag):
    NOP = 0
    ONCE = auto()
    RAISE = auto()


class ListenerCb(T.Protocol[K]):
    def __call__(self, __event_data: K) -> T.Optional[T.Awaitable[None]]:
        ...


_types_t = T.MutableMapping[
    type, T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]]
]
_scope_t = T.MutableMapping[T.Tuple[str, ...], _types_t]


class Listeners:
    def __init__(
        self, _scope: T.Optional[_scope_t] = None, _context: T.Optional["context"] = None
    ) -> None:
        self.scope: T.Final[_scope_t] = _scope or defaultdict(lambda: defaultdict(BestDict))
        self.context: T.Final[T.Optional["context"]] = _context


@T.runtime_checkable
class Listenable(T.Protocol):
    """A protocol that defines emitter namespaces."""

    __listeners__: Listeners


class BoundLoopListenerWrapper(T.Generic[K]):
    __slots__ = ("__loop__", "listener")

    def __init__(self, loop: "AbstractEventLoop", listener: ListenerCb[K]):
        self.__loop__ = loop
        self.listener: T.Final[ListenerCb[K]] = listener

    def __call__(self, __event_data: K) -> T.Optional[T.Awaitable[None]]:
        return self.listener(__event_data)
