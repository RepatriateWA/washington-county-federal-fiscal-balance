"""Normalize Assistance places into the shared USAspending place domain."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from etl.common.db import get_connection
from etl.common.identity.place_identity import (
    PlaceIdentityInput,
    classify_place_identity,
)
from etl.common.normalization.text import (
    clean_optional_text,
    normalize_comparison_text,
)


EVIDENCE_ROOT = Path("evidence/assistance")

COUNTRY_NAME = "United States"
STATE_CODE = "WA"
STATE_NAME = "Washington"
STATE_FIPS = "53"


@dataclass(frozen=True)
class PlaceObservation:
    """One normalized place observation from a raw Assistance row."""

    source_row_number: int
    assistance_award_unique_key: str

    place_identity_key: str
    place_identity_type: str
    place_source_condition: str | None

    country_code: str
    country_name: str
    state_code: str
    state_name: str
    state_fips: str

    county_name: str | None
    county_fips: str | None

    city_name: str | None
    zip4: str | None

    congressional_district_current: str | None
    congressional_district_original: str | None


@dataclass(frozen=True)
class CanonicalPlace:
    """One deterministic shared place identity."""

    place_identity_key: str
    place_identity_type: str
    place_source_condition: str | None

    country_code: str
    country_name: str
    state_code: str
    state_name: str
    state_fips: str

    county_name: str | None
    county_fips: str | None

    city_name: str | None
    zip4: str | None

    congressional_district_current: str | None
    congressional_district_original: str | None

    observation_count: int
    award_count: int
    source_row_first: int
    source_row_last: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Assistance place-of-performance observations "
            "into the shared USAspending place domain."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def normalize_county_lookup_name(
    value: object,
) -> str | None:
    """Normalize a county name for registry lookup."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    normalized = normalize_comparison_text(cleaned)

    if normalized.endswith(" COUNTY"):
        normalized = normalized[:-7].strip()

    return normalized


def load_washington_counties(
    cur,
) -> dict[str, tuple[str, str]]:
    """
    Load Washington counties by normalized short name.

    Returns:
        normalized source county name ->
        (canonical county name, full county FIPS).
    """

    cur.execute(
        """
        SELECT
            county_name,
            full_fips
        FROM reference.county_registry
        WHERE state_id = (
            SELECT state_id
            FROM reference.state_registry
            WHERE state_abbreviation = 'WA'
        )
        ORDER BY full_fips;
        """
    )

    lookup: dict[str, tuple[str, str]] = {}

    for county_name, full_fips in cur.fetchall():
        canonical_name = str(county_name)
        lookup_name = normalize_county_lookup_name(
            canonical_name
        )

        if lookup_name is None:
            raise ValueError(
                f"County registry contains blank name "
                f"for FIPS {full_fips!r}."
            )

        if lookup_name in lookup:
            raise ValueError(
                f"Duplicate normalized Washington county "
                f"name {lookup_name!r}."
            )

        lookup[lookup_name] = (
            canonical_name,
            str(full_fips),
        )

    if len(lookup) != 39:
        raise ValueError(
            "Washington county registry did not contain "
            f"39 counties; found {len(lookup):,}."
        )

    return lookup

ZIP_5_PATTERN = re.compile(r"^\d{5}$")
ZIP_9_PATTERN = re.compile(r"^\d{9}$")
ZIP_PLUS_4_PATTERN = re.compile(r"^(\d{5})-(\d{4})$")


def normalize_zip4_for_warehouse(
    value: object,
) -> str | None:
    """
    Normalize a source ZIP value to the shared warehouse format.

    Accepted warehouse forms:
        12345
        123456789

    Source ZIP+4 values such as 12345-6789 are stored as 123456789.

    Non-postal source text remains preserved in the immutable raw row
    but is not inserted into procurement.place.zip4.
    """

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    normalized = cleaned.upper()

    if ZIP_5_PATTERN.fullmatch(normalized):
        return normalized

    if ZIP_9_PATTERN.fullmatch(normalized):
        return normalized

    zip_plus_4_match = ZIP_PLUS_4_PATTERN.fullmatch(
        normalized
    )

    if zip_plus_4_match is not None:
        return (
            zip_plus_4_match.group(1)
            + zip_plus_4_match.group(2)
        )

    return None

