"""Regression test for reversed USAspending performance dates."""

from __future__ import annotations

from datetime import date

from etl.loaders.normalize_usaspending_awards import (
    build_award_records,
)


AWARD_KEY = "CONT_AWD_36C26023P0181_3600_-NONE-_-NONE-"


def main() -> None:
    raw_rows = [
        (
            6244,
            {
                "contract_award_unique_key": AWARD_KEY,
                "award_id_piid": "36C26023P0181",
                "parent_award_id_piid": "",
                "award_type_code": "A",
                "award_type": "BPA Call",
                "prime_award_base_transaction_description": (
                    "Example award"
                ),
                "period_of_performance_start_date": (
                    "2023-01-17"
                ),
                "period_of_performance_current_end_date": (
                    "2023-01-13"
                ),
            },
        ),
        (
            6245,
            {
                "contract_award_unique_key": AWARD_KEY,
                "award_id_piid": "36C26023P0181",
                "parent_award_id_piid": "",
                "award_type_code": "A",
                "award_type": "BPA Call",
                "prime_award_base_transaction_description": (
                    "Example award"
                ),
                "period_of_performance_start_date": (
                    "2023-01-17"
                ),
                "period_of_performance_current_end_date": (
                    "2023-01-13"
                ),
            },
        ),
    ]

    awards, anomalies = build_award_records(
        raw_rows,
        load_batch_id=5,
    )

    assert set(awards) == {AWARD_KEY}

    award = awards[AWARD_KEY]

    assert (
        award["period_of_performance_start"]
        == date(2023, 1, 17)
    )

    assert award["period_of_performance_end"] is None

    assert len(anomalies) == 1

    anomaly = anomalies[0]

    assert anomaly["load_batch_id"] == 5
    assert anomaly["entity_type"] == "award"
    assert anomaly["entity_key"] == AWARD_KEY

    assert (
        anomaly["anomaly_code"]
        == "PERFORMANCE_END_BEFORE_START"
    )

    assert anomaly["severity"] == "WARNING"

    assert anomaly["source_row_numbers"] == [
        6244,
        6245,
    ]

    observations = anomaly["raw_values"]["observations"]

    assert observations == [
        {
            "source_row_number": 6244,
            "period_of_performance_start": "2023-01-17",
            "period_of_performance_current_end": "2023-01-13",
        },
        {
            "source_row_number": 6245,
            "period_of_performance_start": "2023-01-17",
            "period_of_performance_current_end": "2023-01-13",
        },
    ]

    assert anomaly["normalized_action"] == {
        "period_of_performance_end": None,
        "rule": (
            "Exclude reversed source end dates "
            "from normalized end-date aggregation."
        ),
    }

    print(
        "USAspending award-date anomaly regression test passed."
    )
    print()
    print(f"Award:           {AWARD_KEY}")
    print("Normalized start: 2023-01-17")
    print("Normalized end:   NULL")
    print("Anomalies:        1")
    print("Source rows:      6244, 6245")


if __name__ == "__main__":
    main()