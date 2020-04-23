# Internal
import typing as T
from asyncio import Task, Future, CancelledError, AbstractEventLoop, ensure_future

# External
import typing_extensions as Te

# Project
from ._types import Listeners, ListenerCb, ListenerOpts
from .errors import ListenerEventLoopError, ListenerStoppedEventLoopError
from ._helpers import (
    get_running_loop,
    retrieve_loop_from_listener,
    retrieve_listeners_from_namespace,
)

# Type generics
K = T.TypeVar("K", contravariant=True)


def _exec_listener(
    listener: ListenerCb[K],
    event_instance: K,
    listener_loop: AbstractEventLoop,
    loop: T.Optional[AbstractEventLoop],
    result_future: "Future[None]",
) -> None:
    awaitable = listener(event_instance)

    try:
        listener_future = ensure_future(T.cast(T.Awaitable[None], awaitable), loop=listener_loop)
    except ValueError:
        raise ListenerEventLoopError(
            "Incompatible Event loop used in awaitable returned by listener"
        )
    except TypeError:
        # Not an awaitable, resolve future
        if loop:
            loop.call_soon_threadsafe(result_future.set_result, None)
        else:
            result_future.set_result(None)
        return

    @listener_future.add_done_callback
    def _handle_listener_future(listener_future: "Future[None]") -> None:
        try:
            result = listener_future.result()
        except CancelledError:
            # Ignore listener future cancellation
            if loop:
                loop.call_soon_threadsafe(result_future.set_result, None)
            else:
                result_future.set_result(None)
            raise
        except Exception as exc:
            if loop:
                loop.call_soon_threadsafe(result_future.set_exception, exc)
            else:
                result_future.set_exception(exc)
        except BaseException:
            # Don't redirect BaseException, it must be handled by the other loop
            # Cancel our future, to report that something went very wrong
            if loop:
                loop.call_soon_threadsafe(result_future.cancel)
            else:
                result_future.cancel()
            raise
        else:
            if loop:
                loop.call_soon_threadsafe(result_future.set_result, result)
            else:
                result_future.set_result(result)


def _exec_listener_thread_safe(
    loop: AbstractEventLoop, listener: ListenerCb[K], event_instance: K
) -> "Future[None]":
    listener_loop = retrieve_loop_from_listener(listener) or loop

    if not listener_loop.is_running():
        # A stopped event loop means this listener got stale
        raise ListenerStoppedEventLoopError(
            "Attempting to execute a listener bounded to a stopped event loop",
            listener_loop,
            listener,
        )

    # Create an internal future to better control the listener result
    result_future = loop.create_future()
    if listener_loop is loop:
        # Same loop means same thread, so just execute the listener
        _exec_listener(listener, event_instance, listener_loop, None, result_future)
    else:
        # A different running loop means another thread
        @listener_loop.call_soon_threadsafe
        def _handle_different_loop() -> None:
            try:
                _exec_listener(listener, event_instance, listener_loop, loop, result_future)
            except Exception as exc:
                loop.call_soon_threadsafe(result_future.set_exception, exc)
            except BaseException:
                # Don't redirect BaseException, it must be handled by the other loop
                # Cancel our future, to report that something went very wrong
                loop.call_soon_threadsafe(result_future.cancel)
                raise

    return result_future


async def _exec_listeners(
    listeners: T.Sequence[T.Tuple[ListenerCb[K], ListenerOpts]], event_instance: K,
) -> bool:
    loop = get_running_loop()
    listener: T.Optional[ListenerCb[K]] = None
    for listener, opts in listeners:
        try:
            await _exec_listener_thread_safe(loop, listener, event_instance)
        except CancelledError:
            raise
        except Exception as exc:
            # Second tier exception aren't treatable to avoid recursion
            if not isinstance(event_instance, Exception):
                try:
                    # Emit an event to attempt treating the exception
                    await emit(exc, namespace=listener)
                except CancelledError:
                    raise
                except Exception as inner_exc:
                    if inner_exc is not exc:
                        exc.__context__ = inner_exc
                else:
                    continue

            # Warn about unhandled exceptions
            loop.call_exception_handler(
                {"message": "Unhandled exception during event emission", "exception": exc}
            )

    # Whether the previous iteration assigned the listener variable determines if a listener was
    # executed or not
    if listener is not None:
        return True
    elif isinstance(event_instance, Exception):
        # When event_instance is an exception, and it is not handled, raise it back to user
        # context
        raise event_instance

    return False


