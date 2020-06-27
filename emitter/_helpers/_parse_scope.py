# Standard
import typing as T


def parse_scope(scope: T.Union[str, T.Tuple[str, ...]]) -> T.Tuple[str, ...]:
    if isinstance(scope, str):
        scope = tuple(scope.split("."))
    return tuple(filter(bool, scope))
