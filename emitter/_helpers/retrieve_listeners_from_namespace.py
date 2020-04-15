# Project
# Internal
import typing as T

from .._types import ListenersMapping
from .new_listener_mapping import new_listener_mapping

# Generic types
K = T.TypeVar("K")

_NOT_FOUND: K = object()  # type: ignore


def retrieve_listeners_from_namespace(
    namespace: object, default: K = _NOT_FOUND
) -> T.Union[K, ListenersMapping]:
    if namespace is None:
        raise ValueError("Namespace can't be None")

    listeners: T.Optional[ListenersMapping] = getattr(namespace, "__listeners__", None)
    if listeners is not None:
        return listeners

    try:
        cache = namespace.__dict__
    except AttributeError:  # not all objects have __dict__ (e.g. class defines slots)
        raise TypeError(
            "Failed to retrieve namespace's listeners. "
            f"Namespace type: {type(namespace).__qualname__!r}, don't expose '__dict__'"
        ) from None

    listeners: T.Optional[ListenersMapping] = cache.get("__listeners__", None)
    if listeners is None:
        if default is not _NOT_FOUND:
            return default

        listeners = new_listener_mapping()
        cache["__listeners__"] = listeners

    return listeners
