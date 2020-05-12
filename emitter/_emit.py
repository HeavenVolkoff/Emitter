# Internal
import typing as T
from asyncio import Task, Future, CancelledError, AbstractEventLoop, ensure_future
from functools import partial
from contextvars import Context

# External
import typing_extensions as Te

# Project
from ._types import Listeners, ListenerCb, ListenerOpts
from .errors import ListenerEventLoopError
from ._helpers import (
    get_running_loop,
    retrieve_loop_from_listener,
    retrieve_listeners_from_namespace,
)

# Type generics
K = T.TypeVar("K", contravariant=True)

_ONCE_EXEC_SENTINEL = object()


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
            resolve(None)
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
        try:
            await _exec_listener_thread_safe(loop, listener, context, event_instance)
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

        handled = (
            handled
            or getattr(listener, "_once_unavailable_sentinel", None) is not _ONCE_EXEC_SENTINEL
        )

    if not handled and isinstance(event_instance, Exception):
        # When event_instance is an exception, and it is not handled, raise it back to user
        # context
        raise event_instance

    return handled


def _handle_once(
    listeners: T.MutableMapping[ListenerCb[K], T.Tuple[ListenerOpts, Context]]
) -> T.Iterator[T.Tuple[ListenerCb[K], T.Tuple[ListenerOpts, Context]]]:
    def _wrap_clear_once(listener: ListenerCb[K]) -> ListenerCb[K]:
        def _clear_once(event: K) -> T.Optional[T.Awaitable[None]]:
            if listener not in listeners:
                setattr(_clear_once, "_once_unavailable_sentinel", _ONCE_EXEC_SENTINEL)
                return None

            del listeners[listener]
            return listener(event)

        if hasattr(listener, "__loop__"):
            setattr(_clear_once, "__loop__", getattr(listener, "__loop__"))

        return _clear_once

    return (
        (_wrap_clear_once(listener) if opts & ListenerOpts.ONCE else listener, (opts, ctx_idx))
        for listener, (opts, ctx_idx) in listeners.items()
    )


def _retrieve_listeners(
    listeners: Listeners, event_instance: K, scope: T.Optional[T.Tuple[str, ...]]
) -> T.Sequence[T.Tuple[ListenerCb[K], T.Tuple[ListenerOpts, Context]]]:
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

    callables: T.List[T.Tuple[ListenerCb[K], T.Tuple[ListenerOpts, Context]]] = []
    if scope:
        for step in range(len(scope), 0, -1):
            callables += _handle_once(listeners.scope[scope[:step]])

        if event_instance is None:
            return callables
    elif event_instance is None:
        raise ValueError("Event type can only be None when accompanied of a scope")

    callables += _handle_once(listeners.types[event_type])

    for event_supertype in event_type.mro()[1:]:
        if event_instance is object or event_instance is BaseException:
            continue

        mro_listeners = listeners.types[event_supertype]
        callables += _handle_once(mro_listeners)

    return callables


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

    When called without a defined loop argument this function always returns a coroutine.

    When called with a defined loop argument this function may return a Task or, when there is
    no listener for the given event, None.

    Listener execution order is as follows:
    - Scoped listeners, from more specific ones to more generics. (Only when scope is passed)
    - Listener for event type.
    - Listener for event super types, from specific super class to generic ones

    Arguments:
        event_instance: Event instance to be emitted.
        namespace: Specify a listener namespace to emit this event.
        loop: Define a loop to execute the listeners.
        scope: Define a scope for this event.

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