def extract_observations(
    cur,
    *,
    load_batch_id: int,
    county_lookup: dict[str, tuple[str, str]],
) -> tuple[int, list[PlaceObservation]]:
    """Extract and classify every raw place observation."""

    cur.execute(
        """
        SELECT
            source_row_number,
            assistance_award_unique_key,

            raw_record
                ->> 'primary_place_of_performance_country_code',

            raw_record
                ->> 'primary_place_of_performance_county_name',

            raw_record
                ->> 'primary_place_of_performance_city_name',

            raw_record
                ->> 'primary_place_of_performance_zip_4',

            raw_record
                ->> 'primary_place_of_performance_congressional_district_current',

            raw_record
                ->> 'primary_place_of_performance_congressional_district_original'

        FROM assistance.raw_award_transaction

        WHERE load_batch_id = %s

        ORDER BY source_row_number;
        """,
        (load_batch_id,),
    )

    rows = cur.fetchall()

    if not rows:
        raise ValueError(
            f"No raw Assistance rows found for load batch "
            f"{load_batch_id}."
        )

    observations: list[PlaceObservation] = []

    unresolved_counties: dict[str, int] = defaultdict(int)

    for row in rows:
        source_row_number = int(row[0])

        source_country_code = clean_optional_text(
            row[2]
        )
        source_county_name = clean_optional_text(
            row[3]
        )
        source_city_name = clean_optional_text(
            row[4]
        )
        source_zip4_raw = clean_optional_text(
            row[5]
        )

        source_zip4 = normalize_zip4_for_warehouse(
            source_zip4_raw
        )

        canonical_county_name: str | None = None
        county_fips: str | None = None

        if source_county_name is not None:
            lookup_name = normalize_county_lookup_name(
                source_county_name
            )

            county_match = (
                county_lookup.get(lookup_name)
                if lookup_name is not None
                else None
            )

            if county_match is None:
                unresolved_counties[
                    source_county_name
                ] += 1
            else:
                (
                    canonical_county_name,
                    county_fips,
                ) = county_match

        if source_county_name is not None and county_fips is None:
            continue

        identity = classify_place_identity(
            PlaceIdentityInput(
                country_code=source_country_code,
                state_code=STATE_CODE,
                state_fips=STATE_FIPS,
                county_name=source_county_name,
                county_fips=county_fips,
                city_name=source_city_name,
                zip4=source_zip4,
                congressional_district_current=(
                    clean_optional_text(row[6])
                ),
                congressional_district_original=(
                    clean_optional_text(row[7])
                ),
            )
        )

        observations.append(
            PlaceObservation(
                source_row_number=source_row_number,
                assistance_award_unique_key=str(
                    row[1]
                ),
                place_identity_key=identity.identity_key,
                place_identity_type=(
                    identity.identity_type.value
                ),
                place_source_condition=(
                    identity.source_condition.value
                    if identity.source_condition is not None
                    else None
                ),
                country_code=identity.country_code,
                country_name=COUNTRY_NAME,
                state_code=identity.state_code,
                state_name=STATE_NAME,
                state_fips=identity.state_fips,
                county_name=canonical_county_name,
                county_fips=identity.county_fips,
                city_name=identity.city_name,
                zip4=identity.zip4,
                congressional_district_current=(
                    identity.congressional_district_current
                ),
                congressional_district_original=(
                    identity.congressional_district_original
                ),
            )
        )

    if unresolved_counties:
        examples = sorted(
            unresolved_counties.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )[:20]

        raise ValueError(
            "Place normalization found unresolved county names: "
            f"{examples!r}"
        )

    if len(observations) != len(rows):
        raise ValueError(
            "Place observation extraction did not reconcile: "
            f"raw={len(rows):,}, "
            f"resolved={len(observations):,}."
        )

    return len(rows), observations


