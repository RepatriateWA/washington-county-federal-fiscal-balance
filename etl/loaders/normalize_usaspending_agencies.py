"""
ETL-004A.3E — Normalize USAspending agencies.

Builds a canonical federal agency hierarchy from immutable USAspending
award transaction observations.

Identity precedence:
    1. Agency code
    2. Normalized agency name when code is absent

Awarding and funding roles resolve to the same canonical dimension.

Usage:
    python -m etl.loaders.normalize_usaspending_agencies

Optional explicit batch:
    python -m etl.loaders.normalize_usaspending_agencies \
        --load-batch-id 2
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

from etl.common.db import get_connection


COMPLETED_STATUSES = {"COMPLETED", "COMPLETED_WITH_REJECTIONS"}
VALID_LEVELS = {"AGENCY", "SUBAGENCY"}


@dataclass(frozen=True)
class RawAgencyObservation:
    source_row_number: int
    awarding_agency_code: str | None
    awarding_agency_name: str | None
    awarding_subagency_code: str | None
    awarding_subagency_name: str | None
    funding_agency_code: str | None
    funding_agency_name: str | None
    funding_subagency_code: str | None
    funding_subagency_name: str | None


@dataclass
class AgencyCandidate:
    agency_code: str | None
    agency_name: str
    agency_name_normalized: str
    agency_level: str
    parent_agency_code: str | None
    parent_agency_name_normalized: str | None


@dataclass(frozen=True)
class ExistingAgency:
    agency_id: int
    agency_code: str | None
    agency_name: str
    agency_name_normalized: str
    agency_level: str
    parent_agency_id: int | None


@dataclass(frozen=True)
class LoadSummary:
    raw_observations: int
    agencies_discovered: int
    subagencies_discovered: int
    inserted: int
    updated: int
    unchanged: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize USAspending federal agencies."
    )
    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Raw procurement load batch to normalize. Defaults to the latest "
            "completed batch containing raw observations."
        ),
    )
    return parser.parse_args()


def normalize_null(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.upper() in {"NULL", "NONE", "N/A", "NA", "NAN"}:
        return None

    return text


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    return collapse_whitespace(value).upper()


def normalize_code(value: Any) -> str | None:
    text = normalize_null(value)
    if text is None:
        return None
    return collapse_whitespace(text).upper()


def get_target_batch(
    conn,
    requested_batch_id: int | None,
) -> tuple[int, str]:
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch lb
                LEFT JOIN procurement.raw_award_transaction raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status;
                """,
                (requested_batch_id,),
            )
        else:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch lb
                JOIN procurement.raw_award_transaction raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_status IN (
                    'COMPLETED',
                    'COMPLETED_WITH_REJECTIONS'
                )
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status
                ORDER BY lb.load_batch_id DESC
                LIMIT 1;
                """
            )

        row = cur.fetchone()

    if row is None:
        raise ValueError("No qualifying procurement load batch was found.")

    load_batch_id, source_file, load_status, raw_count = row

    if load_status not in COMPLETED_STATUSES:
        raise ValueError(
            f"Load batch {load_batch_id} has status {load_status!r}; "
            "a completed batch is required."
        )

    if int(raw_count) == 0:
        raise ValueError(f"Load batch {load_batch_id} contains no raw rows.")

    return int(load_batch_id), str(source_file)


def read_raw_observations(
    conn,
    load_batch_id: int,
) -> list[RawAgencyObservation]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                source_row_number,
                raw_record ->> 'awarding_agency_code',
                raw_record ->> 'awarding_agency_name',
                raw_record ->> 'awarding_subagency_code',
                raw_record ->> 'awarding_subagency_name',
                raw_record ->> 'funding_agency_code',
                raw_record ->> 'funding_agency_name',
                raw_record ->> 'funding_subagency_code',
                raw_record ->> 'funding_subagency_name'
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s
            ORDER BY
                source_row_number,
                raw_award_transaction_id;
            """,
            (load_batch_id,),
        )
        rows = cur.fetchall()

    observations: list[RawAgencyObservation] = []

    for row in rows:
        observations.append(
            RawAgencyObservation(
                source_row_number=int(row[0]),
                awarding_agency_code=normalize_code(row[1]),
                awarding_agency_name=normalize_null(row[2]),
                awarding_subagency_code=normalize_code(row[3]),
                awarding_subagency_name=normalize_null(row[4]),
                funding_agency_code=normalize_code(row[5]),
                funding_agency_name=normalize_null(row[6]),
                funding_subagency_code=normalize_code(row[7]),
                funding_subagency_name=normalize_null(row[8]),
            )
        )

    return observations


