# Internal
import typing as T
from asyncio import Future, CancelledError, AbstractEventLoop, ensure_future

# Project
from ._types import EmptyScope, HandleMode, ListenerCb, ListenerOpts, ListenersMapping
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


def _exec_listener_thread_safe(listener: ListenerCb[K], event_instance: K) -> "Future[None]":
    loop = get_running_loop()
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
    listeners: T.Mapping[T.Tuple[str, ...], T.MutableMapping[ListenerCb[K], ListenerOpts]],
    event_instance: K,
    scope: T.Tuple[str, ...],
) -> bool:
    listener: T.Optional[ListenerCb[K]] = None
    # Range from -1 to include empty scopes in the loop
    for step in range(-1, len(scope)):
        step += 1  # Fix scope index
        scope_listeners = listeners[scope[:step]]
        # .items() returns a dynamic view, make it static by transforming into a tuple.
        # This is necessary to allow listeners to remove events without interfering with any
        # current running event emission.
        for listener, opts in tuple(scope_listeners.items()):
            # Remove listener from the queue if it was set to only exec once.
            # There is a possibility that another listener removed this already, this is an
            # expected behaviour.
            if opts & ListenerOpts.ONCE and listener in scope_listeners:
                del scope_listeners[listener]

            future: T.Optional["Future[None]"] = None
            try:
                await _exec_listener_thread_safe(listener, event_instance)
            except CancelledError:
                raise
            except Exception as exc:
                # Second tier exception aren't treatable
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
                get_running_loop().call_exception_handler(
                    {
                        "future": future,
                        "message": "Unhandled exception during event emission",
                        "exception": exc,
                    }
                )

    # Whether the loop above reassigned the listener variable determines if a listener executed
    # or not
    return listener is not None


async def _emit_single(
    listeners: ListenersMapping, event_instance: K, scope: T.Tuple[str, ...] = EmptyScope
) -> bool:
    handled = False
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

    # Event instance must be an instance of event type
    assert isinstance(event_instance, event_type)

    # .mro() returns a list consisting of [current_type, ..., most_generic_supertype].
    # As such, remove the current type, as it is handled below, and reverse the list to fire
    # this event from the most generic to the most specific supertype.
    for event_supertype in reversed(event_type.mro()[1:]):
        # Short circuit event types that don't have any listener attached.
        if listeners[event_supertype] and listeners[event_supertype][EmptyScope]:
            # Fire this event for it's super types
            handled = (
                await _exec_listeners(listeners[event_supertype], event_instance, EmptyScope)
                or handled
            )

    event_listeners = listeners[event_type]
    if event_listeners:
        # Fire this event for its own type
        handled = await _exec_listeners(event_listeners, event_instance, scope) or handled

    return handled


async def emit(
    event_instance: object, *, scope: str = "", namespace: T.Optional[object] = None
) -> HandleMode:
    """Emit an event, and execute its listeners.

    Arguments:
        event_instance: Event instance to be emitted.
        scope: Define till which scopes this event will execute its listeners.
        namespace: Specify a listener namespace to emit this event.

    Raises:
        ValueError: event_instance is an instance of a builtin type, or it is a type instead of an
                    instance.
        BaseException: Re-raise event instance if it is a BaseException.
        CancelledError: Raised whenever the loop (or something) cancels this coroutine.

    Returns:
        Whether this event emission resulted in any listener execution.
        The returned type is `emitter.HandleMode`. It provides information on which listener
        bundled: global, namespace or both, that handled this event.
        If no listener handled this event the return value is 0.

    """
    from ._global import listeners

    handled = HandleMode.NONE
    normalized_scope = tuple(scope.split(".")) if scope else EmptyScope

    if await _emit_single(listeners, event_instance, normalized_scope):
        handled |= HandleMode.GLOBAL

    if namespace is not None and await _emit_single(
        retrieve_listeners_from_namespace(namespace), event_instance, normalized_scope
    ):
        handled |= HandleMode.NAMESPACE

    if not handled:
        if isinstance(event_instance, Exception):
            # When event_instance is an exception, and it is not handled, raise it back to user
            # context
            raise event_instance

    return handled
