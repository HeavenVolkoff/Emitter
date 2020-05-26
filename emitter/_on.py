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
from ._helpers import get_running_loop, retrieve_listeners_from_namespace

# Type generics
K = T.TypeVar("K")

nullcontext: T.Callable[[], T.ContextManager[K]]
try:
    from contextlib import nullcontext  # type: ignore
except ImportError:
    # Python < 3.7
    @contextmanager
    def nullcontext(enter_result: T.Optional[K] = None) -> T.Generator[T.Optional[K], None, None]:
        yield enter_result


@contextmanager
def _context(
    loop: T.Optional[AbstractEventLoop],
    event: T.Union[str, T.Type[K]],
    listener: ListenerCb[K],
    namespace: object,
    raise_on_exc: bool,
) -> T.Generator[None, None, None]:
    from . import remove

    on(event, namespace, listener, once=False, loop=loop, context=False, raise_on_exc=raise_on_exc)

    try:
        yield
    finally:
        remove(event, namespace, listener)


@T.overload
def on(
    event: T.Union[str, T.Type[K]],
    namespace: object,
    listener: Te.Literal[None] = None,
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    context: Te.Literal[False] = False,
    raise_on_exc: bool = False,
) -> T.Callable[[ListenerCb[K]], ListenerCb[K]]:
    ...


@T.overload
def on(
    event: T.Union[str, T.Type[K]],
    namespace: object,
    listener: ListenerCb[K],
    *,
    once: Te.Literal[False] = False,
    loop: T.Optional[AbstractEventLoop] = None,
    context: Te.Literal[True],
    raise_on_exc: bool = False,
) -> T.ContextManager[None]:
    ...


@T.overload
def on(
    event: T.Union[str, T.Type[K]],
    namespace: object,
    listener: ListenerCb[K],
    *,
    once: bool = False,
    loop: T.Optional[AbstractEventLoop] = None,
    context: Te.Literal[False] = False,
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
    context: bool = False,
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
        if context:
            raise ValueError("Can't use context manager without a listener defined")
        # Decorator behaviour
        return lambda cb: on(
            event, namespace, cb, once=once, loop=loop, context=False, raise_on_exc=raise_on_exc
        )

    if context:
        if once:
            raise ValueError("Can't use context manager with a once listener")
        return _context(loop, event, listener, namespace, raise_on_exc)

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
        nullcontext()
        if listeners.context is None or listeners.context.active
        else listeners.context
    ):
        listener_info = (opts, copy_context())

    # Add the given listener to the correct queue
    if isinstance(event, str):
        if event == "":
            raise ValueError("Event scope must be a valid string")
        listeners.scope[tuple(event.split("."))][listener] = listener_info
    elif event is None:
        raise ValueError("Event type can't be NoneType")
    elif event is object:
        raise ValueError("Event type can't be object, too generic")
    elif issubclass(event, BaseException) and not issubclass(event, Exception):
        raise ValueError("Event type can't be a BaseException")
    elif issubclass(event, type):
        # Event type must be a class. Reject Metaclass and cia.
        raise ValueError("Event type must be an instance of type")
    else:
        listeners.types[event][listener] = listener_info

    return listener
