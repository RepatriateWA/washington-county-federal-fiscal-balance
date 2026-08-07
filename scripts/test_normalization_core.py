"""Contract tests for shared normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass

from etl.common.normalization.canonical import (
    select_canonical,
)
from etl.common.normalization.text import (
    clean_optional_text,
    normalize_comparison_text,
)


@dataclass(frozen=True)
class Observation:
    value: str
    occurrence_count: int
    last_source_row_number: int


def main() -> None:
    if clean_optional_text(None) is not None:
        raise AssertionError(
            "None should remain null."
        )

    if clean_optional_text("   ") is not None:
        raise AssertionError(
            "Blank text should normalize to null."
        )

    if clean_optional_text("  Value  ") != "Value":
        raise AssertionError(
            "Text trimming failed."
        )

    normalized = normalize_comparison_text(
        "  Federal\n  Assistance   Program "
    )

    if normalized != "FEDERAL ASSISTANCE PROGRAM":
        raise AssertionError(
            f"Unexpected normalized text: {normalized!r}"
        )

    candidates = [
        Observation(
            value="Title B",
            occurrence_count=5,
            last_source_row_number=100,
        ),
        Observation(
            value="Title A",
            occurrence_count=10,
            last_source_row_number=50,
        ),
        Observation(
            value="Title C",
            occurrence_count=10,
            last_source_row_number=75,
        ),
    ]

    result = select_canonical(
        candidates,
        key=lambda item: (
            -item.occurrence_count,
            -item.last_source_row_number,
            item.value,
        ),
    )

    if result.selected.value != "Title C":
        raise AssertionError(
            "Canonical selection precedence failed."
        )

    if len(result.ordered_candidates) != 3:
        raise AssertionError(
            "Candidate history was not preserved."
        )

    try:
        select_canonical(
            [],
            key=lambda item: item,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Empty canonical selection should fail."
        )

    print("Normalization core contract test passed.")
    print()
    print("Verified:")
    print("  optional text cleaning")
    print("  conservative comparison normalization")
    print("  deterministic canonical selection")
    print("  complete candidate preservation")
    print("  empty-selection rejection")


if __name__ == "__main__":
    main()