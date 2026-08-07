"""Public API for deterministic shared place identity."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from etl.common.normalization.text import (
    clean_optional_text,
)


WASHINGTON_STATE_CODE = "WA"
WASHINGTON_STATE_FIPS = "53"
WASHINGTON_COUNTRY_CODE = "USA"


class PlaceIdentityType(str, Enum):
    """Supported canonical place identity methods."""

    GEOGRAPHIC_FINGERPRINT = "GEOGRAPHIC_FINGERPRINT"
    SOURCE_CONDITION = "SOURCE_CONDITION"


class PlaceSourceCondition(str, Enum):
    """Special source conditions that do not assert exact geography."""

    WASHINGTON_UNSPECIFIED = "WASHINGTON_UNSPECIFIED"


@dataclass(frozen=True)
class PlaceIdentityInput:
    """Source and derived fields used to classify one place."""

    country_code: str | None
    county_name: str | None
    city_name: str | None
    zip4: str | None

    state_code: str = WASHINGTON_STATE_CODE
    state_fips: str = WASHINGTON_STATE_FIPS
    county_fips: str | None = None

    congressional_district_current: str | None = None
    congressional_district_original: str | None = None


@dataclass(frozen=True)
class PlaceIdentity:
    """Deterministic identity assigned to one place observation."""

    identity_key: str
    identity_type: PlaceIdentityType
    source_condition: PlaceSourceCondition | None

    country_code: str
    state_code: str
    state_fips: str

    county_name: str | None
    county_fips: str | None
    city_name: str | None
    zip4: str | None

    congressional_district_current: str | None
    congressional_district_original: str | None


def normalize_code(
    value: object,
) -> str | None:
    """Normalize an optional code value."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    return cleaned.upper()


def normalize_place_text(
    value: object,
) -> str | None:
    """
    Normalize place text conservatively.

    Source spellings remain available in the raw layer.
    """

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    return " ".join(
        cleaned.split()
    ).upper()


def is_washington_unspecified(
    *,
    county_name: str | None,
    city_name: str | None,
    zip4: str | None,
) -> bool:
    """Return whether no substate geography was reported."""

    return (
        county_name is None
        and city_name is None
        and zip4 is None
    )

def encode_identity_component(
    value: str | None,
) -> str:
    """Mirror procurement.place's generated identity expression."""

    if value is None:
        return "-1:"

    return f"{len(value)}:{value}"


def build_geographic_identity_key(
    *,
    country_code: str,
    state_code: str,
    state_fips: str,
    county_name: str | None,
    county_fips: str | None,
    city_name: str | None,
    zip4: str | None,
    congressional_district_current: str | None,
    congressional_district_original: str | None,
) -> str:
    """
    Build the database-compatible shared place identity key.

    The existing generated PostgreSQL column intentionally uses:
        country_code;
        state_fips;
        county_fips;
        city_name;
        zip4.

    State code, county name, and congressional districts are
    descriptive or derivable attributes and are not key components.
    """

    del (
        state_code,
        county_name,
        congressional_district_current,
        congressional_district_original,
    )

    return "|".join(
        [
            encode_identity_component(country_code),
            encode_identity_component(state_fips),
            encode_identity_component(county_fips),
            encode_identity_component(city_name),
            encode_identity_component(zip4),
        ]
    )


def classify_place_identity(
    observation: PlaceIdentityInput,
) -> PlaceIdentity:
    """Classify one Washington place-of-performance observation."""

    country_code = (
        normalize_code(observation.country_code)
        or WASHINGTON_COUNTRY_CODE
    )

    state_code = (
        normalize_code(observation.state_code)
        or WASHINGTON_STATE_CODE
    )

    state_fips = (
        normalize_code(observation.state_fips)
        or WASHINGTON_STATE_FIPS
    )

    county_name = normalize_place_text(
        observation.county_name
    )
    county_fips = normalize_code(
        observation.county_fips
    )
    city_name = normalize_place_text(
        observation.city_name
    )
    zip4 = normalize_place_text(
        observation.zip4
    )

    district_current = normalize_code(
        observation.congressional_district_current
    )
    district_original = normalize_code(
        observation.congressional_district_original
    )

    if country_code != WASHINGTON_COUNTRY_CODE:
        raise ValueError(
            "The current Assistance place identity engine "
            f"supports USA observations only; received "
            f"{country_code!r}."
        )

    if state_code != WASHINGTON_STATE_CODE:
        raise ValueError(
            "The current Assistance place identity engine "
            f"supports Washington observations only; received "
            f"{state_code!r}."
        )

    if state_fips != WASHINGTON_STATE_FIPS:
        raise ValueError(
            "Washington place identity requires state FIPS '53'; "
            f"received {state_fips!r}."
        )

    if is_washington_unspecified(
        county_name=county_name,
        city_name=city_name,
        zip4=zip4,
    ):
        condition = (
            PlaceSourceCondition
            .WASHINGTON_UNSPECIFIED
        )

        return PlaceIdentity(
            identity_key=build_geographic_identity_key(
                country_code=country_code,
                state_code=state_code,
                state_fips=state_fips,
                county_name=None,
                county_fips=None,
                city_name=None,
                zip4=None,
                congressional_district_current=None,
                congressional_district_original=None,
            ),
            identity_type=(
                PlaceIdentityType.SOURCE_CONDITION
            ),
            source_condition=condition,
            country_code=country_code,
            state_code=state_code,
            state_fips=state_fips,
            county_name=None,
            county_fips=None,
            city_name=None,
            zip4=None,
            congressional_district_current=None,
            congressional_district_original=None,
        )

    return PlaceIdentity(
        identity_key=build_geographic_identity_key(
            country_code=country_code,
            state_code=state_code,
            state_fips=state_fips,
            county_name=county_name,
            county_fips=county_fips,
            city_name=city_name,
            zip4=zip4,
            congressional_district_current=(
                district_current
            ),
            congressional_district_original=(
                district_original
            ),
        ),
        identity_type=(
            PlaceIdentityType.GEOGRAPHIC_FINGERPRINT
        ),
        source_condition=None,
        country_code=country_code,
        state_code=state_code,
        state_fips=state_fips,
        county_name=county_name,
        county_fips=county_fips,
        city_name=city_name,
        zip4=zip4,
        congressional_district_current=(
            district_current
        ),
        congressional_district_original=(
            district_original
        ),
    )