"""Normalize Assistance agencies into the shared USAspending agency domain."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass

from etl.common.db import get_connection
from etl.common.normalization.canonical import select_canonical
from etl.common.normalization.text import (
    clean_optional_text,
    normalize_comparison_text,
)


SPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class AgencyObservation:
    """One agency code-name-parent observation."""

    agency_code: str
    agency_name: str
    proposed_level: str
    parent_agency_code: str | None
    source_role: str
    source_row_number: int


@dataclass(frozen=True)
class CanonicalAgency:
    """One canonical shared agency representation."""

    agency_code: str
    agency_name: str
    agency_name_normalized: str
    proposed_level: str
    parent_agency_code: str | None
    observations: tuple[AgencyObservation, ...]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Assistance agencies and subagencies into "
            "the shared USAspending agency domain."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def extract_observations(
    cur,
    *,
    load_batch_id: int,
) -> tuple[int, list[AgencyObservation]]:
    """Extract all populated agency observations from raw Assistance rows."""

    cur.execute(
        """
        SELECT
            source_row_number,

            raw_record ->> 'awarding_agency_code',
            raw_record ->> 'awarding_agency_name',
            raw_record ->> 'awarding_sub_agency_code',
            raw_record ->> 'awarding_sub_agency_name',

            raw_record ->> 'funding_agency_code',
            raw_record ->> 'funding_agency_name',
            raw_record ->> 'funding_sub_agency_code',
            raw_record ->> 'funding_sub_agency_name'

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

    observations: list[AgencyObservation] = []

    for row in rows:
        source_row_number = int(row[0])

        awarding_agency_code = clean_optional_text(row[1])
        awarding_agency_name = clean_optional_text(row[2])
        awarding_subagency_code = clean_optional_text(row[3])
        awarding_subagency_name = clean_optional_text(row[4])

        funding_agency_code = clean_optional_text(row[5])
        funding_agency_name = clean_optional_text(row[6])
        funding_subagency_code = clean_optional_text(row[7])
        funding_subagency_name = clean_optional_text(row[8])

        source_values = (
            (
                awarding_agency_code,
                awarding_agency_name,
                "AGENCY",
                None,
                "AWARDING_AGENCY",
            ),
            (
                awarding_subagency_code,
                awarding_subagency_name,
                "SUBAGENCY",
                awarding_agency_code,
                "AWARDING_SUBAGENCY",
            ),
            (
                funding_agency_code,
                funding_agency_name,
                "AGENCY",
                None,
                "FUNDING_AGENCY",
            ),
            (
                funding_subagency_code,
                funding_subagency_name,
                "SUBAGENCY",
                funding_agency_code,
                "FUNDING_SUBAGENCY",
            ),
        )

        for (
            agency_code,
            agency_name,
            proposed_level,
            parent_agency_code,
            source_role,
        ) in source_values:
            if agency_code is None and agency_name is None:
                continue

            if agency_code is None or agency_name is None:
                raise ValueError(
                    f"Source row {source_row_number:,}: "
                    f"{source_role} has an incomplete code-name pair."
                )

            observations.append(
                AgencyObservation(
                    agency_code=agency_code,
                    agency_name=agency_name,
                    proposed_level=proposed_level,
                    parent_agency_code=parent_agency_code,
                    source_role=source_role,
                    source_row_number=source_row_number,
                )
            )

    return len(rows), observations


def observation_sort_key(
    observation: AgencyObservation,
) -> tuple[int, str, str]:
    """Deterministically order agency observations."""

    return (
        -observation.source_row_number,
        normalize_comparison_text(
            observation.agency_name
        ),
        observation.agency_name,
    )


