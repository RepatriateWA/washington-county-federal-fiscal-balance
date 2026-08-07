"""Contract tests for extraordinary-funding validation helpers."""

from __future__ import annotations

from etl.common.extraordinary_funding.validation import (
    require_equal_count,
    require_no_database_failures,
    require_no_unresolved_reference_codes,
    require_unique_relationships,
    require_zero,
)


def expect_value_error(
    function,
    *,
    label: str,
) -> None:
    """Require one validation call to raise ValueError."""

    try:
        function()
    except ValueError:
        return

    raise AssertionError(
        f"{label} did not raise ValueError."
    )


def main() -> None:
    require_unique_relationships(
        [
            (1, 10),
            (1, 11),
            (2, 10),
        ]
    )

    expect_value_error(
        lambda: require_unique_relationships(
            [
                (1, 10),
                (1, 10),
            ]
        ),
        label="duplicate relationship validation",
    )

    require_no_unresolved_reference_codes(
        {}
    )

    require_no_unresolved_reference_codes(
        {
            "L": 0,
            "M": 0,
        }
    )

    expect_value_error(
        lambda: require_no_unresolved_reference_codes(
            {
                "AAA": 3,
            }
        ),
        label="unresolved-code validation",
    )

    require_equal_count(
        label="test reconciliation",
        expected=10,
        actual=10,
    )

    expect_value_error(
        lambda: require_equal_count(
            label="test reconciliation",
            expected=10,
            actual=9,
        ),
        label="count reconciliation",
    )

    require_zero(
        label="test zero",
        count=0,
    )

    expect_value_error(
        lambda: require_zero(
            label="test zero",
            count=1,
        ),
        label="zero-count validation",
    )

    require_no_database_failures(
        {
            "duplicates": 0,
            "orphans": 0,
        }
    )

    expect_value_error(
        lambda: require_no_database_failures(
            {
                "duplicates": 0,
                "orphans": 2,
            }
        ),
        label="database failure validation",
    )

    print(
        "Extraordinary-funding validation "
        "contract test passed."
    )
    print()
    print("Verified:")
    print("  unique transaction-code relationships")
    print("  duplicate relationship rejection")
    print("  strict unresolved-code validation")
    print("  exact count reconciliation")
    print("  zero-failure validation")
    print("  combined database integrity failures")


if __name__ == "__main__":
    main()