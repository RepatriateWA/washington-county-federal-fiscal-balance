"""Link Assistance transactions to canonical shared places."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.common.identity.place_identity import (
    PlaceIdentityInput,
    classify_place_identity,
)
from etl.common.normalization.text import clean_optional_text
from etl.common.relationships import (
    count_distinct_configurations,
    group_by_key,
    require_equal_count,
    require_no_failures,
    select_one_per_group,
)


EVIDENCE_ROOT = Path("evidence/assistance")
PAGE_SIZE = 1_000

COUNTRY_CODE = "USA"
STATE_CODE = "WA"
STATE_FIPS = "53"

ZIP_5_PATTERN = re.compile(r"^\d{5}$")
ZIP_9_PATTERN = re.compile(r"^\d{9}$")
ZIP_PLUS_4_PATTERN = re.compile(r"^(\d{5})-(\d{4})$")


@dataclass(frozen=True)
class PlaceRelationshipObservation:
    """One normalized transaction-to-place observation."""

    source_row_number: int
    assistance_award_unique_key: str
    assistance_transaction_unique_key: str
    action_date: date | None

    place_identity_key: str
    place_id: int

    county_name: str | None
    county_fips: str | None
    city_name: str | None
    zip4: str | None
    place_source_condition: str | None


@dataclass(frozen=True)
class AwardPlaceSelection:
    """Latest observed place selected for one award."""

    assistance_award_unique_key: str
    place_identity_key: str
    place_id: int

    county_name: str | None
    county_fips: str | None
    city_name: str | None
    zip4: str | None
    place_source_condition: str | None

    selected_source_row_number: int
    selected_action_date: date | None

    distinct_place_count: int
    observation_count: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Link Assistance transactions to canonical shared "
            "places of performance."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def parse_date(
    value: object,
    *,
    source_row_number: int,
) -> date | None:
    """Parse an optional ISO-style action date."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError as exc:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"invalid action_date {value!r}."
        ) from exc


def normalize_county_lookup_name(
    value: object,
) -> str | None:
    """Normalize a source county name for registry lookup."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    normalized = " ".join(
        cleaned.upper().split()
    )

    if normalized.endswith(" COUNTY"):
        normalized = normalized[:-7].strip()

    return normalized


def normalize_zip4_for_warehouse(
    value: object,
) -> str | None:
    """Normalize ZIP source text to the shared warehouse format."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    normalized = cleaned.upper()

    if ZIP_5_PATTERN.fullmatch(normalized):
        return normalized

    if ZIP_9_PATTERN.fullmatch(normalized):
        return normalized

    match = ZIP_PLUS_4_PATTERN.fullmatch(
        normalized
    )

    if match is not None:
        return match.group(1) + match.group(2)

    # Non-postal source text remains preserved in the raw JSON.
    return None