def build_canonical_agencies(
    observations: list[AgencyObservation],
) -> list[CanonicalAgency]:
    """Build one canonical representation per agency code."""

    grouped: dict[str, list[AgencyObservation]] = defaultdict(list)

    for observation in observations:
        grouped[observation.agency_code].append(
            observation
        )

    agencies: list[CanonicalAgency] = []

    for agency_code in sorted(grouped):
        candidates = grouped[agency_code]

        normalized_names = {
            normalize_comparison_text(item.agency_name)
            for item in candidates
        }

        if len(normalized_names) != 1:
            raise ValueError(
                f"Agency code {agency_code!r} has multiple names: "
                f"{sorted(normalized_names)!r}."
            )

        selection = select_canonical(
            candidates,
            key=observation_sort_key,
        )

        selected = selection.selected

        observed_levels = {
            item.proposed_level
            for item in candidates
        }

        # Some federal entities can be represented in different source
        # roles. Preserve an existing shared level later rather than
        # forcing a reclassification from Assistance alone.
        proposed_level = (
            "AGENCY"
            if "AGENCY" in observed_levels
            else "SUBAGENCY"
        )

        parent_codes = {
            item.parent_agency_code
            for item in candidates
            if item.parent_agency_code is not None
        }

        parent_agency_code = (
            sorted(parent_codes)[0]
            if len(parent_codes) == 1
            else None
        )

        agencies.append(
            CanonicalAgency(
                agency_code=agency_code,
                agency_name=selected.agency_name,
                agency_name_normalized=(
                    normalize_comparison_text(
                        selected.agency_name
                    )
                ),
                proposed_level=proposed_level,
                parent_agency_code=parent_agency_code,
                observations=selection.ordered_candidates,
            )
        )

    return agencies


def load_existing_agencies(
    cur,
) -> dict[str, tuple[int, str, str, int | None]]:
    """Return existing shared agencies by code."""

    cur.execute(
        """
        SELECT
            agency_id,
            agency_code,
            agency_name,
            agency_level,
            parent_agency_id
        FROM procurement.agency
        WHERE agency_code IS NOT NULL
        ORDER BY agency_id;
        """
    )

    lookup: dict[
        str,
        tuple[int, str, str, int | None],
    ] = {}

    for (
        agency_id,
        agency_code,
        agency_name,
        agency_level,
        parent_agency_id,
    ) in cur.fetchall():
        code = str(agency_code).strip()

        if code in lookup:
            raise ValueError(
                f"Existing shared agency code {code!r} "
                "appears more than once."
            )

        lookup[code] = (
            int(agency_id),
            str(agency_name),
            str(agency_level),
            (
                int(parent_agency_id)
                if parent_agency_id is not None
                else None
            ),
        )

    return lookup


def insert_missing_agencies(
    cur,
    *,
    agencies: list[CanonicalAgency],
    existing_lookup: dict[
        str,
        tuple[int, str, str, int | None],
    ],
) -> tuple[int, int]:
    """
    Insert missing shared agencies using PostgreSQL-generated IDs.

    Existing agency names, levels, and hierarchy remain unchanged.
    Top-tier agencies are inserted before subagencies so parent
    relationships can be resolved.
    """

    missing = [
        agency
        for agency in agencies
        if agency.agency_code not in existing_lookup
    ]

    if not missing:
        return 0, 0

    top_tier = [
        agency
        for agency in missing
        if agency.proposed_level == "AGENCY"
    ]

    subagencies = [
        agency
        for agency in missing
        if agency.proposed_level == "SUBAGENCY"
    ]

    inserted_top_tier = 0
    inserted_subagencies = 0

    for agency in top_tier:
        cur.execute(
            """
            INSERT INTO procurement.agency (
                agency_code,
                agency_name,
                agency_name_normalized,
                parent_agency_id,
                agency_level
            )
            VALUES (
                %s,
                %s,
                %s,
                NULL,
                'AGENCY'
            )
            RETURNING agency_id;
            """,
            (
                agency.agency_code,
                agency.agency_name,
                agency.agency_name_normalized,
            ),
        )

        agency_id = int(
            cur.fetchone()[0]
        )

        existing_lookup[agency.agency_code] = (
            agency_id,
            agency.agency_name,
            "AGENCY",
            None,
        )

        inserted_top_tier += 1

    for agency in subagencies:
        parent_agency_id: int | None = None

        if agency.parent_agency_code is not None:
            parent = existing_lookup.get(
                agency.parent_agency_code
            )

            if parent is None:
                raise ValueError(
                    f"Subagency {agency.agency_code!r} has "
                    f"unresolved parent code "
                    f"{agency.parent_agency_code!r}."
                )

            parent_agency_id = parent[0]

        cur.execute(
            """
            INSERT INTO procurement.agency (
                agency_code,
                agency_name,
                agency_name_normalized,
                parent_agency_id,
                agency_level
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                'SUBAGENCY'
            )
            RETURNING agency_id;
            """,
            (
                agency.agency_code,
                agency.agency_name,
                agency.agency_name_normalized,
                parent_agency_id,
            ),
        )

        agency_id = int(
            cur.fetchone()[0]
        )

        existing_lookup[agency.agency_code] = (
            agency_id,
            agency.agency_name,
            "SUBAGENCY",
            parent_agency_id,
        )

        inserted_subagencies += 1

    return (
        inserted_top_tier,
        inserted_subagencies,
    )


