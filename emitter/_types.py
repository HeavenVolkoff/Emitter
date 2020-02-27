# Internal
import typing as T
from enum import Flag, auto, unique

# External
import typing_extensions as Te

K = T.TypeVar("K", contravariant=True)


class ListenerCb(Te.Protocol[K]):
    def __call__(self, __event_data: K) -> T.Optional[T.Awaitable[None]]:
        ...


@unique
class HandleMode(Flag):
    """Defines which kind of listener a `emitter.emit` call executed during an event emission"""

    NONE = 0
    """No listener was executed"""

    GLOBAL = auto()
    """Only listeners from the global namespace were executed"""

    NAMESPACE = auto()
    """Only listeners from a specified namespace were executed"""


@unique
class ListenerOpts(Flag):
    NOP = 0
    ONCE = auto()


EmptyScope = tuple()  # type: ignore

ListenersMapping = T.MutableMapping[
    type, T.MutableMapping[T.Tuple[str, ...], T.MutableMapping[ListenerCb[T.Any], ListenerOpts]],
]