def load_washington_counties(
    cur,
) -> dict[str, tuple[str, str]]:
    """
    Load authoritative Washington county resolution.

    Returns:
        normalized short county name ->
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
        lookup_name = normalize_county_lookup_name(
            county_name
        )

        if lookup_name is None:
            raise ValueError(
                f"Blank county registry name for "
                f"FIPS {full_fips!r}."
            )

        if lookup_name in lookup:
            raise ValueError(
                f"Duplicate normalized county name "
                f"{lookup_name!r}."
            )

        lookup[lookup_name] = (
            str(county_name),
            str(full_fips),
        )

    require_equal_count(
        label="Washington county registry",
        expected=39,
        actual=len(lookup),
    )

    return lookup


def load_place_lookup(
    cur,
) -> dict[str, tuple[int, str | None]]:
    """
    Load canonical place identities.

    Returns:
        generated place identity key ->
        (place ID, source condition).
    """

    cur.execute(
        """
        SELECT
            place_identity_key,
            place_id,
            place_source_condition
        FROM procurement.place
        WHERE place_identity_key IS NOT NULL
        ORDER BY place_id;
        """
    )

    lookup: dict[
        str,
        tuple[int, str | None],
    ] = {}

    for (
        identity_key,
        place_id,
        source_condition,
    ) in cur.fetchall():
        key = str(identity_key)

        if key in lookup:
            raise ValueError(
                f"Duplicate shared place identity key "
                f"{key!r}."
            )

        lookup[key] = (
            int(place_id),
            (
                str(source_condition)
                if source_condition is not None
                else None
            ),
        )

    return lookup


def extract_observations(
    cur,
    *,
    load_batch_id: int,
    county_lookup: dict[str, tuple[str, str]],
    place_lookup: dict[str, tuple[int, str | None]],
) -> tuple[int, list[PlaceRelationshipObservation]]:
    """Recompute and resolve every raw place observation."""

    cur.execute(
        """
        SELECT
            source_row_number,
            assistance_award_unique_key,
            assistance_transaction_unique_key,

            raw_record ->> 'action_date',

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
            f"No raw Assistance rows found for "
            f"load batch {load_batch_id}."
        )

    observations: list[
        PlaceRelationshipObservation
    ] = []

    unresolved_counties: dict[str, int] = defaultdict(int)
    unresolved_places: dict[str, int] = defaultdict(int)

    for row in rows:
        source_row_number = int(row[0])

        source_county_name = clean_optional_text(
            row[5]
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
                continue

            (
                canonical_county_name,
                county_fips,
            ) = county_match

        normalized_zip4 = (
            normalize_zip4_for_warehouse(
                row[7]
            )
        )

        identity = classify_place_identity(
            PlaceIdentityInput(
                country_code=(
                    clean_optional_text(row[4])
                    or COUNTRY_CODE
                ),
                state_code=STATE_CODE,
                state_fips=STATE_FIPS,
                county_name=source_county_name,
                county_fips=county_fips,
                city_name=clean_optional_text(
                    row[6]
                ),
                zip4=normalized_zip4,
                congressional_district_current=(
                    clean_optional_text(row[8])
                ),
                congressional_district_original=(
                    clean_optional_text(row[9])
                ),
            )
        )

        place_match = place_lookup.get(
            identity.identity_key
        )

        if place_match is None:
            unresolved_places[
                identity.identity_key
            ] += 1
            continue

        place_id, stored_source_condition = (
            place_match
        )

        expected_source_condition = (
            identity.source_condition.value
            if identity.source_condition is not None
            else None
        )

        if (
            stored_source_condition
            != expected_source_condition
        ):
            raise ValueError(
                f"Source row {source_row_number:,}: "
                f"place {place_id} has source condition "
                f"{stored_source_condition!r}, expected "
                f"{expected_source_condition!r}."
            )

        observations.append(
            PlaceRelationshipObservation(
                source_row_number=source_row_number,
                assistance_award_unique_key=str(
                    row[1]
                ),
                assistance_transaction_unique_key=str(
                    row[2]
                ),
                action_date=parse_date(
                    row[3],
                    source_row_number=source_row_number,
                ),
                place_identity_key=(
                    identity.identity_key
                ),
                place_id=place_id,
                county_name=canonical_county_name,
                county_fips=county_fips,
                city_name=identity.city_name,
                zip4=identity.zip4,
                place_source_condition=(
                    expected_source_condition
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
            "Place linking found unresolved county "
            f"names: {examples!r}"
        )

    if unresolved_places:
        examples = sorted(
            unresolved_places.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )[:20]

        raise ValueError(
            "Place linking found unresolved identities: "
            f"{examples!r}"
        )

    require_equal_count(
        label="Place relationship extraction",
        expected=len(rows),
        actual=len(observations),
    )

    return len(rows), observations


def award_selection_sort_key(
    observation: PlaceRelationshipObservation,
) -> tuple[bool, int, int, str]:
    """Define deterministic award-level selection precedence."""

    return (
        observation.action_date is None,
        (
            -observation.action_date.toordinal()
            if observation.action_date is not None
            else 0
        ),
        -observation.source_row_number,
        observation.place_identity_key,
    )


def build_award_selections(
    observations: list[PlaceRelationshipObservation],
) -> list[AwardPlaceSelection]:
    """Select the latest observed place for every award."""

    selected_by_award = select_one_per_group(
        observations,
        group_key=lambda item: (
            item.assistance_award_unique_key
        ),
        selection_key=award_selection_sort_key,
    )

    grouped = group_by_key(
        observations,
        key=lambda item: (
            item.assistance_award_unique_key
        ),
    )

    selections: list[AwardPlaceSelection] = []

    for award_key in sorted(
        selected_by_award
    ):
        selected = selected_by_award[
            award_key
        ]
        candidates = grouped[award_key]

        selections.append(
            AwardPlaceSelection(
                assistance_award_unique_key=award_key,
                place_identity_key=(
                    selected.place_identity_key
                ),
                place_id=selected.place_id,
                county_name=selected.county_name,
                county_fips=selected.county_fips,
                city_name=selected.city_name,
                zip4=selected.zip4,
                place_source_condition=(
                    selected.place_source_condition
                ),
                selected_source_row_number=(
                    selected.source_row_number
                ),
                selected_action_date=(
                    selected.action_date
                ),
                distinct_place_count=(
                    count_distinct_configurations(
                        candidates,
                        configuration_key=lambda item: (
                            item.place_id
                        ),
                    )
                ),
                observation_count=len(candidates),
            )
        )

    return selections


def link_transactions(
    cur,
    *,
    load_batch_id: int,
    observations: list[PlaceRelationshipObservation],
) -> int:
    """
    Populate transaction place-of-performance foreign keys.

    Canonical transaction identity is global across load batches. A
    transaction observed in the current raw batch may have been inserted
    canonically by an earlier batch, so linkage uses the stable
    assistance_transaction_unique_key rather than batch-local provenance.
    """

    values = [
        (
            observation.assistance_transaction_unique_key,
            observation.place_id,
        )
        for observation in observations
    ]

    execute_values(
        cur,
        """
        UPDATE assistance.award_transaction AS transaction
        SET
            place_of_performance_id =
                source.place_id,
            updated_at = CASE
                WHEN transaction.place_of_performance_id
                     IS DISTINCT FROM source.place_id
                THEN CURRENT_TIMESTAMP
                ELSE transaction.updated_at
            END
        FROM (
            VALUES %s
        ) AS source (
            assistance_transaction_unique_key,
            place_id
        )
        WHERE transaction.assistance_transaction_unique_key
              = source.assistance_transaction_unique_key;
        """,
        values,
        template="(%s, %s)",
        page_size=PAGE_SIZE,
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction AS transaction
        WHERE transaction.assistance_transaction_unique_key IN (
            SELECT raw.assistance_transaction_unique_key
            FROM assistance.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        )
          AND transaction.place_of_performance_id IS NOT NULL;
        """,
        (load_batch_id,),
    )

    return int(cur.fetchone()[0])

def validate_results(
    cur,
    *,
    load_batch_id: int,
    raw_row_count: int,
    expected_award_count: int,
) -> dict[str, int]:
    """Validate transaction place linkage and award evidence coverage."""

    cur.execute(
        """
        SELECT
            COUNT(*) AS transaction_count,

            COUNT(*) FILTER (
                WHERE place_of_performance_id IS NULL
            ) AS missing_place_count

        FROM assistance.award_transaction AS transaction

        WHERE transaction.assistance_transaction_unique_key IN (
            SELECT raw.assistance_transaction_unique_key
            FROM assistance.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        );
        """,
        (load_batch_id,),
    )

    (
        transaction_count,
        missing_place_count,
    ) = [
        int(value)
        for value in cur.fetchone()
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction AS transaction

        LEFT JOIN procurement.place AS place
          ON place.place_id
             = transaction.place_of_performance_id

        WHERE transaction.assistance_transaction_unique_key IN (
            SELECT raw.assistance_transaction_unique_key
            FROM assistance.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        )
          AND place.place_id IS NULL;
        """,
        (load_batch_id,),
    )

    orphan_place_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(
            DISTINCT assistance_award_unique_key
        )
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    raw_award_count = int(
        cur.fetchone()[0]
    )

    require_equal_count(
        label="Transaction place coverage",
        expected=raw_row_count,
        actual=transaction_count,
    )

    require_equal_count(
        label="Award place selection coverage",
        expected=raw_award_count,
        actual=expected_award_count,
    )

    failures = {
        "missing_transaction_places": (
            missing_place_count
        ),
        "orphan_transaction_places": (
            orphan_place_count
        ),
    }

    require_no_failures(
        failures
    )

    return {
        "transaction_count": transaction_count,
        "missing_place_count": missing_place_count,
        "orphan_place_count": orphan_place_count,
        "award_selection_count": raw_award_count,
    }


def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    observations: list[PlaceRelationshipObservation],
    selections: list[AwardPlaceSelection],
    validation: dict[str, int],
) -> Path:
    """Write place-linking evidence artifacts."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "enrichment"
        / "places"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    selection_file = (
        output_directory
        / "award_place_selections.csv"
    )

    change_file = (
        output_directory
        / "award_place_changes.csv"
    )

    summary_file = (
        output_directory
        / "link_summary.txt"
    )

    with selection_file.open(
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
                "assistance_award_unique_key",
                "place_id",
                "place_identity_key",
                "county_name",
                "county_fips",
                "city_name",
                "zip4",
                "place_source_condition",
                "selected_source_row_number",
                "selected_action_date",
                "distinct_place_count",
                "observation_count",
            ]
        )

        for selection in selections:
            writer.writerow(
                [
                    selection.assistance_award_unique_key,
                    selection.place_id,
                    selection.place_identity_key,
                    selection.county_name,
                    selection.county_fips,
                    selection.city_name,
                    selection.zip4,
                    selection.place_source_condition,
                    selection.selected_source_row_number,
                    (
                        selection.selected_action_date.isoformat()
                        if selection.selected_action_date
                        is not None
                        else ""
                    ),
                    selection.distinct_place_count,
                    selection.observation_count,
                ]
            )

    observations_by_award = group_by_key(
        observations,
        key=lambda item: (
            item.assistance_award_unique_key
        ),
    )

    selections_by_award = {
        selection.assistance_award_unique_key: (
            selection
        )
        for selection in selections
    }

    changed_award_count = 0

    with change_file.open(
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
                "assistance_award_unique_key",
                "distinct_place_count",
                "source_row_number",
                "assistance_transaction_unique_key",
                "action_date",
                "place_id",
                "place_identity_key",
                "county_name",
                "county_fips",
                "city_name",
                "zip4",
                "place_source_condition",
                "selected_as_latest",
            ]
        )

        for award_key in sorted(
            observations_by_award
        ):
            award_observations = (
                observations_by_award[award_key]
            )

            distinct_place_count = (
                count_distinct_configurations(
                    award_observations,
                    configuration_key=lambda item: (
                        item.place_id
                    ),
                )
            )

            if distinct_place_count <= 1:
                continue

            changed_award_count += 1

            selection = selections_by_award[
                award_key
            ]

            for observation in sorted(
                award_observations,
                key=lambda item: (
                    item.source_row_number,
                    item.place_identity_key,
                ),
            ):
                writer.writerow(
                    [
                        award_key,
                        distinct_place_count,
                        observation.source_row_number,
                        (
                            observation
                            .assistance_transaction_unique_key
                        ),
                        (
                            observation.action_date.isoformat()
                            if observation.action_date
                            is not None
                            else ""
                        ),
                        observation.place_id,
                        observation.place_identity_key,
                        observation.county_name,
                        observation.county_fips,
                        observation.city_name,
                        observation.zip4,
                        observation.place_source_condition,
                        str(
                            observation.source_row_number
                            == selection
                            .selected_source_row_number
                            and observation.place_id
                            == selection.place_id
                        ).upper(),
                    ]
                )

    summary_lines = [
        "=" * 72,
        "ETL-005D.5C — ASSISTANCE PLACE RELATIONSHIP ENRICHMENT",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        (
            "Transaction place relationships "
            f"{validation['transaction_count']:,}"
        ),
        (
            "Award place selections ......... "
            f"{validation['award_selection_count']:,}"
        ),
        (
            "Awards with place changes ...... "
            f"{changed_award_count:,}"
        ),
        (
            "Missing transaction places ..... "
            f"{validation['missing_place_count']:,}"
        ),
        (
            "Orphan transaction places ...... "
            f"{validation['orphan_place_count']:,}"
        ),
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Every normalized transaction links to the place "
            "identity reconstructed from its immutable raw row."
        ),
        (
            "Award-level selections are evidence outputs because "
            "assistance.award currently has no place-of-performance "
            "foreign-key column."
        ),
        (
            "Award selections use latest action date, latest source "
            "row, and place identity key as deterministic precedence."
        ),
        (
            "Non-postal ZIP source text remains preserved in the "
            "raw layer and is null in the normalized place dimension."
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
    print("ETL-005D.5C — Link Assistance Places")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            county_lookup = load_washington_counties(
                cur
            )

            place_lookup = load_place_lookup(
                cur
            )

            (
                raw_row_count,
                observations,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
                county_lookup=county_lookup,
                place_lookup=place_lookup,
            )

            selections = build_award_selections(
                observations
            )

            transaction_coverage = link_transactions(
                cur,
                load_batch_id=args.load_batch_id,
                observations=observations,
            )

            validation = validate_results(
                cur,
                load_batch_id=args.load_batch_id,
                raw_row_count=raw_row_count,
                expected_award_count=len(selections),
            )

        conn.commit()

        evidence_directory = write_evidence(
            load_batch_id=args.load_batch_id,
            raw_row_count=raw_row_count,
            observations=observations,
            selections=selections,
            validation=validation,
        )

        changed_award_count = sum(
            selection.distinct_place_count > 1
            for selection in selections
        )

        print()
        print("=" * 72)
        print("ETL-005D.5C SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Transaction place relationships "
            f"{transaction_coverage:,}"
        )
        print(
            "Award place selections ......... "
            f"{validation['award_selection_count']:,}"
        )
        print(
            "Awards with place changes ...... "
            f"{changed_award_count:,}"
        )
        print(
            "Missing transaction places ..... "
            f"{validation['missing_place_count']:,}"
        )
        print(
            "Orphan transaction places ...... "
            f"{validation['orphan_place_count']:,}"
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
            "Assistance place relationships linked "
            "successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance place relationship enrichment failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()