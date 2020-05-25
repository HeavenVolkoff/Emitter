# Standard
from contextvars import Context
import typing as T

# Project
from ._types import Listeners, ListenerCb, ListenerOpts
from ._context import CONTEXT, context as emitter_context
from ._helpers import retrieve_listeners_from_namespace

K = T.TypeVar("K")


def _remove_context_listener(
    context: emitter_context,
    listener: ListenerCb[K],
    listeners: T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]],
) -> bool:
    if listener not in listeners:
        return False

    _, ctx = listeners[listener]
    if ctx[CONTEXT] not in context:
        return False

    del listeners[listener]
    return True


def _remove_context_listeners(
    context: emitter_context,
    listeners: T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]],
) -> bool:
    removed = False

    for (listener, (_, ctx)) in tuple(listeners.items()):
        if ctx[CONTEXT] in context:
            removed = True
            del listeners[listener]

    return removed


def _remove_all_context_listeners(context: emitter_context, listeners: Listeners) -> bool:
    removed = False
    for _, event_listeners in listeners.types.items():
        removed = _remove_context_listeners(context, event_listeners) or removed

    for _, scoped_listeners in listeners.scope.items():
        removed = _remove_context_listeners(context, scoped_listeners) or removed

    return removed


def _remove_scoped_context_listener(
    scope: T.Tuple[str, ...],
    context: emitter_context,
    listener: ListenerCb[K],
    listeners: T.MutableMapping[
        T.Tuple[str, ...], T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]],
    ],
) -> bool:
    removed = False
    for step in range(len(scope), 0, -1):
        removed = (
            _remove_context_listener(context, listener, listeners[scope[: (step + 1)]]) or removed
        )

    return removed


def _remove_all_scoped_context_listener(
    scope: T.Tuple[str, ...],
    context: emitter_context,
    listeners: T.MutableMapping[
        T.Tuple[str, ...], T.MutableMapping[ListenerCb[T.Any], T.Tuple[ListenerOpts, Context]],
    ],
) -> bool:
    removed = False
    for listener_scope, scoped_listeners in listeners.items():
        if scope > listener_scope:
            continue

        removed = _remove_context_listeners(context, scoped_listeners) or removed

    return removed


def remove(
    event: T.Union[str, None, T.Type[K]],
    namespace: object,
    listener: T.Optional[ListenerCb[K]] = None,
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

        listener: Define the listener to be removed.

        namespace: Define from which namespace to remove the listener

        context: Define context to restrict listener removal

    Returns:

        Boolean indicating whether any listener removal occurred.

    """
    listeners = retrieve_listeners_from_namespace(namespace)

    if context is None:
        context = listeners.context or CONTEXT.get()

    if event is None:
        if listener is None:
            return _remove_all_context_listeners(context, listeners)

        removed = False
        for scoped_listeners in listeners.scope.values():
            removed = _remove_context_listener(context, listener, scoped_listeners) or removed

        for typed_listeners in listeners.types.values():
            removed = _remove_context_listener(context, listener, typed_listeners) or removed

        return removed
    elif isinstance(event, str):
        if event == "":
            raise ValueError("Event scope must be a valid string")

        scope = tuple(event.split("."))
        return (
            _remove_all_scoped_context_listener(scope, context, listeners.scope)
            if listener is None
            else _remove_scoped_context_listener(scope, context, listener, listeners.scope)
        )
    elif event in listeners.types:
        typed_listeners = listeners.types[event]
        return (
            _remove_context_listeners(context, typed_listeners)
            if listener is None
            else _remove_context_listener(context, listener, typed_listeners)
        )
    return False