def choose_preferred_name(current: str, incoming: str) -> str:
    current_clean = collapse_whitespace(current)
    incoming_clean = collapse_whitespace(incoming)

    if len(incoming_clean) > len(current_clean):
        return incoming_clean

    return current_clean


def add_candidate(
    candidates: dict[tuple[str, str], AgencyCandidate],
    *,
    agency_code: str | None,
    agency_name: str | None,
    agency_level: str,
    parent_agency_code: str | None = None,
    parent_agency_name: str | None = None,
) -> None:
    if agency_level not in VALID_LEVELS:
        raise ValueError(f"Invalid agency level: {agency_level!r}")

    if agency_name is None and agency_code is None:
        return

    if agency_name is None:
        raise ValueError(
            f"Agency code {agency_code!r} is present without an agency name."
        )

    clean_name = collapse_whitespace(agency_name)
    normalized_name = normalize_name(clean_name)

    identity_value = agency_code or normalized_name
    key = (agency_level, identity_value)

    parent_name_normalized = (
        normalize_name(parent_agency_name)
        if parent_agency_name is not None
        else None
    )

    incoming = AgencyCandidate(
        agency_code=agency_code,
        agency_name=clean_name,
        agency_name_normalized=normalized_name,
        agency_level=agency_level,
        parent_agency_code=parent_agency_code,
        parent_agency_name_normalized=parent_name_normalized,
    )

    existing = candidates.get(key)
    if existing is None:
        candidates[key] = incoming
        return

    if (
        existing.agency_code is not None
        and incoming.agency_code is not None
        and existing.agency_code != incoming.agency_code
    ):
        raise ValueError(
            f"Conflicting agency codes for {clean_name!r}: "
            f"{existing.agency_code!r} and {incoming.agency_code!r}."
        )

    if (
        existing.parent_agency_code is not None
        and incoming.parent_agency_code is not None
        and existing.parent_agency_code != incoming.parent_agency_code
    ):
        raise ValueError(
            f"Conflicting parent agencies for {clean_name!r}: "
            f"{existing.parent_agency_code!r} and "
            f"{incoming.parent_agency_code!r}."
        )

    existing.agency_name = choose_preferred_name(
        existing.agency_name,
        incoming.agency_name,
    )
    existing.agency_name_normalized = normalize_name(existing.agency_name)
    existing.agency_code = existing.agency_code or incoming.agency_code
    existing.parent_agency_code = (
        existing.parent_agency_code or incoming.parent_agency_code
    )
    existing.parent_agency_name_normalized = (
        existing.parent_agency_name_normalized
        or incoming.parent_agency_name_normalized
    )


def build_candidates(
    observations: Iterable[RawAgencyObservation],
) -> list[AgencyCandidate]:
    candidates: dict[tuple[str, str], AgencyCandidate] = {}

    for observation in observations:
        add_candidate(
            candidates,
            agency_code=observation.awarding_agency_code,
            agency_name=observation.awarding_agency_name,
            agency_level="AGENCY",
        )
        add_candidate(
            candidates,
            agency_code=observation.funding_agency_code,
            agency_name=observation.funding_agency_name,
            agency_level="AGENCY",
        )
        add_candidate(
            candidates,
            agency_code=observation.awarding_subagency_code,
            agency_name=observation.awarding_subagency_name,
            agency_level="SUBAGENCY",
            parent_agency_code=observation.awarding_agency_code,
            parent_agency_name=observation.awarding_agency_name,
        )
        add_candidate(
            candidates,
            agency_code=observation.funding_subagency_code,
            agency_name=observation.funding_subagency_name,
            agency_level="SUBAGENCY",
            parent_agency_code=observation.funding_agency_code,
            parent_agency_name=observation.funding_agency_name,
        )

    return sorted(
        candidates.values(),
        key=lambda item: (
            0 if item.agency_level == "AGENCY" else 1,
            item.agency_code or "",
            item.agency_name_normalized,
        ),
    )


