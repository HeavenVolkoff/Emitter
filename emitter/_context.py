# Internal
import typing as T
from uuid import UUID, uuid4
from contextvars import Token, ContextVar

# External
import typing_extensions as Te

# Constants
CONTEXT: Te.Final["ContextVar[context]"] = ContextVar("emitter")


class context(T.ContextManager["context"]):
    """Emitter listener context.

    For advanced control of listener's life-cycle.

    TODO: Improve, add examples
    """

    def __init__(self, custom_index: T.Optional[UUID] = None) -> None:
        self.id: T.Final[UUID] = uuid4() if custom_index is None else custom_index

        # Internal
        self._ids: T.Final[T.Set[UUID]] = {self.id}
        self._token: T.Optional["Token[context]"] = None

    def __exit__(self, _: T.Any, __: T.Any, ___: T.Any) -> Te.Literal[False]:
        if self._token is not None:
            CONTEXT.reset(self._token)
            self._token = None

        return False

    def __enter__(self) -> "context":
        self._token = CONTEXT.set(self)

        self.add(self.id)

        return self

    def __contains__(self, item: T.Union[UUID, "context"]) -> bool:
        return (item.id if isinstance(item, context) else item) in self._ids

    def add(self, other: UUID) -> None:
        """Add an identifier to this context.

        Args:
            other: Identifier

        """
        assert self._token is not None

        self._ids.add(other)

        previous_context = self._token.old_value
        if previous_context is not Token.MISSING:
            previous_context.add(other)


if CONTEXT.get(T.cast(context, None)) is None:
    # Init base context
    context().__enter__()
