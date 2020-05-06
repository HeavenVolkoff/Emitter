# Internal
import typing as T
from asyncio import AbstractEventLoop, iscoroutinefunction
from contextlib import contextmanager

# External
import typing_extensions as Te

# Project
from ._types import ListenerCb, ListenerOpts
from ._helpers import get_running_loop, bound_loop_to_listener, retrieve_listeners_from_namespace

# Type generics
K = T.TypeVar("K")


@contextmanager
def _context(
    event: T.Union[str, T.Type[K]], namespace: object, listener: ListenerCb[K], raise_on_exc: bool
) -> T.Generator[None, None, None]:
    from . import remove

    on(event, namespace, listener, raise_on_exc=raise_on_exc)

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

    Arguments:
        event: Event type to attach the listener to.
        namespace: Specify which listeners namespace to attach the given event listener.
                   (Default: Global namespace)
        listener: Callable to be executed when there is an emission of the given event type.
        once: Define whether the given listener is to be removed after it's first execution.
        loop: Specify a loop to bound to the given listener and ensure it is always executed in the
              correct context. (Default: Current running loop for coroutines functions, None for
              any other callable)
        context: Return a context for easy management of this listener lifecycle
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
        return lambda cb: on(event, namespace, cb, once=once, loop=loop, raise_on_exc=raise_on_exc)

    if context:
        if once:
            raise ValueError("Can't use context manager with a once listener")
        return _context(event, namespace, listener, raise_on_exc=raise_on_exc)

    if event is object:
        raise ValueError("Event type can't be object, too generic")

    if isinstance(event, str):
        if event == "":
            raise ValueError("Event scope must be a valid string")

        scope: T.Optional[T.Tuple[str, ...]] = tuple(event.split("."))
    else:
        if issubclass(event, BaseException) and not issubclass(event, Exception):
            raise ValueError("Event type can't be a BaseException")

        if not isinstance(event, type) or issubclass(event, type):
            raise ValueError("Event type must be an instance of type")

        scope = None

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
        try:
            loop = get_running_loop()
        except RuntimeError:
            loop = None

    if loop:
        listener = bound_loop_to_listener(listener, loop)

    # Retrieve listeners
    listeners = retrieve_listeners_from_namespace(namespace)

    # Add the given listener to the correct queue
    if scope:
        listeners.scope[scope][listener] = opts
    else:
        assert isinstance(event, type)
        listeners.types[event][listener] = opts

    return listener
