"""Validation helpers for extraordinary-funding relationships."""

from __future__ import annotations

from collections.abc import Iterable


def require_no_unresolved_reference_codes(
    unresolved_codes: dict[str, int],
) -> None:
    """
    Reject unresolved reference codes when strict resolution is required.

    Unknown source codes may still be retained separately as evidence;
    this helper is for contexts that require complete classification.
    """

    nonzero = {
        code: count
        for code, count in unresolved_codes.items()
        if count
    }

    if nonzero:
        raise ValueError(
            "Unresolved extraordinary-funding codes: "
            f"{nonzero!r}"
        )


def require_unique_relationships(
    relationships: Iterable[
        tuple[int, int]
    ],
) -> None:
    """
    Require unique transaction-to-classification relationships.

    Each tuple contains:
        assistance_transaction_id;
        extraordinary_funding_code_id.
    """

    observed: set[
        tuple[int, int]
    ] = set()

    duplicates: set[
        tuple[int, int]
    ] = set()

    for relationship in relationships:
        if relationship in observed:
            duplicates.add(
                relationship
            )
        else:
            observed.add(
                relationship
            )

    if duplicates:
        examples = sorted(
            duplicates
        )[:20]

        raise ValueError(
            "Duplicate extraordinary-funding relationships "
            f"were detected: {examples!r}"
        )


def require_equal_count(
    *,
    label: str,
    expected: int,
    actual: int,
) -> None:
    """Require exact count reconciliation."""

    if actual != expected:
        raise ValueError(
            f"{label} did not reconcile: "
            f"expected={expected:,}, actual={actual:,}."
        )


def require_zero(
    *,
    label: str,
    count: int,
) -> None:
    """Require a validation failure count to equal zero."""

    if count:
        raise ValueError(
            f"{label}: {count:,} failure rows."
        )


def require_no_database_failures(
    failures: dict[str, int],
) -> None:
    """Raise with all nonzero database integrity failures."""

    nonzero = {
        key: value
        for key, value in failures.items()
        if value
    }

    if nonzero:
        raise ValueError(
            "Extraordinary-funding relationship validation "
            f"failed: {nonzero!r}"
        )