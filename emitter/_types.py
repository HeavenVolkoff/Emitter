# Standard
from enum import Flag, auto, unique
from platform import python_implementation
from collections import OrderedDict, defaultdict
from contextvars import Context
import sys
import typing as T

# External
import typing_extensions as Te

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


class ListenerCb(Te.Protocol[K]):
    def __call__(self, __event_data: K) -> T.Optional[T.Awaitable[None]]:
        ...


_scope_t = T.MutableMapping[
    T.Tuple[str, ...], T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]],
]
_types_t = T.MutableMapping[
    type, T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]]
]


class Listeners:
    """Data struct for storing listeners in a Namespace."""

    __slots__ = ("scope", "types", "context")

    def __init__(
        self,
        *,
        _scope: T.Optional[_scope_t] = None,
        _types: T.Optional[_types_t] = None,
        _context: T.Optional["context"] = None,
    ) -> None:
        self.scope: Te.Final[_scope_t] = defaultdict(BestDict) if _scope is None else _scope
        self.types: Te.Final[_types_t] = defaultdict(BestDict) if _types is None else _types
        self.context: Te.Final[T.Optional["context"]] = _context


@Te.runtime_checkable
class Listenable(Te.Protocol):
    """A protocol that defines emitter namespaces."""

    __listeners__: Listeners


class BoundLoopListenerWrapper(T.Generic[K]):
    __slots__ = ("__loop__", "listener")

    def __init__(self, loop: "AbstractEventLoop", listener: ListenerCb[K]):
        self.__loop__ = loop
        self.listener: Te.Final[ListenerCb[K]] = listener

    def __call__(self, __event_data: K) -> T.Optional[T.Awaitable[None]]:
        return self.listener(__event_data)
