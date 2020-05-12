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
"""


# Internal
from sys import version_info

# External
from importlib_metadata import version

# Project
from ._on import on
from ._emit import emit
from ._wait import wait
from ._types import Listeners, Listenable
from ._remove import remove
from ._context import context

try:
    __version__: str = version(__name__)
except Exception:  # pragma: no cover
    import traceback
    from warnings import warn

    warn(f"Failed to set version due to:\n{traceback.format_exc()}", ImportWarning)
    __version__ = "0.0a0"

# Enable asyncio contextvars support in Python 3.6:
if version_info < (3, 7):
    import aiocontextvars

    del aiocontextvars

__all__ = (
    "on",
    "wait",
    "emit",
    "remove",
    "context",
    "Listeners",
    "Listenable",
    "__version__",
)
