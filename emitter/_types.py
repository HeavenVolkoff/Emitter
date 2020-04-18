# Internal
import sys
import typing as T
from enum import Flag, auto, unique
from platform import python_implementation
from collections import OrderedDict, defaultdict

# External
import typing_extensions as Te

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


class ListenerCb(Te.Protocol[K]):
    def __call__(self, __event_data: K) -> T.Optional[T.Awaitable[None]]:
        ...


class Listeners:
    __slots__ = ("scope", "types")

    def __init__(self) -> None:
        self.scope: T.MutableMapping[
            T.Tuple[str, ...], T.MutableMapping[ListenerCb[T.Any], ListenerOpts]
        ] = defaultdict(BestDict)
        self.types: T.MutableMapping[
            type, T.MutableMapping[ListenerCb[T.Any], ListenerOpts]
        ] = defaultdict(BestDict)
