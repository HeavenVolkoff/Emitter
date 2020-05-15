# Internal
import sys
import typing as T
from enum import Flag, auto, unique
from uuid import UUID
from platform import python_implementation
from collections import OrderedDict, defaultdict
from contextvars import Context

# External
import typing_extensions as Te

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


class Listeners:
    """Data struct for storing listeners in a Namespace."""

    __slots__ = ("scope", "types")

    def __init__(self) -> None:
        self.scope: Te.Final[
            T.MutableMapping[
                T.Tuple[str, ...],
                T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]],
            ]
        ] = defaultdict(BestDict)
        self.types: Te.Final[
            T.MutableMapping[
                type, T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]]
            ]
        ] = defaultdict(BestDict)


@Te.runtime_checkable
class Listenable(Te.Protocol):
    """A protocol that defines emitter namespaces."""

    __listeners__: Listeners
