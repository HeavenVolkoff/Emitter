# Standard
from weakref import WeakKeyDictionary
import typing as T

# Project
from .._types import Listeners, BoundLoopListenerWrapper

_GLOBAL_LISTENERS: T.MutableMapping[object, Listeners] = WeakKeyDictionary()


def retrieve_listeners_from_namespace(namespace: object) -> Listeners:
    if namespace is None:
        raise ValueError("Namespace can't be None")
    elif isinstance(namespace, Listeners):
        return namespace
    elif isinstance(namespace, BoundLoopListenerWrapper):
        namespace = namespace.listener

    listeners: T.Optional[Listeners] = getattr(namespace, "__listeners__", None)
    if not isinstance(listeners, Listeners):
        if namespace in _GLOBAL_LISTENERS:
            return _GLOBAL_LISTENERS[namespace]

        listeners = Listeners()
        _GLOBAL_LISTENERS[namespace] = listeners

    return listeners
