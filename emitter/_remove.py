# Internal
import typing as T

# External
import typing_extensions as Te

# Project
from ._types import ListenerCb
from ._helpers import retrieve_listeners_from_namespace

K = T.TypeVar("K")


@T.overload
def remove(event: Te.Literal[None], namespace: object, listener: Te.Literal[None] = None) -> bool:
    ...


@T.overload
def remove(
    event: T.Union[str, T.Type[K]], namespace: object, listener: T.Optional[ListenerCb[K]]
) -> bool:
    ...


def remove(
    event: T.Union[str, None, T.Type[K]],
    namespace: object,
    listener: T.Optional[ListenerCb[K]] = None,
) -> bool:
    """Remove listeners, limited by scope, from given event type.

    No event_type, which also assumes no scope and listener, results in the removal of all
    listeners from the given namespace (`None` means global).

    No scope and listener, results in the removal of all listeners of the specified event from the
    given namespace (`None` means global).

    No scope, results in the removal of given listener from all scopes of the specified event from
    the given namespace (`None` means global).

    An event_type, listener and scope, results in the removal of given listener from this scope of
    the specified event from the given namespace (`None` means global).

    Raises:
        ValueError: event_type is None, but scope or listener are not.

    Arguments:
        event: Define from which event types the listeners will be removed.
        listener: Define the listener to be removed.
        namespace: Define from which namespace to remove the listener

    Returns:
        Whether any listener removal occurred.

    """
    listeners = retrieve_listeners_from_namespace(namespace)

    if event is None:
        if listener is None:
            # Clear all listeners
            removed = bool(listeners.scope) or bool(listeners.types)
            listeners.scope.clear()
            listeners.types.clear()
            return removed
        else:
            raise ValueError("Listener can't be defined without an Event type or scope")

    removed = False

    if isinstance(event, str):
        if event == "":
            raise ValueError("Event scope must be a valid string")

        scope = tuple(event.split("."))
        for listener_scope, scoped_listeners in tuple(listeners.scope.items()):
            if scope > listener_scope:
                continue

            if listener is None:
                removed = removed or bool(scoped_listeners)
                listeners.scope[listener_scope].clear()
            elif listener in scoped_listeners:
                removed = True
                del scoped_listeners[listener]

        return removed

    if event in listeners.types:
        if listener is None:
            removed = bool(listeners.types[event])
            listeners.types[event].clear()
        elif listener in listeners.types[event]:
            removed = True
            del listeners.types[event][listener]

    return removed