def build_canonical_places(
    observations: list[PlaceObservation],
) -> list[CanonicalPlace]:
    """Build one canonical place per deterministic identity key."""

    grouped: dict[
        str,
        list[PlaceObservation],
    ] = defaultdict(list)

    for observation in observations:
        grouped[
            observation.place_identity_key
        ].append(observation)

    places: list[CanonicalPlace] = []

    for identity_key in sorted(grouped):
        candidates = grouped[identity_key]

        identity_types = {
            item.place_identity_type
            for item in candidates
        }

        source_conditions = {
            item.place_source_condition
            for item in candidates
        }

        geographic_values = {
            (
                item.country_code,
                item.state_code,
                item.state_fips,
                item.county_name,
                item.county_fips,
                item.city_name,
                item.zip4,
                item.congressional_district_current,
                item.congressional_district_original,
            )
            for item in candidates
        }

        if len(identity_types) != 1:
            raise ValueError(
                f"Place identity {identity_key!r} has "
                f"multiple identity types."
            )

        if len(source_conditions) != 1:
            raise ValueError(
                f"Place identity {identity_key!r} has "
                f"multiple source conditions."
            )

        if len(geographic_values) != 1:
            raise ValueError(
                f"Place identity {identity_key!r} has "
                "conflicting normalized geography."
            )

        selected = sorted(
            candidates,
            key=lambda item: (
                -item.source_row_number,
                item.place_identity_key,
            ),
        )[0]

        places.append(
            CanonicalPlace(
                place_identity_key=identity_key,
                place_identity_type=(
                    selected.place_identity_type
                ),
                place_source_condition=(
                    selected.place_source_condition
                ),
                country_code=selected.country_code,
                country_name=selected.country_name,
                state_code=selected.state_code,
                state_name=selected.state_name,
                state_fips=selected.state_fips,
                county_name=selected.county_name,
                county_fips=selected.county_fips,
                city_name=selected.city_name,
                zip4=selected.zip4,
                congressional_district_current=(
                    selected.congressional_district_current
                ),
                congressional_district_original=(
                    selected.congressional_district_original
                ),
                observation_count=len(candidates),
                award_count=len(
                    {
                        item.assistance_award_unique_key
                        for item in candidates
                    }
                ),
                source_row_first=min(
                    item.source_row_number
                    for item in candidates
                ),
                source_row_last=max(
                    item.source_row_number
                    for item in candidates
                ),
            )
        )

    return places


def find_existing_place(
    cur,
    place: CanonicalPlace,
):
    """
    Find an existing shared place.

    Matching precedence:
        1. exact place identity key;
        2. exact normalized geography on a legacy row.
    """

    cur.execute(
        """
        SELECT
            place_id,
            country_code,
            country_name,
            state_code,
            state_name,
            state_fips,
            county_name,
            county_fips,
            city_name,
            zip4,
            congressional_district_current,
            congressional_district_original,
            place_identity_key,
            place_identity_type,
            place_source_condition
        FROM procurement.place
        WHERE place_identity_key = %s;
        """,
        (place.place_identity_key,),
    )

    existing = cur.fetchone()

    if existing is not None:
        return existing

    cur.execute(
        """
        SELECT
            place_id,
            country_code,
            country_name,
            state_code,
            state_name,
            state_fips,
            county_name,
            county_fips,
            city_name,
            zip4,
            congressional_district_current,
            congressional_district_original,
            place_identity_key,
            place_identity_type,
            place_source_condition
        FROM procurement.place
        WHERE country_code
                IS NOT DISTINCT FROM %s
          AND state_code
                IS NOT DISTINCT FROM %s
          AND state_fips
                IS NOT DISTINCT FROM %s
          AND county_name
                IS NOT DISTINCT FROM %s
          AND county_fips
                IS NOT DISTINCT FROM %s
          AND city_name
                IS NOT DISTINCT FROM %s
          AND zip4
                IS NOT DISTINCT FROM %s
          AND congressional_district_current
                IS NOT DISTINCT FROM %s
          AND congressional_district_original
                IS NOT DISTINCT FROM %s
        ORDER BY place_id;
        """,
        (
            place.country_code,
            place.state_code,
            place.state_fips,
            place.county_name,
            place.county_fips,
            place.city_name,
            place.zip4,
            place.congressional_district_current,
            place.congressional_district_original,
        ),
    )

    matches = cur.fetchall()

    if len(matches) > 1:
        raise ValueError(
            f"Place identity {place.place_identity_key!r} "
            f"matches {len(matches):,} legacy place rows."
        )

    return matches[0] if matches else None


