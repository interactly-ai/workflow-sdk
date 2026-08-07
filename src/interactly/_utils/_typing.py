"""
NOT_GIVEN sentinel — the canonical way to distinguish "caller did not supply
this argument" from "caller explicitly passed None".

Why this matters for PATCH requests:
    update(name=None)       → sets name to JSON null in the request body
    update()                → name field is omitted from the body entirely

Usage:
    from interactly._utils._typing import NOT_GIVEN, NotGivenOr, is_given
"""

from __future__ import annotations

from typing import ClassVar, Literal, TypeVar, Union, final

from typing_extensions import TypeGuard

T = TypeVar("T")


@final
class NotGiven:
    """
    Singleton sentinel object. Compares False in boolean context so that
    ``if field:`` idioms work as expected.
    """

    _instance: ClassVar[NotGiven | None] = None

    def __new__(cls) -> "NotGiven":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = NotGiven()

# Type alias: a parameter that is either a real value T or was not supplied.
NotGivenOr = Union[T, NotGiven]


def is_given(value: NotGivenOr[T]) -> TypeGuard[T]:
    """Return True iff *value* is not the NOT_GIVEN sentinel.

    Declared as a ``TypeGuard[T]`` rather than ``bool`` so type checkers narrow
    ``NotGivenOr[T]`` to ``T`` inside the guarded branch. As a plain ``bool`` every
    ``if is_given(x): x.isoformat()`` was an error under strict mode — the value was still
    ``T | NotGiven`` as far as the checker knew — which pushed call sites into redundant
    ``is not None`` guards or casts. Narrowing at the source fixes all of them at once, and
    SDK users get the same benefit in their own editors.
    """
    return not isinstance(value, NotGiven)