def read_existing_agencies(conn) -> list[ExistingAgency]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                agency_id,
                agency_code,
                agency_name,
                agency_name_normalized,
                agency_level,
                parent_agency_id
            FROM procurement.agency
            ORDER BY agency_id;
            """
        )
        rows = cur.fetchall()

    return [
        ExistingAgency(
            agency_id=int(row[0]),
            agency_code=normalize_code(row[1]),
            agency_name=str(row[2]),
            agency_name_normalized=str(row[3]),
            agency_level=str(row[4]),
            parent_agency_id=(
                int(row[5]) if row[5] is not None else None
            ),
        )
        for row in rows
    ]


def build_existing_indexes(
    agencies: Iterable[ExistingAgency],
) -> tuple[
    dict[str, ExistingAgency],
    dict[tuple[str, str], ExistingAgency],
]:
    code_index: dict[str, ExistingAgency] = {}
    name_index: dict[tuple[str, str], ExistingAgency] = {}

    for agency in agencies:
        if agency.agency_code is not None:
            if agency.agency_code in code_index:
                raise ValueError(
                    f"Duplicate agency code already exists: "
                    f"{agency.agency_code}"
                )
            code_index[agency.agency_code] = agency
        else:
            key = (agency.agency_level, agency.agency_name_normalized)
            if key in name_index:
                raise ValueError(
                    f"Duplicate name-only agency already exists: {key!r}"
                )
            name_index[key] = agency

    return code_index, name_index


def resolve_existing(
    candidate: AgencyCandidate,
    code_index: dict[str, ExistingAgency],
    name_index: dict[tuple[str, str], ExistingAgency],
) -> ExistingAgency | None:
    if candidate.agency_code is not None:
        return code_index.get(candidate.agency_code)

    return name_index.get(
        (candidate.agency_level, candidate.agency_name_normalized)
    )


def resolve_parent_id(
    candidate: AgencyCandidate,
    code_index: dict[str, ExistingAgency],
    name_index: dict[tuple[str, str], ExistingAgency],
) -> int | None:
    if candidate.agency_level == "AGENCY":
        return None

    parent: ExistingAgency | None = None

    if candidate.parent_agency_code is not None:
        parent = code_index.get(candidate.parent_agency_code)
    elif candidate.parent_agency_name_normalized is not None:
        parent = name_index.get(
            ("AGENCY", candidate.parent_agency_name_normalized)
        )

    if parent is None:
        raise ValueError(
            f"Unable to resolve parent for subagency "
            f"{candidate.agency_name!r}."
        )

    return parent.agency_id


def apply_candidates(
    conn,
    candidates: list[AgencyCandidate],
) -> tuple[int, int, int]:
    inserted = 0
    updated = 0
    unchanged = 0

    existing = read_existing_agencies(conn)
    code_index, name_index = build_existing_indexes(existing)

    ordered = sorted(
        candidates,
        key=lambda item: 0 if item.agency_level == "AGENCY" else 1,
    )

    with conn.cursor() as cur:
        for candidate in ordered:
            match = resolve_existing(candidate, code_index, name_index)
            parent_agency_id = resolve_parent_id(
                candidate,
                code_index,
                name_index,
            )

            if match is None:
                cur.execute(
                    """
                    INSERT INTO procurement.agency (
                        agency_code,
                        agency_name,
                        agency_name_normalized,
                        parent_agency_id,
                        agency_level
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING agency_id;
                    """,
                    (
                        candidate.agency_code,
                        candidate.agency_name,
                        candidate.agency_name_normalized,
                        parent_agency_id,
                        candidate.agency_level,
                    ),
                )
                agency_id = int(cur.fetchone()[0])
                inserted += 1
            else:
                agency_id = match.agency_id

                differs = any(
                    (
                        match.agency_code != candidate.agency_code,
                        match.agency_name != candidate.agency_name,
                        match.agency_name_normalized
                        != candidate.agency_name_normalized,
                        match.agency_level != candidate.agency_level,
                        match.parent_agency_id != parent_agency_id,
                    )
                )

                if differs:
                    cur.execute(
                        """
                        UPDATE procurement.agency
                        SET
                            agency_code = %s,
                            agency_name = %s,
                            agency_name_normalized = %s,
                            parent_agency_id = %s,
                            agency_level = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE agency_id = %s;
                        """,
                        (
                            candidate.agency_code,
                            candidate.agency_name,
                            candidate.agency_name_normalized,
                            parent_agency_id,
                            candidate.agency_level,
                            agency_id,
                        ),
                    )
                    updated += 1
                else:
                    unchanged += 1

            refreshed = ExistingAgency(
                agency_id=agency_id,
                agency_code=candidate.agency_code,
                agency_name=candidate.agency_name,
                agency_name_normalized=(
                    candidate.agency_name_normalized
                ),
                agency_level=candidate.agency_level,
                parent_agency_id=parent_agency_id,
            )

            if candidate.agency_code is not None:
                code_index[candidate.agency_code] = refreshed
            else:
                name_index[
                    (
                        candidate.agency_level,
                        candidate.agency_name_normalized,
                    )
                ] = refreshed

    return inserted, updated, unchanged


def validate_dimension(
    conn,
    candidates: list[AgencyCandidate],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT agency_code, COUNT(*)
            FROM procurement.agency
            WHERE agency_code IS NOT NULL
            GROUP BY agency_code
            HAVING COUNT(*) > 1;
            """
        )
        duplicate_codes = cur.fetchall()

        cur.execute(
            """
            SELECT agency_level, agency_name_normalized, COUNT(*)
            FROM procurement.agency
            WHERE agency_code IS NULL
            GROUP BY agency_level, agency_name_normalized
            HAVING COUNT(*) > 1;
            """
        )
        duplicate_names = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*)
            FROM procurement.agency
            WHERE agency_name IS NULL
               OR BTRIM(agency_name) = ''
               OR agency_name_normalized IS NULL
               OR BTRIM(agency_name_normalized) = '';
            """
        )
        missing_names = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM procurement.agency
            WHERE agency_level = 'SUBAGENCY'
              AND parent_agency_id IS NULL;
            """
        )
        orphan_subagencies = int(cur.fetchone()[0])

    if duplicate_codes:
        raise ValueError(
            f"Duplicate agency codes found: {duplicate_codes!r}"
        )
    if duplicate_names:
        raise ValueError(
            f"Duplicate name-only agencies found: {duplicate_names!r}"
        )
    if missing_names:
        raise ValueError(
            f"Found {missing_names} agencies without valid names."
        )
    if orphan_subagencies:
        raise ValueError(
            f"Found {orphan_subagencies} orphan subagencies."
        )

    existing = read_existing_agencies(conn)
    code_index, name_index = build_existing_indexes(existing)

    unresolved: list[str] = []

    for candidate in candidates:
        match = resolve_existing(candidate, code_index, name_index)
        if match is None:
            unresolved.append(candidate.agency_name)

    if unresolved:
        raise ValueError(
            f"{len(unresolved)} agency candidates did not resolve: "
            f"{unresolved[:10]!r}"
        )


