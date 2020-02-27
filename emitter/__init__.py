"""Async-aware event emitter that enables
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
    The soles exceptions are bare objects and BaseExceptions.
    The reason they can't be events is due to unexpected behaviour.
    Bare object are too generic and listeners attached to it would run for all fired events, which
    probably isn't the behaviour expected by the user.
    BaseExceptions have special meaning, and the python interpreter normally expectes to handle
    them internally, so trapping them as events would probably result in unexpected behaviour

The method `emitter.emit` enables arbitrary event emission.
It receives a single argument, that is an instance of the event to be emitted, it returns a
`emitter.HandleMode` indicating whether it executed any listener and in which namespace it executed
them.

```python
listener_executed = await emitter.emit(
    UserRegisteredEvent(
        69, 'Michael Scott', 'whatshesaid@dundermifflin.com'
    )
)

# listener_executed is equal to HandleMode.NONE or 0
# That is because there is no listener registered for this event
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

- `emitter.ListenerMissingEventLoopError`

    Whenever `emitter.emit` attempts to execute a listener which bounded loop was garbage
    collected, it fires this event. It is an Exception subclass.

- `Exception` and it's subclasses:

    Their behaviour is equivalent to any other event type, with the sole difference being when
    there are no listeners registered to handle an emission of them. In those cases, `emitter.emit`
    call will raise the Exception instance back to the user context that called it.

## Scopes

Scope is a feature that allow limiting the execution of listeners to specific instances of an event
emission.

A scoped listener definition requires passing the `scope` argument to `emitter.on`.
It's default value is the empty scope, which is the one where all listeners registered under it are
guarantee to be executed whenever there is any emission of the event they are bounded to.
```python
@emitter.on(UserRegisteredEvent, scope="permission.manager")
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
Scope is a dot separated string. Each dot constrained name defines a more specif scope that must
also be specified when emitting an event to enable the execution of the registered scoped listener.
Scoped events will execute all listeners from the most generic scope (the empty scope) till the
specified scope.
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

## Namespace

Namespace is functionally equivalent to Scope.
However instead of defining a list of generic names, Namespace limit the listener execution
to certain object instances.

A namespaced listener definition requires passing the `namespace` argument to `emitter.on`.
It's default value is the global namespace, which is the one where all listeners registered under
it are guarantee to be executed whenever there is any emission of the event they are bounded to.
```python
site1_reader, _ = loop.create_connection()
site2_reader, _ = loop.create_connection()

@emitter.on(str, namespace=site1_reader)
async def write_data_site_1(event: str) -> None:
    conn = await asyncpg.connect(
        host='127.0.0.1'
        user='user',
        password='password',
        database='database',
    )

    await con.execute(
        'INSERT INTO data(json) VALUES($1)',
        event
    )

    await conn.close()

@emitter.on(str, namespace=site2_reader)
async def write_data_site_1(event: str) -> None:
    conn = await asyncpg.connect(
        host='10.24.0.1'
        user='user',
        password='password',
        database='database',
    )

    await con.execute(
        'INSERT INTO data(json) VALUES($1)',
        event
    )

    await conn.close()

await emitter.emit(await site1_reader.read(), namespace=site1_reader)
await emitter.emit(await site2_reader.read(), namespace=site2_reader)
```

Namespace and scopes can be combined freely.

.. important::
    `emitter.emit` always execute listeners in the global namespace. After, it executes listeners
    in local namespaces if any was given to it.

## Event inheritance

Event inheritance allows specialization of events and their listeners.

Whenever `emitter.emit` is called with an event type instance, it will retrieve all superclasses
that this instance inherits from, filter them by the ones that have registered unscoped listeners
and emit their events.

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

@emitter.on(Metric):
def register_metric(event: Metric):
    metrics.add(event)

@dataclass
class ErrorMetric(Metric):
    error: T.Type[Exception]

@emitter.on(Metric):
def calculate_total_error(event: ErrorMetric):
    total_error[emitter.error] += 1

emitter.emit(ErrorMetric(name="error", value=1, error=RuntimeError))
```
"""


# External
from importlib_metadata import version

# Project
from ._on import on
from ._emit import emit
from ._types import HandleMode
from ._remove import remove
from ._retrieve import retrieve

try:
    __version__: str = version(__name__)
except Exception:  # pragma: no cover
    import traceback
    from warnings import warn

    warn(f"Failed to set version due to:\n{traceback.format_exc()}", ImportWarning)
    __version__ = "0.0a0"


__all__ = (
    "on",
    "emit",
    "remove",
    "retrieve",
    "HandleMode",
    "__version__",
)
