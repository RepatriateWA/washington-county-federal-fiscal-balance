"""
Shared validation utilities for ETL and data-quality checks.

This module centralizes common mechanics used by validation scripts:

- immutable validation result records
- scalar SQL queries
- standardized report headers
- standardized PASS/FAIL result tables
- process exit behavior for failed checks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

# Shared validation framework used by all ETL validation scripts.
VALIDATION_FRAMEWORK_VERSION = "1.0.0"

DEFAULT_REPORT_WIDTH = 76


@dataclass(frozen=True)
class ValidationResult:
    """Represent one validation assertion."""

    name: str
    actual: Any
    expected: Any
    passed: bool
    detail: str | None = None


def scalar(
    cursor,
    sql: str,
    params: Sequence[Any] = (),
) -> Any:
    """Execute a query expected to return exactly one row and one column."""
    cursor.execute(sql, tuple(params))
    row = cursor.fetchone()

    if row is None:
        raise ValueError("Scalar query returned no row.")

    return row[0]


def scalar_int(
    cursor,
    sql: str,
    params: Sequence[Any] = (),
) -> int:
    """Execute a scalar query and coerce the result to int."""
    value = scalar(cursor, sql, params)

    if value is None:
        raise ValueError("Scalar integer query returned NULL.")

    return int(value)


def format_value(value: Any) -> str:
    """Format common validation values for human-readable reports."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def print_header(
    title: str,
    *,
    width: int = DEFAULT_REPORT_WIDTH,
    subtitle: str | None = None,
) -> None:
    """Print a standardized validation report header."""
    print("=" * width)
    print(title)
    print("=" * width)

    if subtitle:
        print(subtitle)

    print()


def print_metrics(
    metrics: Mapping[str, Any],
    *,
    label_width: int = 36,
) -> None:
    """Print summary metrics using aligned dotted leaders."""
    for label, value in metrics.items():
        dots = "." * max(1, label_width - len(label))
        print(f"{label} {dots} {format_value(value)}")

    if metrics:
        print()


def count_failures(results: Iterable[ValidationResult]) -> int:
    """Return the number of failed validation results."""
    return sum(1 for result in results if not result.passed)


def print_results(
    results: Sequence[ValidationResult],
    *,
    width: int = DEFAULT_REPORT_WIDTH,
    name_width: int = 48,
    raise_on_failure: bool = True,
) -> int:
    """Print standardized PASS/FAIL rows and an overall result."""
    print("-" * width)

    failures = 0

    for result in results:
        status = "PASS" if result.passed else "FAIL"

        if not result.passed:
            failures += 1

        line = (
            f"{status:4}  {result.name:<{name_width}} "
            f"actual={format_value(result.actual)} "
            f"expected={format_value(result.expected)}"
        )

        if result.detail:
            line += f"  detail={result.detail}"

        print(line)

    print("-" * width)

    if failures:
        print(
            f"OVERALL RESULT: FAIL "
            f"({failures} validation check(s) failed)"
        )
    else:
        print("OVERALL RESULT: PASS")

    print("=" * width)

    if failures and raise_on_failure:
        raise SystemExit(1)

    return failures


def require_nonzero(
    value: int,
    *,
    subject: str,
) -> None:
    """Raise a clear error when a validation scope contains no rows."""
    if value == 0:
        raise ValueError(f"No rows found for {subject}.")


def equality_result(
    name: str,
    actual: Any,
    expected: Any,
    *,
    detail: str | None = None,
) -> ValidationResult:
    """Create a ValidationResult based on equality."""
    return ValidationResult(
        name=name,
        actual=actual,
        expected=expected,
        passed=actual == expected,
        detail=detail,
    )


def zero_result(
    name: str,
    actual: int,
    *,
    detail: str | None = None,
) -> ValidationResult:
    """Create a ValidationResult that passes only when actual equals zero."""
    return equality_result(
        name=name,
        actual=actual,
        expected=0,
        detail=detail,
    )