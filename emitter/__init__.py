"""Async-aware event emitter that enables
[event-driven programming](https://en.wikipedia.org/wiki/Event-driven_programming) by providing the
basic interface needed for emitting events and registering listeners.

```python
import emitter
```

.. topics::
    [TOC]

## Namespace

Namespaces are objects that have an `__listeners__` attribute which expose an
`emitter.Listeners` instance. If the namespace don't have an `__listeners__` attribute the lib
will attempt transparently inject a weak reference for one so that most python objects can be
used as Namespaces.

```python
# A bare class can be a namespace
class GlobalNamespace:
    pass
```

## Events

Events are any [Type Object](https://docs.python.org/3/library/stdtypes.html#type-objects).

Basically, most python classes can be an Event:
```python
from typing import NamedTuple

# An event
class UserRegisteredEvent(NamedTuple):
    id: int
    name: str
    email: str
```

.. warning::

    Due to possible unexpected behaviour by the user, the following classes are not accepted as
    Events

    - `object`:

        Bare object are too generic and listeners attached to it would run for all fired
        events.

    - `NoneType`:

        NoneType events have very little functionality. However, they are accepted when
        using together with [Scope](#scope).

    - `BaseException`:

        BaseExceptions have special meaning, and the python interpreter normally expects to
        handle them internally, so trapping them as events wouldn't be advisable.

    A `ValueError` is raised if one of these classes are used as an Event.

The method `emitter.emit` enables arbitrary event emission.
It receives two positional arguments:

1. An instance of the event to be emitted.

2. An instance of a namespace where the event will be emitted.

It returns a boolean indicating whether this emission resulted in the execution of any listener.

```python
listener_executed = await emitter.emit(
    UserRegisteredEvent(
        1, 'Michael Scott',
        'thats_what_she_said@dundermifflin.com'
    ),
    GlobalNamespace
)

# listener_executed is False due to there being no listener registered for this
# event at the moment
assert not listener_executed
```

.. important::

    `emitter.emit` returns an `Awaitable[bool]` that blocks until all listeners for the event
    finishes executing.

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
emitter.on(UserRegisteredEvent, GlobalNamespace, user_registry)
```

- A lambda as listener:

```python
# Register listener
emitter.on(
    UserRegisteredEvent,
    GlobalNamespace,
    lambda event: print(
        f"User<id={emitter.id}, name={emitter.name}, email={emitter.email}> "
        "registered"
    )
)
```

- A function as listener:

```python
# Another approach to example 1
user_registry: T.List[UserRegisteredEvent] = []

# Register listener
@emitter.on(UserRegisteredEvent, GlobalNamespace)
def register_user(event: UserRegisteredEvent) -> None:
    user_registry.append(event)
```

- An asynchronous function as listener:

```python
import asyncpg

# Register listener
@emitter.on(UserRegisteredEvent, GlobalNamespace)
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

- `emitter.error.EmitterError`:

    A generic internal event fired whenever an error occurs while emitting an event. It is an
    Exception subclass.

- `emitter.error.ListenerEventLoopError`:

    Whenever a listener returned awaitable is bounded to a loop different from the one bounded to
    the listener, `emitter.emit` fires this event. It is an Exception subclass.

- `emitter.error.ListenerStoppedEventLoopError`

    Whenever `emitter.emit` attempts to execute a listener bounded to a stopped loop, it fires this
    event. It is an Exception subclass.

- `Exception` and it's subclasses:

    Their behaviour is equivalent to any other event type, with the sole difference being when
    there are no listeners registered to handle an emission of them. In those cases, `emitter.emit`
    call will raise the Exception instance back to the user context that called it.

## Scope

Scope is a feature that allow emitting, and listening, events bounded to a name instead of an
event type.

A scoped listener definition requires passing a scope name as argument to `emitter.on` instead
of an event type.

```python
@emitter.on("permission.manager", GlobalNamespace)
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

Scope names are dot separated strings. Each dot specifies a more specific scope that must also
be provided when emitting an event so that the registered listener can be executed.

Scoped events will execute all listeners registered to the given scope, following the order from
most specific to more generic ones. Event type listeners will also be executed as normal.

Scoped event emissions can use `None` when wanting to emit a scoped event not ties to any event
type.

```python
await emitter.emit(
    UserRegisteredEvent(
        1, 'Michael Scott',
        'thats_what_she_said@dundermifflin.com'
    ),
    GlobalNamespace,
    scope="permission.manager"
)
```

The call above will execute all 5 listeners that were registered in the event. Being one of them
scoped under `permission.manager`, and the other 4 being event type listeners.

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

@emitter.on(Metric, GlobalNamespace)
def register_metric(event: Metric):
    metrics.add(event)

@dataclass
class ErrorMetric(Metric):
    error: T.Type[Exception]

@emitter.on(Metric, GlobalNamespace)
def calculate_total_error(event: ErrorMetric):
    total_error[emitter.error] += 1

emitter.emit(
    ErrorMetric(name="error", value=1, error=RuntimeError),
    GlobalNamespace
)
```
"""

# Must be first as to load the aiocontextvars polyfill lib
from ._helpers import contextvars  # isort:skip

# External
from importlib_metadata import version  # type: ignore[import]

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