def merge_optional(
    existing: object,
    proposed: object,
) -> object:
    """Preserve an existing populated value and fill nulls."""

    return proposed if existing is None else existing


def upsert_places(
    cur,
    places: list[CanonicalPlace],
) -> tuple[int, int, int, int]:
    """
    Insert or safely enrich shared place rows.

    procurement.place.place_identity_key is generated by PostgreSQL.
    The loader never inserts or updates that column directly.
    """

    inserted = 0
    updated = 0
    unchanged = 0
    conflicts = 0

    for place in places:
        existing = find_existing_place(
            cur,
            place,
        )

        if existing is None:
            cur.execute(
                """
                INSERT INTO procurement.place (
                    country_code,
                    country_name,
                    state_code,
                    state_name,
                    state_fips,
                    county_name,
                    county_fips,
                    city_name,
                    zip4,
                    congressional_district_current,
                    congressional_district_original,
                    place_identity_type,
                    place_source_condition
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                RETURNING
                    place_id,
                    place_identity_key;
                """,
                (
                    place.country_code,
                    place.country_name,
                    place.state_code,
                    place.state_name,
                    place.state_fips,
                    place.county_name,
                    place.county_fips,
                    place.city_name,
                    place.zip4,
                    place.congressional_district_current,
                    place.congressional_district_original,
                    place.place_identity_type,
                    place.place_source_condition,
                ),
            )

            (
                place_id,
                generated_identity_key,
            ) = cur.fetchone()

            if (
                generated_identity_key
                != place.place_identity_key
            ):
                raise ValueError(
                    f"Inserted place {place_id} generated "
                    f"identity {generated_identity_key!r}, "
                    "but the shared identity engine expected "
                    f"{place.place_identity_key!r}."
                )

            inserted += 1
            continue

        place_id = int(existing[0])

        # find_existing_place() returns:
        #
        #  0  place_id
        #  1  country_code
        #  2  country_name
        #  3  state_code
        #  4  state_name
        #  5  state_fips
        #  6  county_name
        #  7  county_fips
        #  8  city_name
        #  9  zip4
        # 10  congressional_district_current
        # 11  congressional_district_original
        # 12  place_identity_key
        # 13  place_identity_type
        # 14  place_source_condition

        existing_country_code = existing[1]
        existing_country_name = existing[2]
        existing_state_code = existing[3]
        existing_state_name = existing[4]
        existing_state_fips = existing[5]
        existing_county_name = existing[6]
        existing_county_fips = existing[7]
        existing_city_name = existing[8]
        existing_zip4 = existing[9]
        existing_district_current = existing[10]
        existing_district_original = existing[11]
        existing_identity_key = existing[12]
        existing_identity_type = existing[13]
        existing_source_condition = existing[14]

        if (
            existing_identity_key is not None
            and existing_identity_key
            != place.place_identity_key
        ):
            conflicts += 1

            raise ValueError(
                f"Shared place {place_id} already has "
                f"identity {existing_identity_key!r}, but "
                f"Assistance expected "
                f"{place.place_identity_key!r}."
            )

        merged_country_code = merge_optional(
            existing_country_code,
            place.country_code,
        )
        merged_country_name = merge_optional(
            existing_country_name,
            place.country_name,
        )
        merged_state_code = merge_optional(
            existing_state_code,
            place.state_code,
        )
        merged_state_name = merge_optional(
            existing_state_name,
            place.state_name,
        )
        merged_state_fips = merge_optional(
            existing_state_fips,
            place.state_fips,
        )
        merged_county_name = merge_optional(
            existing_county_name,
            place.county_name,
        )
        merged_county_fips = merge_optional(
            existing_county_fips,
            place.county_fips,
        )
        merged_city_name = merge_optional(
            existing_city_name,
            place.city_name,
        )
        merged_zip4 = merge_optional(
            existing_zip4,
            place.zip4,
        )
        merged_district_current = merge_optional(
            existing_district_current,
            place.congressional_district_current,
        )
        merged_district_original = merge_optional(
            existing_district_original,
            place.congressional_district_original,
        )
        merged_identity_type = merge_optional(
            existing_identity_type,
            place.place_identity_type,
        )
        merged_source_condition = merge_optional(
            existing_source_condition,
            place.place_source_condition,
        )

        existing_editable_values = (
            existing_country_code,
            existing_country_name,
            existing_state_code,
            existing_state_name,
            existing_state_fips,
            existing_county_name,
            existing_county_fips,
            existing_city_name,
            existing_zip4,
            existing_district_current,
            existing_district_original,
            existing_identity_type,
            existing_source_condition,
        )

        merged_editable_values = (
            merged_country_code,
            merged_country_name,
            merged_state_code,
            merged_state_name,
            merged_state_fips,
            merged_county_name,
            merged_county_fips,
            merged_city_name,
            merged_zip4,
            merged_district_current,
            merged_district_original,
            merged_identity_type,
            merged_source_condition,
        )

        if (
            merged_editable_values
            == existing_editable_values
        ):
            unchanged += 1
            continue

        cur.execute(
            """
            UPDATE procurement.place
            SET
                country_code = %s,
                country_name = %s,
                state_code = %s,
                state_name = %s,
                state_fips = %s,
                county_name = %s,
                county_fips = %s,
                city_name = %s,
                zip4 = %s,
                congressional_district_current = %s,
                congressional_district_original = %s,
                place_identity_type = %s,
                place_source_condition = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE place_id = %s
            RETURNING place_identity_key;
            """,
            (
                *merged_editable_values,
                place_id,
            ),
        )

        generated_identity_key = cur.fetchone()[0]

        if (
            generated_identity_key
            != place.place_identity_key
        ):
            raise ValueError(
                f"Updated place {place_id} generated "
                f"identity {generated_identity_key!r}, "
                "but the shared identity engine expected "
                f"{place.place_identity_key!r}."
            )

        updated += 1

    return (
        inserted,
        updated,
        unchanged,
        conflicts,
    )


