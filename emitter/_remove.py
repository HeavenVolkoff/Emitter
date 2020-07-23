# Standard
import typing as T

# Project
from ._types import ListenerCb
from ._context import CONTEXT, context as emitter_context
from ._helpers import parse_scope, retrieve_listeners_from_namespace

K = T.TypeVar("K")


@T.overload
def remove(
    event: str,
    namespace: object,
    listener: T.Optional[ListenerCb[K]] = None,
    *,
    context: T.Optional[emitter_context] = None,
) -> bool:
    ...


@T.overload
def remove(
    event: T.Optional[T.Type[K]],
    namespace: object,
    listener: T.Optional[ListenerCb[K]] = None,
    *,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    context: T.Optional[emitter_context] = None,
) -> bool:
    ...


def remove(
    event: T.Union[str, None, T.Type[K]],
    namespace: object,
    listener: T.Optional[ListenerCb[K]] = None,
    *,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    context: T.Optional[emitter_context] = None,
) -> bool:
    """Remove listeners, limited by scope, from given event type.

    When no context is provided assumes current context.

    When no event_type and no listener are passed removes all listeners from the given namespace
    and context.

    When no event_type is specified but a listener is given removes all references to the listener,
    whetever scoped or typed, from the given namespace and context.

    When both event and listener are specified, remove only the correspondent match from the given
    namespace and context.

    Raises:

        ValueError: event_type is None, but scope or listener are not.

    Args:

        event: Define from which event types the listeners will be removed.

        namespace: Define from which namespace to remove the listener

        scope: Specify scope for limiting the removal of listeners.

        listener: Define the listener to be removed.

        context: Define context to restrict listener removal

    Returns:

        Boolean indicating whether any listener removal occurred.

    """
    if isinstance(event, str):
        assert scope == ""
        scope = parse_scope(event)
        event = None
    else:
        scope = parse_scope(scope)

    if context is None:
        context = CONTEXT.get()

    scopes = tuple(retrieve_listeners_from_namespace(namespace).scope.items())
    removed = False
    if not (listener is None or event is None):
        for type_scope, types in scopes:
            if type_scope < scope or event not in types:
                continue

            listeners = types[event]
            if listener not in listeners:
                continue

            _, ctx = listeners[listener]
            if ctx[CONTEXT] not in context:
                continue

            del listeners[listener]
            removed = True

        return removed

    if listener is None and event is not None:
        for type_scope, types in scopes:
            if type_scope < scope or event not in types:
                continue

            listeners = types[event]
            for (listener, (_, ctx)) in tuple(listeners.items()):
                if ctx[CONTEXT] not in context:
                    continue

                del listeners[listener]
                removed = True

        return removed

    if event is None and listener is not None:
        for type_scope, types in scopes:
            if type_scope < scope:
                continue

            for event, listeners in tuple(types.items()):
                if listener not in listeners:
                    continue

                _, ctx = listeners[listener]
                if ctx[CONTEXT] not in context:
                    continue

                del listeners[listener]
                removed = True

        return removed

    for type_scope, types in scopes:
        if type_scope < scope:
            continue

        for event, listeners in tuple(types.items()):
            listeners = types[event]
            for (listener, (_, ctx)) in tuple(listeners.items()):
                if ctx[CONTEXT] not in context:
                    continue

                del listeners[listener]
                removed = True

    return removed
