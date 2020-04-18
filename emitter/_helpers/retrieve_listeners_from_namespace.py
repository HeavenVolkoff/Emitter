# Internal
import typing as T

# Project
from .._types import Listeners


def retrieve_listeners_from_namespace(namespace: object) -> Listeners:
    if namespace is None:
        raise ValueError("Namespace can't be None")

    if isinstance(namespace, Listeners):
        return namespace

    listeners: T.Optional[Listeners] = getattr(namespace, "__listeners__", None)
    if not isinstance(listeners, Listeners):
        if listeners is not None:
            raise TypeError(
                "Failed to retrieve namespace's listeners. "
                f"Namespace({type(namespace).__qualname__}) already defines an "
                "incompatible `__listeners__` attribute"
            ) from None

        listeners = Listeners()
        try:
            setattr(namespace, "__listeners__", listeners)
        except AttributeError:  # not all objects are writable
            raise TypeError(
                "Failed to retrieve namespace's listeners. "
                f"Namespace({type(namespace).__qualname__}) attributes aren't writable"
            ) from None

    return listeners