def validate_results(
    cur,
    *,
    places: list[CanonicalPlace],
) -> dict[str, int]:
    """Validate complete place identity representation."""

    identity_keys = [
        place.place_identity_key
        for place in places
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.place
        WHERE place_identity_key = ANY(%s);
        """,
        (identity_keys,),
    )

    represented_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT place_identity_key
            FROM procurement.place
            WHERE place_identity_key = ANY(%s)
            GROUP BY place_identity_key
            HAVING COUNT(*) > 1
        ) AS duplicates;
        """,
        (identity_keys,),
    )

    duplicate_identity_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.place
        WHERE place_identity_key = ANY(%s)
          AND place_identity_type = 'GEOGRAPHIC_FINGERPRINT'
          AND county_name IS NOT NULL
          AND county_fips IS NULL;
        """,
        (identity_keys,),
    )

    unresolved_county_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.place
        WHERE place_identity_key = ANY(%s)
          AND place_identity_type = 'SOURCE_CONDITION'
          AND place_source_condition IS NULL;
        """,
        (identity_keys,),
    )

    invalid_condition_count = int(
        cur.fetchone()[0]
    )

    if represented_count != len(places):
        raise ValueError(
            "Place representation did not reconcile: "
            f"expected={len(places):,}, "
            f"represented={represented_count:,}."
        )

    if duplicate_identity_count:
        raise ValueError(
            f"Place validation found "
            f"{duplicate_identity_count:,} duplicate identities."
        )

    if unresolved_county_count:
        raise ValueError(
            f"Place validation found "
            f"{unresolved_county_count:,} county names without FIPS."
        )

    if invalid_condition_count:
        raise ValueError(
            f"Place validation found "
            f"{invalid_condition_count:,} invalid source conditions."
        )

    identity_type_counts: dict[str, int] = {}

    cur.execute(
        """
        SELECT
            place_identity_type,
            COUNT(*)
        FROM procurement.place
        WHERE place_identity_key = ANY(%s)
        GROUP BY place_identity_type;
        """,
        (identity_keys,),
    )

    for identity_type, count in cur.fetchall():
        identity_type_counts[str(identity_type)] = int(count)

    return {
        "represented_count": represented_count,
        "duplicate_identity_count": duplicate_identity_count,
        "unresolved_county_count": unresolved_county_count,
        "invalid_condition_count": invalid_condition_count,
        "geographic_count": identity_type_counts.get(
            "GEOGRAPHIC_FINGERPRINT",
            0,
        ),
        "source_condition_count": identity_type_counts.get(
            "SOURCE_CONDITION",
            0,
        ),
    }


