from __future__ import annotations


def require_equal_count(
    *,
    label: str,
    expected: int,
    actual: int,
) -> None:
    """Raise when two reconciliation counts differ."""

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
    """Raise when a validation failure count is nonzero."""

    if count:
        raise ValueError(
            f"{label}: {count:,} failure rows."
        )


def require_no_failures(
    failures: dict[str, int],
) -> None:
    """Raise with all nonzero validation failures."""

    nonzero = {
        key: value
        for key, value in failures.items()
        if value
    }

    if nonzero:
        raise ValueError(
            f"Relationship validation failed: {nonzero!r}"
        )