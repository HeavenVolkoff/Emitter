# Standard
from asyncio import Task, Future, CancelledError, AbstractEventLoop, ensure_future
from functools import partial
from contextvars import Context
import typing as T

# External
import typing_extensions as Te

# Project
from .error import ListenerEventLoopError
from ._types import Listeners, ListenerCb, ListenerOpts
from ._helpers import (
    parse_scope,
    get_running_loop,
    retrieve_loop_from_listener,
    retrieve_listeners_from_namespace,
)

# Type generics
K = T.TypeVar("K", contravariant=True)

# Constants
_TO_EXEC_ONCE_IDS: T.Set[int] = set()
_NOT_EXEC_ONCE_SENTINEL = object()


def _exec_listener(
    loop: T.Optional[AbstractEventLoop],
    cancel: T.Callable[[], bool],
    reject: T.Callable[[T.Union[type, BaseException]], None],
    resolve: T.Callable[[None], None],
    listener: ListenerCb[K],
    event_instance: K,
) -> None:
    try:
        awaitable = listener(event_instance)

        try:
            task = ensure_future(T.cast(T.Awaitable[None], awaitable), loop=loop)
        except ValueError:
            reject(
                ListenerEventLoopError(
                    "Incompatible Event loop used in awaitable returned by listener"
                )
            )
            return
        except TypeError:  # Listener result isn't an awaitable
            resolve(T.cast(None, awaitable))
            return
    except Exception as exc:
        reject(exc)
        return
    except BaseException:
        # Don't bubble up BaseException
        cancel()
        raise

    @task.add_done_callback
    def _handle_listener_future(listener_future: "Future[None]") -> None:
        try:
            listener_future.result()
        except CancelledError:
            # Don't bubble up task-only cancellation
            resolve(None)
            raise
        except Exception as exc:
            reject(exc)
        except BaseException:
            # Don't bubble up BaseException
            cancel()
            raise
        else:
            resolve(None)


def _exec_listener_thread_safe(
    loop: AbstractEventLoop, listener: ListenerCb[K], context: Context, event_instance: K
) -> "Future[None]":
    # Create an internal future to better control the listener result
    result_future: "Future[None]" = loop.create_future()
    listener_loop = retrieve_loop_from_listener(listener) or loop
    if loop is listener_loop:
        context.run(
            _exec_listener,
            loop,
            result_future.cancel,
            result_future.set_exception,
            result_future.set_result,
            listener,
            event_instance,
        )
    else:
        listener_loop.call_soon_threadsafe(
            context.run,
            _exec_listener,
            listener_loop,
            partial(loop.call_soon_threadsafe, result_future.cancel),
            partial(loop.call_soon_threadsafe, result_future.set_exception),
            partial(loop.call_soon_threadsafe, result_future.set_result),
            listener,
            event_instance,
        )

    return result_future


async def _exec_listeners(
    listeners: T.Sequence[T.Tuple[ListenerCb[K], T.Tuple[ListenerOpts, Context]]],
    event_instance: K,
) -> bool:
    loop = get_running_loop()
    handled = False
    for listener, (opts, context) in listeners:
        result = None
        try:
            result = await _exec_listener_thread_safe(loop, listener, context, event_instance)
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

            if opts & ListenerOpts.RAISE:
                raise exc
            else:
                # Warn about unhandled exceptions
                loop.call_exception_handler(
                    {"message": "Unhandled exception during event emission", "exception": exc}
                )
        finally:
            handled = handled or (result is not _NOT_EXEC_ONCE_SENTINEL)

    if not handled and isinstance(event_instance, Exception):
        # When event_instance is an exception, and it is not handled, raise it back to user
        # context
        raise event_instance

    return handled


def _wrap_clear_once(
    listeners: T.MutableMapping[ListenerCb[K], T.Tuple[ListenerOpts, Context]],
    listener: ListenerCb[K],
) -> ListenerCb[K]:
    # Save listener identity to indicate that it still has to be executed
    _TO_EXEC_ONCE_IDS.add(id(listeners))

    def _clear_once(event: K) -> T.Optional[T.Awaitable[None]]:
        listener_id = id(listeners)
        if listener_id in _TO_EXEC_ONCE_IDS:
            # Listener identity is still present in TO_EXEC, so it was not executed yet.
            # Remove identity from TO_EXEC to indicate that we will execute this listener.
            _TO_EXEC_ONCE_IDS.remove(listener_id)

            # Check whether listener is still in listeners mapping.
            # Even if the execution of the listener still didn't happen it could have been
            # removed by the user in the interim.
            if listener in listeners:
                # Remove the listener from mapping as we are going to execute it
                del listeners[listener]

            # Exec listener
            return listener(event)

        # Sentinel to indicate to `_exec_listeners` that this listener wasn't really executed
        return _NOT_EXEC_ONCE_SENTINEL  # type: ignore[return-value]

    if hasattr(listener, "__loop__"):
        setattr(_clear_once, "__loop__", getattr(listener, "__loop__"))

    return _clear_once


