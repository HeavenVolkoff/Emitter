Module emitter
==============
Async-aware event emitter that enables
[event-driven programming](https://en.wikipedia.org/wiki/Event-driven_programming) by providing the
basic interface needed for emitting events and registering listeners.

```python
import emitter
```

.. topics::
    [TOC]

## Events

Events are any [Type Object](https://docs.python.org/3/library/stdtypes.html#type-objects).
Basically, any class can be an Event.

```python
from typing import NamedTuple

# An event
class UserRegisteredEvent(NamedTuple):
    id: int
    name: str
    email: str
```

... warning:
    The soles exceptions are bare objects, NoneType, and BaseExceptions.
    The reason they can't be events is due possible unexpected behaviour by the user.
    Bare object are too generic and listeners attached to it would run for all fired events, which
    probably isn't the behaviour expected or wanted by the user.
    BaseExceptions have special meaning, and the python interpreter normally expects to handle
    them internally, so trapping them as events wouldn't be advisable.

The method `emitter.emit` enables arbitrary event emission.
It receives a single argument, that is an instance of the event to be emitted and returns a boolean
indicating whether any listener were executed.

```python
listener_executed = await emitter.emit(
    UserRegisteredEvent(
        69, 'Michael Scott', 'whatshesaid@dundermifflin.com'
    )
)

# listener_executed is False
# That is because there is no listener registered for this event at the moment
assert not listener_executed
```
.. important::
    `emitter.emit` blocks until it finishes executing all listeners registered for the received
    event.

## Listeners

Listeners are any callable that receives a single argument (an instance of the event type) and
returns `None` or `Awaitable[None]`.
A listener can be registered for an event via `emitter.on`.

- A callable object as listener:

```python
class UserRegistry:
    def __init__() -> None:
        self.registry: T.List[UserRegisteredEvent] = []

    def __call__(event: UserRegisteredEvent) -> None:
        self.registry.append(event)

user_registry = UserRegistry()

# Register listener
emitter.on(UserRegisteredEvent, user_registry)
```

- A lambda as listener:

```python
# Register listener
emitter.on(
    UserRegisteredEvent,
    lambda event: print(
        f"User<id={emitter.id}, name={emitter.name}, email={emitter.email}>"
         "registered"
    )
)
```

- A function as listener:

```python
# Another approach to example 1
user_registry: T.List[UserRegisteredEvent] = []

# Register listener
@emitter.on(UserRegisteredEvent)
def register_user(event: UserRegisteredEvent) -> None:
    user_registry.append(event)
```

- An asynchronous function as listener:

```python
import asyncpg

# Register listener
@emitter.on(UserRegisteredEvent)
async def write_user(event: UserRegisteredEvent) -> None:
    conn = await asyncpg.connect(
        host='127.0.0.1'
        user='user',
        password='password',
        database='database',
    )

    await conn.execute(
        'INSERT INTO users(id, name, email) VALUES($1, $2, $3)',
        emitter.id, emitter.name, emitter.email
    )

    await conn.close()
```

.. important::
    The execution of event listeners follows insertion order (restricted to namespace) and waits
    for the completion of any awaitable returned.

### Special events:

- `emitter.EmitterError`:

    A generic internal event fired whenever an error occurs while emitting an event. It is an
    Exception subclass.

- `emitter.ListenerEventLoopError`:

    Whenever a listener returned awaitable is bounded to a loop different from the one bounded to
    the listener, `emitter.emit` fires this event. It is an Exception subclass.

- `emitter.ListenerStoppedEventLoopError`

    Whenever `emitter.emit` attempts to execute a listener bounded to a stopped loop, it fires this
    event. It is an Exception subclass.

- `Exception` and it's subclasses:

    Their behaviour is equivalent to any other event type, with the sole difference being when
    there are no listeners registered to handle an emission of them. In those cases, `emitter.emit`
    call will raise the Exception instance back to the user context that called it.

## Scopes

Scope is a feature that allow emitting events bounded to a namespace, and listening to events given
a namespace and not an event type.

A scoped listener definition requires passing a scope namespace as argument to `emitter.on`,
instead of an event type.
```python
@emitter.on("permission.manager")
async def write_admin_permission(event: UserRegisteredEvent) -> None:
    conn = await asyncpg.connect(
        host='127.0.0.1'
        user='user',
        password='password',
        database='database',
    )

    await con.execute(
        'UPDATE users SET admin=$2 WHERE id=$1',
        emitter.id, True
    )

    await conn.close()
```
Scope namespace is a dot separated string. Each dot constrained name defines a more specific scope
that must also be specified when emitting an event to enable the execution of the registered scoped
listener.
Scoped events will execute all listeners registered to the given scope as well as more generic
ones. Event type listeners will also be executed as normal.
```python
await emitter.emit(
    UserRegisteredEvent(
        69,
        'Michael Scott',
        'whatshesaid@dundermifflin.com'
    ),
    scope="permission.manager"
)
```
The call above will execute all 5 listeners that were registered in the event. Being 4 of them
unscoped (or empty scoped), and the last one scoped under `permission.manager`.

## Event inheritance

Event inheritance allows specialization of events and their listeners.

Whenever `emitter.emit` is called with an event type instance, it will retrieve all superclasses
that this instance inherits from, filter them by the ones that have registered listeners and emit
their events.

```python
from dataclass import dataclass
from collections import Counter
import event

metrics = set()
total_error = Counter()

@dataclass
class Metric:
    name: str
    value: int

    def __hash__(self):
        return hash(self.name)

@emitter.on(Metric)
def register_metric(event: Metric):
    metrics.add(event)

@dataclass
class ErrorMetric(Metric):
    error: T.Type[Exception]

@emitter.on(Metric)
def calculate_total_error(event: ErrorMetric):
    total_error[emitter.error] += 1

emitter.emit(ErrorMetric(name="error", value=1, error=RuntimeError))
```

Sub-modules
-----------
* emitter.errors

Functions
---------

    
`emit(event_instance: object, namespace: object, *, loop: Union[asyncio.events.AbstractEventLoop, NoneType] = None, scope: str = '') -> Union[NoneType, ForwardRef('Task[bool]'), Coroutine[NoneType, NoneType, bool]]`
:   Emit an event, and execute its listeners.
    
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

    
`on(event: Union[str, Type[~K]], namespace: object, listener: Union[emitter._types.ListenerCb[~K], NoneType] = None, *, once: bool = False, loop: Union[asyncio.events.AbstractEventLoop, NoneType] = None, context: bool = False, raise_on_exc: bool = False) -> Union[emitter._types.ListenerCb[~K], AbstractContextManager[NoneType], Callable[[emitter._types.ListenerCb[~K]], emitter._types.ListenerCb[~K]]]`
:   Add a listener to event type.
    
    Context can't be specified when using this function in decorator mode.
    Context can't be specified when passing once=True.
    
    Arguments:
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
        If listener isn't provided, this method returns a function that takes a Callable as a         single argument. As such it can be used as a decorator. In both the decorated and         undecorated forms this function returns the given event listener.

    
`remove(event: Union[str, NoneType, Type[~K]], namespace: object, listener: Union[emitter._types.ListenerCb[~K], NoneType] = None, context: Union[emitter._context.context, NoneType] = None) -> bool`
:   Remove listeners, limited by scope, from given event type.
    
    When no context is provided assumes current context.
    
    When no event_type and no listener are passed removes all listeners from the given namespace
    and context.
    
    When no event_type is specified but a listener is given removes all references to the listener,
    whetever scoped or typed, from the given namespace and context.
    
    When both event and listener are specified, remove only the correspondent match from the given
    namespace and context.
    
    Raises:
        ValueError: event_type is None, but scope or listener are not.
    
    Arguments:
        event: Define from which event types the listeners will be removed.
        listener: Define the listener to be removed.
        namespace: Define from which namespace to remove the listener
        context: Define context to restrict listener removal
    
    Returns:
        Whether any listener removal occurred.

    
`wait(event: Union[str, Type[~K]], namespace: object) -> ~K`
:   This is a helper function that awaits for the first execution of a given
    event or scope namespace and return its value.
    
    Arguments:
        event: Event type or scope namespace.
        namespace: Specify the namespace in which to wait for the event emission.
    
    Returns:
        Emitted event instance.

Classes
-------

`Listenable(*args, **kwds)`
:   A protocol that defines emitter namespaces

    ### Ancestors (in MRO)

    * typing.Protocol
    * typing.Generic

`Listeners()`
:   

    ### Instance variables

    `scope`
    :   Return an attribute of instance, which is of type owner.

    `types`
    :   Return an attribute of instance, which is of type owner.

`context(*args, **kwds)`
:   Emitter listener context.
    
    For advanced control of listener's life-cycle.
    
    TODO: Improve, add examples

    ### Ancestors (in MRO)

    * contextlib.AbstractContextManager
    * abc.ABC
    * typing.Generic

    ### Methods

    `add(self, other: uuid.UUID) -> NoneType`
    :   Add an identifier to this context.
        
        Args:
            other: Identifier