def _clear_once(
    filtered_listeners: T.Sequence[T.Tuple[ListenerCb[T.Any], ListenerOpts]],
    listeners: T.MutableMapping[ListenerCb[T.Any], ListenerOpts],
) -> None:
    for listener, listener_opts in filtered_listeners:
        if listener_opts & ListenerOpts.ONCE:
            del listeners[listener]


def _retrieve_listeners(
    listeners: Listeners, event_instance: K, scope: T.Optional[T.Tuple[str, ...]]
) -> T.Sequence[T.Tuple[ListenerCb[K], ListenerOpts]]:
    event_type = type(event_instance)

    if isinstance(event_instance, BaseException) and not isinstance(event_instance, Exception):
        # Bare instance of BaseException are re-raised.
        # Handling bare BaseExceptions could prevent normal behaviour of the interpreter on certain
        # situations.
        raise event_instance

    if not isinstance(event_type, type) or issubclass(event_type, type):
        # Event type must be a class. Reject Metaclass and cia.
        raise ValueError("Event type must be an instance of type")

    if event_type is object:
        # Object is too generic, it would cause unexpected behaviour.
        raise ValueError("Event type can't be object, must be a subclass of it")

    functions: T.List[T.Tuple[ListenerCb[K], ListenerOpts]] = []
    for event_supertype in reversed(event_type.mro()[1:]):
        if event_instance is object or event_instance is BaseException:
            continue

        mro_listeners = listeners.types[event_supertype]
        filtered_mao_listeners = tuple(mro_listeners.items())
        _clear_once(filtered_mao_listeners, mro_listeners)
        functions += filtered_mao_listeners

    type_listeners = listeners.types[event_type]
    filtered_type_listeners = tuple(type_listeners.items())
    _clear_once(filtered_type_listeners, type_listeners)
    functions += filtered_type_listeners

    if scope:
        for step in range(-1, len(scope)):
            scoped_listeners = listeners.scope[scope[: (step + 1)]]
            filtered_scoped_listeners = tuple(scoped_listeners.items())
            _clear_once(filtered_scoped_listeners, scoped_listeners)
            functions += filtered_scoped_listeners

    return tuple(functions)


@T.overload
def emit(
    event_instance: object, namespace: object, *, loop: AbstractEventLoop, scope: str = "",
) -> T.Optional["Task[bool]"]:
    ...


@T.overload
def emit(
    event_instance: object, namespace: object, *, loop: Te.Literal[None] = None, scope: str = "",
) -> T.Coroutine[None, None, bool]:
    ...


def emit(
    event_instance: object,
    namespace: object,
    *,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: str = "",
) -> T.Union[None, "Task[bool]", T.Coroutine[None, None, bool]]:
    """Emit an event, and execute its listeners.

    Arguments:
        event_instance: Event instance to be emitted.
        namespace: Specify a listener namespace to emit this event.
        loop: Define loop to run event emission
        scope: Define till which scopes this event will execute its listeners.

    Raises:
        ValueError: event_instance is an instance of a builtin type, or it is a type instead of an
                    instance.
        BaseException: Re-raise event instance if it is a BaseException.
        CancelledError: Raised whenever the loop (or something) cancels this coroutine.

    Returns:
        Coroutine or awaitable representing the event emission

    """
    namespace_listeners = _retrieve_listeners(
        retrieve_listeners_from_namespace(namespace),
        event_instance,
        tuple(scope.split(".")) if scope else None,
    )

    coro = _exec_listeners(namespace_listeners, event_instance)

    if loop is None:
        return coro

    if namespace:
        return loop.create_task(coro)

    return None
