# Project
from .._types import ListenersMapping
from .new_listener_mapping import new_listener_mapping


def retrieve_listeners_from_namespace(namespace: object) -> ListenersMapping:
    if namespace is None:
        raise ValueError("Namespace can't be None")

    try:
        cache = namespace.__dict__
    except AttributeError:  # not all objects have __dict__ (e.g. class defines slots)
        raise TypeError(
            "Failed to retrieve namespace's listeners. "
            f"Namespace type: {type(namespace).__qualname__!r}, don't expose '__dict__'"
        ) from None

    listeners: ListenersMapping = cache.get("__listeners__", None)
    if listeners is None:
        listeners = new_listener_mapping()
        cache["__listeners__"] = listeners

    return listeners