def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    places: list[CanonicalPlace],
    inserted: int,
    updated: int,
    unchanged: int,
    conflicts: int,
    validation: dict[str, int],
) -> Path:
    """Write place-normalization evidence."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "normalization"
        / "places"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_file = (
        output_directory
        / "place_inventory.csv"
    )

    summary_file = (
        output_directory
        / "normalization_summary.txt"
    )

    with inventory_file.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(
            file,
            lineterminator="\n",
        )

        writer.writerow(
            [
                "place_identity_key",
                "place_identity_type",
                "place_source_condition",
                "country_code",
                "state_code",
                "state_fips",
                "county_name",
                "county_fips",
                "city_name",
                "zip4",
                "observation_count",
                "award_count",
                "source_row_first",
                "source_row_last",
            ]
        )

        for place in places:
            writer.writerow(
                [
                    place.place_identity_key,
                    place.place_identity_type,
                    place.place_source_condition,
                    place.country_code,
                    place.state_code,
                    place.state_fips,
                    place.county_name,
                    place.county_fips,
                    place.city_name,
                    place.zip4,
                    place.observation_count,
                    place.award_count,
                    place.source_row_first,
                    place.source_row_last,
                ]
            )

    summary_lines = [
        "=" * 72,
        "ETL-005D.5B — ASSISTANCE PLACE NORMALIZATION",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        f"Canonical place identities ..... {len(places):,}",
        (
            "Geographic fingerprints ........ "
            f"{validation['geographic_count']:,}"
        ),
        (
            "Source-condition identities .... "
            f"{validation['source_condition_count']:,}"
        ),
        f"Places inserted ................ {inserted:,}",
        f"Places updated ................. {updated:,}",
        f"Places unchanged ............... {unchanged:,}",
        f"Identity conflicts ............. {conflicts:,}",
        (
            "Duplicate identity keys ........ "
            f"{validation['duplicate_identity_count']:,}"
        ),
        (
            "Unresolved county identities ... "
            f"{validation['unresolved_county_count']:,}"
        ),
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Washington state code and state FIPS are derived "
            "from the Washington-scoped source extract."
        ),
        (
            "County FIPS values are derived from the authoritative "
            "Washington county registry."
        ),
        (
            "WASHINGTON_UNSPECIFIED records do not assert "
            "statewide geographic scope."
        ),
        (
            "ZIP values are preserved as source text, including "
            "nonstandard source values."
        ),
        "",
    ]

    summary_file.write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
        newline="\n",
    )

    return output_directory


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print("ETL-005D.5B — Normalize Assistance Places")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            county_lookup = load_washington_counties(
                cur
            )

            (
                raw_row_count,
                observations,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
                county_lookup=county_lookup,
            )

            places = build_canonical_places(
                observations
            )

            (
                inserted,
                updated,
                unchanged,
                conflicts,
            ) = upsert_places(
                cur,
                places,
            )

            validation = validate_results(
                cur,
                places=places,
            )

        conn.commit()

        evidence_directory = write_evidence(
            load_batch_id=args.load_batch_id,
            raw_row_count=raw_row_count,
            places=places,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            conflicts=conflicts,
            validation=validation,
        )

        print()
        print("=" * 72)
        print("ETL-005D.5B SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Canonical place identities ..... "
            f"{len(places):,}"
        )
        print(
            "Geographic fingerprints ........ "
            f"{validation['geographic_count']:,}"
        )
        print(
            "Source-condition identities .... "
            f"{validation['source_condition_count']:,}"
        )
        print(
            "Places inserted ................ "
            f"{inserted:,}"
        )
        print(
            "Places updated ................. "
            f"{updated:,}"
        )
        print(
            "Places unchanged ............... "
            f"{unchanged:,}"
        )
        print(
            "Identity conflicts ............. "
            f"{conflicts:,}"
        )
        print(
            "Unresolved county identities ... "
            f"{validation['unresolved_county_count']:,}"
        )
        print(
            "Validation ..................... PASS"
        )
        print(
            "Evidence directory ............. "
            f"{evidence_directory}"
        )
        print("=" * 72)
        print()
        print(
            "Assistance places normalized successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance place normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()