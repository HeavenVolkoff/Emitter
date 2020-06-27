# Standard
from asyncio import AbstractEventLoop
from inspect import iscoroutinefunction
from contextlib import suppress, contextmanager
from contextvars import copy_context
import typing as T

# External
import typing_extensions as Te

# Project
from ._types import ListenerCb, ListenerOpts, BoundLoopListenerWrapper
from ._helpers import parse_scope, get_running_loop, retrieve_listeners_from_namespace

# Type generics
K = T.TypeVar("K")

try:
    from contextlib import nullcontext
except ImportError:
    # Required for Python < 3.7
    @contextmanager  # type: ignore[no-redef]
    def nullcontext(enter_result: T.Optional[K] = None) -> T.Generator[T.Optional[K], None, None]:
        yield enter_result


@T.overload
def on(
    event: str,
    namespace: object,
    listener: Te.Literal[None] = None,
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    raise_on_exc: bool = False,
) -> T.Callable[[ListenerCb[K]], ListenerCb[K]]:
    ...


@T.overload
def on(
    event: str,
    namespace: object,
    listener: ListenerCb[K],
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    raise_on_exc: bool = False,
) -> ListenerCb[K]:
    ...


@T.overload
def on(
    event: T.Type[K],
    namespace: object,
    listener: Te.Literal[None] = None,
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    raise_on_exc: bool = False,
) -> T.Callable[[ListenerCb[K]], ListenerCb[K]]:
    ...


@T.overload
def on(
    event: T.Type[K],
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
    event: T.Union[str, T.Type[K]],
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

        event: Specify which event type or scope namespace will trigger this listener execution.

        namespace: Specify the namespace in which the listener will be attached.

        listener: Callable to be executed when there is an emission of the given event.

        once: Define whether the given listener is to be removed after it's first execution.

        loop: Specify a loop to bound to the given listener and ensure it is always executed in the
              correct context. (Default: Current running loop for coroutines functions, None for
              any other callable)

        scope: TODO

        context: Return a context for management of this listener lifecycle.

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
            event,  # type: ignore[arg-type]
            namespace,
            cb,
            once=once,
            loop=loop,
            scope=scope,  # FIX-ME: ignore on top is due to missing Literal[()] support
            raise_on_exc=raise_on_exc,
        )

    if isinstance(event, str):
        assert scope == ""
        scope = parse_scope(event)
        event = T.cast(T.Type[K], object)
    else:
        scope = parse_scope(scope)

    if not callable(listener):
        raise ValueError("Listener must be callable")

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
    if event is None:
        raise ValueError("Event type can't be NoneType")
    elif issubclass(event, type):
        # Event type must be a class. Reject Metaclass and cia.
        raise ValueError("Event type must be an concrete type")
    elif event is object and not scope:
        raise ValueError("Event type can't be object without a scope, too generic")
    elif issubclass(event, BaseException) and not issubclass(event, Exception):
        raise ValueError("Event type can't be a BaseException")
    else:
        listeners.scope[scope][event][listener] = listener_info

    return listener


@contextmanager
def on_context(
    event: T.Union[str, T.Type[K]],
    namespace: object,
    listener: ListenerCb[K],
    *,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
    raise_on_exc: bool = False,
) -> T.Iterator[None]:
    from . import remove

    on(
        event,  # type: ignore[arg-type]
        namespace,
        listener,
        once=False,
        loop=loop,
        scope=scope,  # FIX-ME: ignore on top is due to missing Literal[()] support
        raise_on_exc=raise_on_exc,
    )

    try:
        yield
    finally:
        remove(event, namespace, listener)
