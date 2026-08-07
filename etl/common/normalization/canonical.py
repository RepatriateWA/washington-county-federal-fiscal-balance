"""Shared deterministic canonical-selection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class CanonicalSelection(Generic[T]):
    """Result of one deterministic canonical selection."""

    selected: T
    ordered_candidates: tuple[T, ...]


def select_canonical(
    candidates: Iterable[T],
    *,
    key,
) -> CanonicalSelection[T]:
    """
    Select the first candidate under a deterministic sort key.

    Callers are responsible for supplying a complete tie-breaking key.
    """

    ordered = tuple(
        sorted(
            candidates,
            key=key,
        )
    )

    if not ordered:
        raise ValueError(
            "Canonical selection requires at least one candidate."
        )

    return CanonicalSelection(
        selected=ordered[0],
        ordered_candidates=ordered,
    )