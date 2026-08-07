from __future__ import annotations

from dataclasses import dataclass

from etl.common.relationships import (
    count_distinct_configurations,
    require_equal_count,
    require_no_failures,
    require_zero,
    select_one_per_group,
)


@dataclass(frozen=True)
class Observation:
    award_key: str
    action_rank: int
    source_row_number: int
    relationship_value: str


def main() -> None:
    observations = [
        Observation("A", 2, 10, "KING"),
        Observation("A", 3, 11, "PIERCE"),
        Observation("B", 1, 12, "SPOKANE"),
        Observation("B", 1, 13, "SPOKANE"),
    ]

    selections = select_one_per_group(
        observations,
        group_key=lambda item: item.award_key,
        selection_key=lambda item: (
            -item.action_rank,
            -item.source_row_number,
            item.relationship_value,
        ),
    )

    if selections["A"].relationship_value != "PIERCE":
        raise AssertionError(
            "Latest award relationship was not selected."
        )

    if selections["B"].source_row_number != 13:
        raise AssertionError(
            "Source-row tie breaker was not applied."
        )

    a_count = count_distinct_configurations(
        [
            item
            for item in observations
            if item.award_key == "A"
        ],
        configuration_key=lambda item: item.relationship_value,
    )

    if a_count != 2:
        raise AssertionError(
            "Distinct configuration count was incorrect."
        )

    require_equal_count(
        label="test count",
        expected=4,
        actual=4,
    )

    require_zero(
        label="test failures",
        count=0,
    )

    require_no_failures(
        {
            "missing": 0,
            "orphan": 0,
        }
    )

    print("Relationship helper contract test passed.")
    print()
    print("Verified:")
    print("  deterministic grouping")
    print("  latest-observation selection")
    print("  source-row tie breaking")
    print("  distinct configuration counts")
    print("  count reconciliation")
    print("  zero-failure validation")


if __name__ == "__main__":
    main()