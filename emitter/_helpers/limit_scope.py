# Internal
import typing as T

# Project
from .._types import EmptyScope

# Type generics
K = T.TypeVar("K")


def limit_scope(
    scope: T.Optional[str], listeners: T.Iterable[T.Tuple[T.Tuple[str, ...], K]],
) -> T.Iterable[T.Tuple[T.Tuple[str, ...], K]]:
    if scope:
        event_scope = tuple(scope.split(".")) if scope else EmptyScope
        listeners = filter(
            lambda scope_and_listener: event_scope >= scope_and_listener[0], listeners
        )

    return listeners
