# Standard
from contextvars import Token, ContextVar
import typing as T

# External
import typing_extensions as Te

# Project
from ._types import Listeners
from ._helpers import retrieve_listeners_from_namespace

CONTEXT: Te.Final["ContextVar[context]"] = ContextVar("emitter.context")


class context(T.ContextManager["context"]):
    """Emitter listener context.

    For advanced control of listener's life-cycle.

    .. TODO::
        Improve, add examples
    """

    def __init__(self) -> None:
        # Internal
        self._ids: T.Final[T.Set[int]] = {id(self)}
        self._token: T.Optional[Token[context]] = None

    def __exit__(self, _: T.Any, __: T.Any, ___: T.Any) -> Te.Literal[False]:
        if self._token is None:
            raise RuntimeError("Exiting an inactive emitter.context is not possible")

        CONTEXT.reset(self._token)
        self._token = None

        return False

    def __enter__(self) -> "context":
        if self._token is not None:
            raise RuntimeError("Entering an active emitter.context is not possible")

        self._token = CONTEXT.set(self)
        self.add(self)
        return self

    def __contains__(self, item: T.Union[int, "context"]) -> bool:
        return (id(item) if isinstance(item, context) else item) in self._ids

    def add(self, other: T.Union[int, "context"]) -> None:
        """Add another context as child of this one.

        Args:
            other: Other context

        """
        if isinstance(other, context):
            other = id(other)

        if id(self) != other:
            self._ids.add(other)

        if self._token and self._token.old_value is not Token.MISSING:
            self._token.old_value.add(other)

    @property
    def active(self) -> bool:
        return self._token is not None

    def wrap_listeners(self, namespace: object) -> Listeners:
        if self._token is None:
            raise RuntimeError("Emitter.context must be active to wrap listeners")

        listeners = retrieve_listeners_from_namespace(namespace)
        return Listeners(_scope=listeners.scope, _types=listeners.types, _context=self)


if CONTEXT.get(T.cast(context, None)) is None:
    # Init base context
    context().__enter__()
