"""Async-aware event emitter that enables
[event-driven programming](https://en.wikipedia.org/wiki/Event-driven_programming) by providing the
basic interface needed for emitting events and registering listeners.

```python
import emitter
```

.. topics::
    [TOC]

## Namespace

Namespaces are objects that have a `__listeners__` attribute which exposes an `emitter.Listeners`
instance. If the namespace doesn't have a `__listeners__` attribute, but has writable attributes,
the library will automatically attempt to inject a weak reference to one. This way, most Python
objects can be used as Namespaces.

```python
# A bare class can be a namespace
class GlobalNamespace:
    pass
```

## Events

Events are any [Type Object](https://docs.python.org/3/library/stdtypes.html#type-objects)s.

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
    Events:

    - `object`:

        Bare objects are too generic and listeners attached to it would be triggered on all fired
        events.

    - `NoneType`:

        NoneType events have very little functionality. However, they are accepted when
        used along with a [Scope](#scope).

    - `BaseException`:

        BaseExceptions have special meaning, and the Python interpreter is normally expected to
        handle them internally. Therefore, trapping them as events wouldn't be advisable.

    A `ValueError` is raised if one of these classes is used as an Event.

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

# listener_executed is False since there is no listener registered for this
# event at the moment
assert not listener_executed
```

.. important::

    `emitter.emit` returns an `Awaitable[bool]` that blocks until all listeners for the event
    finish executing.

## Listeners

Listeners are any callable that receive a single argument (an instance of the event type) and
returns `None` or `Awaitable[None]`.
A listener can be registered for an event using `emitter.on`.

- A callable object as a listener:

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

- A lambda as a listener:

```python
# Register listener
emitter.on(
    UserRegisteredEvent,
    GlobalNamespace,
    lambda event: print(
        f"User<id={event.id}, name={event.name}, email={event.email}> "
        "registered"
    )
)
```

- A function as a listener:

```python
# Another approach to example 1
user_registry: T.List[UserRegisteredEvent] = []

# Register listener
@emitter.on(UserRegisteredEvent, GlobalNamespace)
def register_user(event: UserRegisteredEvent) -> None:
    user_registry.append(event)
```

- An asynchronous function as a listener:

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
        event.id, event.name, event.email
    )

    await conn.close()
```

.. important::

    The execution of event listeners follows insertion order (restricted to namespace) and waits
    for the completion of any awaitable returned.

### Special events:

- `emitter.NewListener`:

    Event emitted when a new listener has been added.
    TODO: Explain use, object exception, NewListener recursion and sync only listeners

- `emitter.error.EmitterError`:

    A generic internal event fired whenever an error occurs while emitting an event. It is an
    Exception subclass.

- `emitter.error.ListenerEventLoopError`:

    `emitter.emit` fires this event whenever an awaitable returned by a listener is bound to a loop different than that of the
    listener. It is an Exception subclass.

- `emitter.error.ListenerStoppedEventLoopError`

    It's fired whenever `emitter.emit` attempts to execute a listener bound to a loop that has stopped. It
    is an Exception subclass.

- `Exception` and its subclasses:

    Their behaviour is equivalent to any other event type, with the sole difference being when
    there are no listeners registered to handle an emission of them. In those cases, `emitter.emit`
    will raise the Exception instance back to the user context that called it.

## Scope

> TODO: Explain recent changes that allow using scopes alongside event inheritance

Scope is a feature that allows emitting and listening to events bound to a name rather than an
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
        event.id, True
    )

    await conn.close()
```

Scope names are dot separated strings. Each dot specifies a more specific scope that must also
be provided when emitting an event to the desired listeners.

Scoped events will execute all listeners registered to the given scope following the order from
most specific to most generic one. Listeners bound to event types will also be executed as normal.

Scoped event emissions may also use `None` if no event type is to be associated.

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

The call above will execute all 5 listeners that were registered on the event. One of them is
scoped under `permission.manager` and the other four are event type listeners.

## Event inheritance

Event inheritance allows specialization of events and their listeners.

Whenever `emitter.emit` is called with an event type instance, it will retrieve all inherited superclasses,
filter them by the ones that have registered listeners and emit their events.

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
    total_error[event.error] += 1

emitter.emit(
    ErrorMetric(name="error", value=1, error=RuntimeError),
    GlobalNamespace
)
```
"""


# Standard
from importlib.metadata import version

# Project
from ._on import on, on_context
from ._emit import emit
from ._wait import wait
from ._types import Listeners, Listenable, NewListener
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
    "on_context",
    "NewListener",
    "__version__",
)