def print_summary(
    summary: LoadSummary,
    elapsed_seconds: float,
) -> None:
    print()
    print("=" * 68)
    print("ETL-004A.3E SUMMARY")
    print("=" * 68)
    print(
        f"Raw observations examined .............. "
        f"{summary.raw_observations:,}"
    )
    print(
        f"Canonical agencies discovered .......... "
        f"{summary.agencies_discovered:,}"
    )
    print(
        f"Canonical subagencies discovered ....... "
        f"{summary.subagencies_discovered:,}"
    )
    print(f"Agencies inserted ....................... {summary.inserted:,}")
    print(f"Agencies updated ........................ {summary.updated:,}")
    print(f"Agencies unchanged ...................... {summary.unchanged:,}")
    print("Duplicate agency codes .................. 0")
    print("Duplicate name-only agencies ............ 0")
    print("Orphan subagencies ...................... 0")
    print("Unresolved agency references ............ 0")
    print("Validation .............................. PASS")
    print(f"Elapsed time ............................ {elapsed_seconds:.2f} sec")
    print("=" * 68)


def main() -> None:
    args = parse_arguments()
    started = time.perf_counter()

    print("=" * 68)
    print("ETL-004A.3E — Normalize USAspending Agencies")
    print("=" * 68)

    conn = get_connection()

    try:
        load_batch_id, source_file = get_target_batch(
            conn,
            args.load_batch_id,
        )
        print(f"Target raw load batch: {load_batch_id}")
        print(f"Source file: {source_file}")

        observations = read_raw_observations(conn, load_batch_id)
        print(f"Raw observations read: {len(observations):,}")

        candidates = build_candidates(observations)
        agencies_discovered = sum(
            candidate.agency_level == "AGENCY"
            for candidate in candidates
        )
        subagencies_discovered = sum(
            candidate.agency_level == "SUBAGENCY"
            for candidate in candidates
        )

        print(f"Canonical agencies: {agencies_discovered:,}")
        print(f"Canonical subagencies: {subagencies_discovered:,}")

        inserted, updated, unchanged = apply_candidates(
            conn,
            candidates,
        )

        validate_dimension(conn, candidates)
        conn.commit()

        print_summary(
            LoadSummary(
                raw_observations=len(observations),
                agencies_discovered=agencies_discovered,
                subagencies_discovered=subagencies_discovered,
                inserted=inserted,
                updated=updated,
                unchanged=unchanged,
            ),
            time.perf_counter() - started,
        )

        print()
        print("ETL-004A.3E completed successfully.")

    except Exception as exc:
        conn.rollback()
        print()
        print("ETL-004A.3E failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()