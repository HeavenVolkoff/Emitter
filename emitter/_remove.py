# Internal
import typing as T

# External
import typing_extensions as Te

# Project
from ._types import ListenerCb
from ._helpers import limit_scope, retrieve_listeners_from_namespace

K = T.TypeVar("K")


@T.overload
def remove(
    event_type: Te.Literal[None],
    listener: Te.Literal[None],
    *,
    scope: Te.Literal[None],
    namespace: T.Optional[object] = None,
) -> bool:
    ...


@T.overload
def remove(
    event_type: T.Type[K],
    listener: T.Optional[ListenerCb[K]],
    *,
    scope: T.Optional[str] = None,
    namespace: T.Optional[object] = None,
) -> bool:
    ...


def remove(
    event_type: T.Optional[T.Type[K]],
    listener: T.Optional[ListenerCb[K]],
    *,
    scope: T.Optional[str] = None,
    namespace: T.Optional[object] = None,
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
        listener: Define the listener to be removed.
        event_type: Define from which event types the listeners will be removed.
        scope: Define scope to limit listener removal.
        namespace: Define from which namespace to remove the listener

    Returns:
        Whether any listener removal occurred.

    """
    if namespace is not None:
        listeners = retrieve_listeners_from_namespace(namespace)
    else:
        from ._global import listeners  # type: ignore

    if not listeners:
        return True

    if event_type is None:
        if listener is None and scope is None:
            # Clear all listeners
            listeners.clear()
            return True
        else:
            raise ValueError("Listener or Scope can't be defined without an Event type")

    removal = False
    if listener is not None or scope is not None:
        for listeners_scope, scope_listeners in limit_scope(scope, listeners[event_type].items()):
            if listener:
                # Clear specific listener from scope
                removal = bool(scope_listeners.pop(listener, None)) or removal
                if scope_listeners:
                    continue
                # Clear scope if it became empty

            # Clear all scopes listeners
            del listeners[event_type][listeners_scope]

        if listeners[event_type]:
            return removal
        # Clear event type if it became empty
    else:
        # listener and scope are None
        removal = True

    # Clear all event type listeners
    del listeners[event_type]

    return removal
