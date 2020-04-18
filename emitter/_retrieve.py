# Internal
import typing as T

# Project
from ._types import ListenerCb
from ._helpers import retrieve_listeners_from_namespace

K = T.TypeVar("K")


def retrieve(event: T.Union[str, T.Type[K]], namespace: object) -> T.Sequence[ListenerCb[K]]:
    """Retrieve all listeners, limited by scope, registered to the given event type.

    Arguments:
        event: Define from which event types the listeners will be retrieve.
        namespace: Define from which namespace to retrieve the listeners

    Returns:
        A `Sequence` containing all listeners attached to given event type, limited by the given \
        scope

    """
    listeners = retrieve_listeners_from_namespace(namespace)

    if isinstance(event, str):
        if event == "":
            raise ValueError("Event scope must be a valid string")

        scope = tuple(event.split("."))
        return tuple(
            listener
            for step in range(-1, len(scope))
            for listener, _ in listeners.scope[scope[: (step + 1)]].items()
        )
    else:
        if issubclass(event, BaseException) and not issubclass(event, Exception):
            raise ValueError("Event type can't be a BaseException")

        if not isinstance(event, type) or issubclass(event, type):
            raise ValueError("Event type must be an instance of type")

        return tuple(listener for listener, _ in listeners.types[event].items())
