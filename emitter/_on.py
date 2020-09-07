# Standard
from asyncio import AbstractEventLoop, get_running_loop
from inspect import iscoroutinefunction
from contextlib import suppress, nullcontext, contextmanager
from contextvars import copy_context
import typing as T

# Project
from ._emit import emit
from ._types import ListenerCb, NewListener, ListenerOpts, BoundLoopListenerWrapper
from ._helpers import parse_scope, retrieve_listeners_from_namespace

# Type generics
K = T.TypeVar("K")


@T.overload
def on(
    event_type: T.Union[T.Type[K], T.Type[object]],
    namespace: object,
    listener: T.Literal[None] = None,
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    raise_on_exc: bool = False,
) -> T.Callable[[ListenerCb[K]], ListenerCb[K]]:
    ...


@T.overload
def on(
    event_type: T.Union[T.Type[K], T.Type[object]],
    namespace: object,
    listener: ListenerCb[K],
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    raise_on_exc: bool = False,
) -> ListenerCb[K]:
    ...


def on(
    event_type: T.Union[T.Type[K], T.Type[object]],
    namespace: object,
    listener: T.Optional[ListenerCb[K]] = None,
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    raise_on_exc: bool = False,
) -> T.Union[ListenerCb[K], T.ContextManager[None], T.Callable[[ListenerCb[K]], ListenerCb[K]]]:
    """Add a listener to event type.

    Context can't be specified when using this function in decorator mode.
    Context can't be specified when passing once=True.

    Args:

        event_type: Specify which event type or scope namespace will trigger this listener execution.

        namespace: Specify the namespace in which the listener will be attached.

        listener: Callable to be executed when there is an emission of the given event.

        once: Define whether the given listener is to be removed after it's first execution.

        loop: Specify a loop to bound to the given listener and ensure it is always executed in the
              correct context. (Default: Current running loop for coroutines functions, None for
              any other callable)

        scope: Specify a scope for specializing this listener registration.

        raise_on_exc: Whether an untreated exception raised by this listener will make an event
                      emission to fail.

    Raises:

        TypeError: Failed to bound loop to listener.

        ValueError: event_type is not a type instance, or it is a builtin type, or it is
                    BaseExceptions or listener is not callable.

    Returns:

        If listener isn't provided, this method returns a function that takes a Callable as a \
        single argument. As such it can be used as a decorator. In both the decorated and \
        undecorated forms this function returns the given event listener.

    """

    if listener is None:
        return lambda cb: on(
            event_type,
            namespace,
            cb,
            once=once,
            loop=loop,
            scope=scope,
            raise_on_exc=raise_on_exc,
        )

    if not callable(listener):
        raise ValueError("Listener must be callable")

    scope = parse_scope(scope)

    # Define listeners options
    opts = ListenerOpts.NOP
    if once:
        opts |= ListenerOpts.ONCE
    if raise_on_exc:
        opts |= ListenerOpts.RAISE

    if loop is None and iscoroutinefunction(listener):
        # Automatically set loop for Coroutines to avoid problems with emission from another thread
        with suppress(RuntimeError):
            loop = get_running_loop()

    if loop:
        listener = BoundLoopListenerWrapper(loop, listener)

    # Retrieve listeners
    listeners = retrieve_listeners_from_namespace(namespace)

    # Group listener's opts and context
    with (
        nullcontext(listeners.context)
        if listeners.context is None or listeners.context.active
        else listeners.context
    ):
        listener_info = (opts, copy_context())

    # Add the given listener to the correct queue
    if event_type is None:
        raise ValueError("Event type can't be NoneType")
    elif issubclass(event_type, type):
        # Event type must be a class. Reject Metaclass and cia.
        raise ValueError("Event type must be an concrete type")
    elif issubclass(event_type, BaseException) and not issubclass(event_type, Exception):
        raise ValueError("Event type can't be a BaseException")
    else:
        listeners.scope[scope][event_type][listener] = listener_info

    if event_type is not NewListener:
        emit(NewListener(event_type), namespace, sync=True, scope=scope)

    return listener


@contextmanager
def on_context(
    event_type: T.Union[T.Type[K], T.Type[object]],
    namespace: object,
    listener: ListenerCb[K],
    *,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    raise_on_exc: bool = False,
) -> T.Iterator[None]:
    from . import remove

    on(
        event_type,
        namespace,
        listener,
        once=False,
        loop=loop,
        scope=scope,
        raise_on_exc=raise_on_exc,
    )

    try:
        yield
    finally:
        remove(event_type, namespace, listener)