def _handle_once(
    listeners: T.MutableMapping[ListenerCb[K], T.Tuple[ListenerOpts, Context]]
) -> T.Iterator[T.Tuple[ListenerCb[K], T.Tuple[ListenerOpts, Context]]]:
    return (
        (
            _wrap_clear_once(listeners, listener) if opts & ListenerOpts.ONCE else listener,
            (opts, ctx_idx),
        )
        for listener, (opts, ctx_idx) in listeners.items()
    )


def _retrieve_listeners(
    listeners: Listeners, event_instance: T.Optional[K], scope: T.Tuple[str, ...]
) -> T.Sequence[T.Tuple[ListenerCb[K], T.Tuple[ListenerOpts, Context]]]:
    event_type = type(event_instance)

    if isinstance(event_instance, BaseException) and not isinstance(event_instance, Exception):
        # Bare instance of BaseException are re-raised.
        # Handling bare BaseExceptions could prevent normal behaviour of the interpreter on certain
        # situations.
        raise event_instance

    if issubclass(event_type, type) or isinstance(event_instance, type):
        # Event must be an instance. Event type must be a class. Reject Metaclass and cia.
        raise ValueError("Event type must be an instance of type")

    if event_type is object:
        # Object is too generic, it would cause unexpected behaviour.
        raise ValueError("Event type can't be object, must be a subclass of it")

    if event_instance is None and not scope:
        raise ValueError("Event type can only be None when accompanied of a scope")

    event_mro = tuple(cls for cls in event_type.mro()[1:] if cls is not BaseException)
    callables: T.List[T.Tuple[ListenerCb[K], T.Tuple[ListenerOpts, Context]]] = []
    for step in range(len(scope), -1, -1):
        types = listeners.scope[scope[:step]]
        if event_type in types:
            callables += _handle_once(types[event_type])

        for event_supertype in event_mro:
            if event_supertype in types:
                mro_listeners = types[event_supertype]
                callables += _handle_once(mro_listeners)

    return callables


@T.overload
def emit(
    event_instance: object,
    namespace: object,
    *,
    loop: AbstractEventLoop,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
) -> T.Optional["Task[bool]"]:
    ...


@T.overload
def emit(
    event_instance: object,
    namespace: object,
    *,
    loop: Te.Literal[None] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
) -> T.Coroutine[None, None, bool]:
    ...


def emit(
    event_instance: object,
    namespace: object,
    *,
    loop: T.Optional[AbstractEventLoop] = None,
    scope: T.Union[str, T.Tuple[str, ...]] = "",
) -> T.Union[None, "Task[bool]", T.Coroutine[None, None, bool]]:
    """Emit an event, and execute its listeners.

    When called without a defined loop argument this function always returns a coroutine.

    When called with a defined loop argument this function may return a Task or, when there is
    no listener for the given event, None.

    Listener execution order is as follows:

    - Scoped listeners, from more specific ones to more generics. (Only when scope is passed)

    - Listener for event type.

    - Listener for event super types, from specific super class to generic ones

    Args:

        event_instance: Event instance to be emitted.

        namespace: Specify a listener namespace to emit this event.

        loop: Define a loop to execute the listeners.

        scope: Define a scope for this event.

    Raises:

        ValueError: event_instance is an instance of a builtin type, or it is a type instead of
                    an instance.

        BaseException: Re-raise event instance if it is a BaseException.

        CancelledError: Raised whenever the loop (or something) cancels this coroutine.

    Returns:

        [`typing.Coroutine[None]`](https://docs.python.org/3/library/typing.html#callable) or
        [`typing.Awaitable[None]`](https://docs.python.org/3/library/typing.html#typing.Awaitable)
        representing the event emission.

    """
    namespace_listeners = _retrieve_listeners(
        retrieve_listeners_from_namespace(namespace), event_instance, parse_scope(scope)
    )

    coro = _exec_listeners(namespace_listeners, event_instance)

    if loop is None:
        return coro

    if namespace:
        return loop.create_task(coro)

    return None
