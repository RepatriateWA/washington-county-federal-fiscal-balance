"""Regression tests for classification canonical-selection policy."""

from __future__ import annotations

from etl.loaders.normalize_usaspending_classifications import (
    derive_classifications,
)


def main() -> None:
    # Scenario 1:
    # The most recent action date determines the canonical description.
    raw_rows = [
        (
            100,
            {
                "action_date": "2024-03-01",
                "product_or_service_code": "Q201",
                "product_or_service_code_description": (
                    "MEDICAL- GENERAL HEALTH CARE"
                ),
            },
        ),
        (
            200,
            {
                "action_date": "2024-08-15",
                "product_or_service_code": "Q201",
                "product_or_service_code_description": (
                    "MEDICAL- MANAGED HEALTHCARE"
                ),
            },
        ),
    ]

    (
        naics,
        psc,
        naics_aliases,
        psc_aliases,
        anomalies,
    ) = derive_classifications(
        raw_rows,
        load_batch_id=5,
    )

    assert naics == {}
    assert naics_aliases == []

    assert psc == {
        "Q201": "MEDICAL- MANAGED HEALTHCARE",
    }

    assert len(psc_aliases) == 2

    alias_values = {
        (
            alias.code,
            alias.observed_description,
            alias.occurrence_count,
            alias.first_source_row_number,
            alias.last_source_row_number,
        )
        for alias in psc_aliases
    }

    assert alias_values == {
        (
            "Q201",
            "MEDICAL- GENERAL HEALTH CARE",
            1,
            100,
            100,
        ),
        (
            "Q201",
            "MEDICAL- MANAGED HEALTHCARE",
            1,
            200,
            200,
        ),
    }

    assert len(anomalies) == 1

    anomaly = anomalies[0]

    assert anomaly["load_batch_id"] == 5
    assert anomaly["entity_type"] == "psc"
    assert anomaly["entity_key"] == "Q201"
    assert anomaly["anomaly_code"] == "DESCRIPTION_ALIAS"
    assert anomaly["severity"] == "WARNING"

    assert anomaly["normalized_action"][
        "canonical_description"
    ] == "MEDICAL- MANAGED HEALTHCARE"

    # Scenario 2:
    # Equal action dates are resolved by highest source-row number.
    tie_rows = [
        (
            300,
            {
                "action_date": "2024-08-15",
                "product_or_service_code": "Q201",
                "product_or_service_code_description": (
                    "MEDICAL- MANAGED HEALTHCARE"
                ),
            },
        ),
        (
            400,
            {
                "action_date": "2024-08-15",
                "product_or_service_code": "Q201",
                "product_or_service_code_description": (
                    "MEDICAL- GENERAL HEALTH CARE"
                ),
            },
        ),
    ]

    (
        _tie_naics,
        tie_psc,
        _tie_naics_aliases,
        tie_psc_aliases,
        tie_anomalies,
    ) = derive_classifications(
        tie_rows,
        load_batch_id=6,
    )

    assert tie_psc == {
        "Q201": "MEDICAL- GENERAL HEALTH CARE",
    }

    assert len(tie_psc_aliases) == 2
    assert len(tie_anomalies) == 1

    assert tie_anomalies[0]["normalized_action"][
        "canonical_description"
    ] == "MEDICAL- GENERAL HEALTH CARE"

    print("Classification alias policy regression test passed.")
    print()
    print("Latest-action-date selection: verified")
    print("Highest-source-row tie-break: verified")
    print("Alias preservation: verified")
    print("Conflict warning generation: verified")


if __name__ == "__main__":
    main()