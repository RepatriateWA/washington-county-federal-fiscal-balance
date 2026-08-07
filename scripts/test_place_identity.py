"""Contract tests for the shared place identity engine."""

from __future__ import annotations

from etl.common.identity.place_identity import (
    PlaceIdentityInput,
    PlaceIdentityType,
    PlaceSourceCondition,
    classify_place_identity,
)


def main() -> None:
    first = classify_place_identity(
        PlaceIdentityInput(
            country_code="USA",
            state_code="WA",
            state_fips="53",
            county_name=" King ",
            county_fips="53033",
            city_name=" Seattle ",
            zip4="98195-0001",
        )
    )

    second = classify_place_identity(
        PlaceIdentityInput(
            country_code="usa",
            state_code="wa",
            state_fips="53",
            county_name="KING",
            county_fips="53033",
            city_name="SEATTLE",
            zip4="98195-0001",
        )
    )

    if first.identity_key != second.identity_key:
        raise AssertionError(
            "Equivalent place observations produced "
            "different fingerprints."
        )

    if (
        first.identity_type
        != PlaceIdentityType.GEOGRAPHIC_FINGERPRINT
    ):
        raise AssertionError(
            "Geographic fingerprint type was not assigned."
        )

    county_only = classify_place_identity(
        PlaceIdentityInput(
            country_code="USA",
            county_name="PIERCE",
            county_fips="53053",
            city_name=None,
            zip4=None,
        )
    )

    if (
        county_only.identity_type
        != PlaceIdentityType.GEOGRAPHIC_FINGERPRINT
    ):
        raise AssertionError(
            "County-only geography should remain a "
            "geographic fingerprint."
        )

    unspecified = classify_place_identity(
        PlaceIdentityInput(
            country_code="USA",
            county_name=None,
            city_name=None,
            zip4=None,
        )
    )

    expected_unspecified_key = (
        "3:USA|2:53|-1:|-1:|-1:"
    )

    if unspecified.identity_key != expected_unspecified_key:
        raise AssertionError(
            "Washington-unspecified database-compatible "
            f"identity key was not assigned: "
            f"{unspecified.identity_key!r}."
        )

    if (
        unspecified.identity_type
        != PlaceIdentityType.SOURCE_CONDITION
    ):
        raise AssertionError(
            "Washington-unspecified identity type was not assigned."
        )

    if (
        unspecified.source_condition
        != PlaceSourceCondition.WASHINGTON_UNSPECIFIED
    ):
        raise AssertionError(
            "Washington-unspecified source condition was not assigned."
        )

    changed_zip = classify_place_identity(
        PlaceIdentityInput(
            country_code="USA",
            county_name="KING",
            county_fips="53033",
            city_name="SEATTLE",
            zip4="98105",
        )
    )

    if changed_zip.identity_key == first.identity_key:
        raise AssertionError(
            "Materially different place attributes produced "
            "the same fingerprint."
        )

    source_text_zip = classify_place_identity(
        PlaceIdentityInput(
            country_code="USA",
            county_name="KING",
            county_fips="53033",
            city_name="SEATTLE",
            zip4="CITY-WIDE",
        )
    )

    if source_text_zip.zip4 != "CITY-WIDE":
        raise AssertionError(
            "Source ZIP text was not preserved."
        )

    try:
        classify_place_identity(
            PlaceIdentityInput(
                country_code="CAN",
                county_name="KING",
                city_name="SEATTLE",
                zip4="98195",
            )
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Non-USA place observation should be rejected."
        )

    try:
        classify_place_identity(
            PlaceIdentityInput(
                country_code="USA",
                state_code="OR",
                county_name="KING",
                city_name="SEATTLE",
                zip4="98195",
            )
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Non-Washington state observation should be rejected."
        )

    print("Shared place identity contract test passed.")
    print()
    print("Verified:")
    print("  deterministic geographic fingerprints")
    print("  conservative comparison normalization")
    print("  county-only geographic identities")
    print("  Washington-unspecified source condition")
    print("  material attribute sensitivity")
    print("  source ZIP-text preservation")
    print("  non-USA rejection")
    print("  non-Washington rejection")


if __name__ == "__main__":
    main()