# Internal
import typing as T

# Project
from ._types import ListenerCb
from ._helpers import limit_scope, retrieve_listeners_from_namespace

K = T.TypeVar("K")


def retrieve(
    event_type: T.Type[K], *, scope: T.Optional[str] = None, namespace: T.Optional[object] = None,
) -> T.Sequence[ListenerCb[K]]:
    """Retrieve all listeners, limited by scope, registered to the given event type.

    Arguments:
        event_type: Define from which event types the listeners will be retrieve.
        scope: Define scope to limit listeners retrieval.
        namespace: Define from which namespace to retrieve the listeners

    Returns:
        A `Sequence` containing all listeners attached to given event type, limited by the given \
        scope

    """
    if namespace is not None:
        listeners = retrieve_listeners_from_namespace(namespace)
    else:
        from ._global import listeners  # type: ignore

    return tuple(
        listener
        for _, listener in limit_scope(
            scope,
            (
                (listeners_scope, listener)
                for listeners_scope, listeners in listeners[event_type].items()
                for listener in listeners
            ),
        )
    )