def validate_results(
    cur,
    *,
    agencies: list[CanonicalAgency],
) -> dict[str, int]:
    """Validate complete agency-code representation."""

    observed_codes = [
        agency.agency_code
        for agency in agencies
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.agency
        WHERE agency_code = ANY(%s);
        """,
        (observed_codes,),
    )

    represented_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT agency_code
            FROM procurement.agency
            WHERE agency_code = ANY(%s)
            GROUP BY agency_code
            HAVING COUNT(*) > 1
        ) AS duplicates;
        """,
        (observed_codes,),
    )

    duplicate_code_count = int(
        cur.fetchone()[0]
    )

    if represented_count != len(agencies):
        raise ValueError(
            "Agency representation validation failed: "
            f"expected={len(agencies):,}, "
            f"represented={represented_count:,}."
        )

    if duplicate_code_count:
        raise ValueError(
            f"Agency validation found "
            f"{duplicate_code_count:,} duplicate code groups."
        )

    return {
        "represented_count": represented_count,
        "duplicate_code_count": duplicate_code_count,
    }


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print("ETL-005D.4B — Normalize Assistance Agencies")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            (
                raw_row_count,
                observations,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
            )

            agencies = build_canonical_agencies(
                observations
            )

            existing_lookup = load_existing_agencies(
                cur
            )

            existing_before = sum(
                agency.agency_code
                in existing_lookup
                for agency in agencies
            )

            (
                inserted_top_tier,
                inserted_subagencies,
            ) = insert_missing_agencies(
                cur,
                agencies=agencies,
                existing_lookup=existing_lookup,
            )

            validation = validate_results(
                cur,
                agencies=agencies,
            )

        conn.commit()

        inserted_total = (
            inserted_top_tier
            + inserted_subagencies
        )

        print()
        print("=" * 72)
        print("ETL-005D.4B SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Distinct agency codes .......... "
            f"{len(agencies):,}"
        )
        print(
            "Existing shared agencies ....... "
            f"{existing_before:,}"
        )
        print(
            "Top-tier agencies inserted ..... "
            f"{inserted_top_tier:,}"
        )
        print(
            "Subagencies inserted ........... "
            f"{inserted_subagencies:,}"
        )
        print(
            "Total agencies inserted ........ "
            f"{inserted_total:,}"
        )
        print(
            "Duplicate agency codes ......... "
            f"{validation['duplicate_code_count']:,}"
        )
        print(
            "Validation ..................... PASS"
        )
        print("=" * 72)
        print()
        print(
            "Assistance agencies normalized successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance agency normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()