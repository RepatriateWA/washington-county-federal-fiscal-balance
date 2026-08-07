"""Normalize Assistance Listings from a raw USAspending Assistance batch."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from etl.common.db import get_connection


EVIDENCE_ROOT = Path("evidence/assistance")

SPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class TitleObservation:
    """One distinct title observed for an Assistance Listing."""

    cfda_number: str
    observed_title: str
    normalized_title: str
    occurrence_count: int
    first_source_row_number: int
    last_source_row_number: int


@dataclass(frozen=True)
class CanonicalListing:
    """Deterministically selected canonical Assistance Listing."""

    cfda_number: str
    canonical_title: str
    canonical_title_normalized: str
    observations: tuple[TitleObservation, ...]

    @property
    def has_title_conflict(self) -> bool:
        return len(self.observations) > 1


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Assistance Listings from one raw "
            "USAspending Assistance load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def clean_text(value: object) -> str | None:
    """Trim a source text value and normalize blank values to null."""

    if value is None:
        return None

    cleaned = str(value).strip()

    return cleaned or None


def normalize_title(value: str) -> str:
    """
    Normalize a title conservatively for comparison.

    Official source wording is retained separately.
    """

    return SPACE_PATTERN.sub(
        " ",
        value.strip(),
    ).upper()


def extract_observations(
    cur,
    *,
    load_batch_id: int,
) -> tuple[int, list[TitleObservation], int]:
    """
    Extract distinct CFDA number-title observations.

    Returns:
        raw row count;
        title observations;
        rows missing either CFDA number or title.
    """

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    raw_row_count = int(cur.fetchone()[0])

    if raw_row_count == 0:
        raise ValueError(
            f"No raw Assistance rows found for load batch "
            f"{load_batch_id}."
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
          AND (
                NULLIF(
                    BTRIM(raw_record ->> 'cfda_number'),
                    ''
                ) IS NULL
             OR NULLIF(
                    BTRIM(raw_record ->> 'cfda_title'),
                    ''
                ) IS NULL
          );
        """,
        (load_batch_id,),
    )

    incomplete_row_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT
            BTRIM(raw_record ->> 'cfda_number')
                AS cfda_number,
            BTRIM(raw_record ->> 'cfda_title')
                AS observed_title,
            COUNT(*) AS occurrence_count,
            MIN(source_row_number)
                AS first_source_row_number,
            MAX(source_row_number)
                AS last_source_row_number
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
          AND NULLIF(
                BTRIM(raw_record ->> 'cfda_number'),
                ''
              ) IS NOT NULL
          AND NULLIF(
                BTRIM(raw_record ->> 'cfda_title'),
                ''
              ) IS NOT NULL
        GROUP BY
            BTRIM(raw_record ->> 'cfda_number'),
            BTRIM(raw_record ->> 'cfda_title')
        ORDER BY
            BTRIM(raw_record ->> 'cfda_number'),
            COUNT(*) DESC,
            MAX(source_row_number) DESC,
            BTRIM(raw_record ->> 'cfda_title');
        """,
        (load_batch_id,),
    )

    observations: list[TitleObservation] = []

    for row in cur.fetchall():
        cfda_number = clean_text(row[0])
        observed_title = clean_text(row[1])

        if cfda_number is None or observed_title is None:
            continue

        observations.append(
            TitleObservation(
                cfda_number=cfda_number,
                observed_title=observed_title,
                normalized_title=normalize_title(
                    observed_title
                ),
                occurrence_count=int(row[2]),
                first_source_row_number=int(row[3]),
                last_source_row_number=int(row[4]),
            )
        )

    return (
        raw_row_count,
        observations,
        incomplete_row_count,
    )


def build_canonical_listings(
    observations: list[TitleObservation],
) -> list[CanonicalListing]:
    """
    Select one canonical title per CFDA number.

    Selection precedence:
        1. highest occurrence count;
        2. latest source-row observation;
        3. normalized title;
        4. exact observed title.
    """

    grouped: dict[
        str,
        list[TitleObservation],
    ] = defaultdict(list)

    for observation in observations:
        grouped[
            observation.cfda_number
        ].append(observation)

    canonical_listings: list[
        CanonicalListing
    ] = []

    for cfda_number in sorted(grouped):
        candidates = sorted(
            grouped[cfda_number],
            key=lambda item: (
                -item.occurrence_count,
                -item.last_source_row_number,
                item.normalized_title,
                item.observed_title,
            ),
        )

        selected = candidates[0]

        canonical_listings.append(
            CanonicalListing(
                cfda_number=cfda_number,
                canonical_title=selected.observed_title,
                canonical_title_normalized=(
                    selected.normalized_title
                ),
                observations=tuple(candidates),
            )
        )

    return canonical_listings


def upsert_listings(
    cur,
    listings: list[CanonicalListing],
) -> tuple[int, int, int]:
    """Insert, update, or leave canonical listings unchanged."""

    inserted = 0
    updated = 0
    unchanged = 0

    for listing in listings:
        cur.execute(
            """
            SELECT
                cfda_title,
                cfda_title_normalized
            FROM assistance.assistance_listing
            WHERE cfda_number = %s;
            """,
            (listing.cfda_number,),
        )

        existing = cur.fetchone()

        proposed = (
            listing.canonical_title,
            listing.canonical_title_normalized,
        )

        if existing is None:
            cur.execute(
                """
                INSERT INTO assistance.assistance_listing (
                    cfda_number,
                    cfda_title,
                    cfda_title_normalized
                )
                VALUES (%s, %s, %s);
                """,
                (
                    listing.cfda_number,
                    listing.canonical_title,
                    listing.canonical_title_normalized,
                ),
            )

            inserted += 1

        elif existing == proposed:
            unchanged += 1

        else:
            cur.execute(
                """
                UPDATE assistance.assistance_listing
                SET
                    cfda_title = %s,
                    cfda_title_normalized = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE cfda_number = %s;
                """,
                (
                    listing.canonical_title,
                    listing.canonical_title_normalized,
                    listing.cfda_number,
                ),
            )

            updated += 1

    return inserted, updated, unchanged


def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    incomplete_row_count: int,
    listings: list[CanonicalListing],
    inserted: int,
    updated: int,
    unchanged: int,
) -> Path:
    """Write deterministic normalization evidence artifacts."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "normalization"
        / "assistance_listings"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_file = (
        output_directory
        / "assistance_listing_inventory.csv"
    )

    conflict_file = (
        output_directory
        / "assistance_listing_conflicts.csv"
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
                "cfda_number",
                "canonical_title",
                "canonical_title_normalized",
                "observed_title_count",
                "title_conflict",
            ]
        )

        for listing in listings:
            writer.writerow(
                [
                    listing.cfda_number,
                    listing.canonical_title,
                    listing.canonical_title_normalized,
                    len(listing.observations),
                    str(
                        listing.has_title_conflict
                    ).upper(),
                ]
            )

    with conflict_file.open(
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
                "cfda_number",
                "canonical_title",
                "observed_title",
                "normalized_title",
                "occurrence_count",
                "first_source_row_number",
                "last_source_row_number",
                "selected_as_canonical",
            ]
        )

        for listing in listings:
            if not listing.has_title_conflict:
                continue

            for observation in listing.observations:
                writer.writerow(
                    [
                        listing.cfda_number,
                        listing.canonical_title,
                        observation.observed_title,
                        observation.normalized_title,
                        observation.occurrence_count,
                        observation.first_source_row_number,
                        observation.last_source_row_number,
                        str(
                            observation.observed_title
                            == listing.canonical_title
                        ).upper(),
                    ]
                )

    conflict_count = sum(
        listing.has_title_conflict
        for listing in listings
    )

    summary_lines = [
        "=" * 72,
        "ETL-005C.1 — ASSISTANCE LISTING NORMALIZATION",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        f"Incomplete listing rows ........ {incomplete_row_count:,}",
        f"Distinct Assistance Listings ... {len(listings):,}",
        f"Listings inserted .............. {inserted:,}",
        f"Listings updated ............... {updated:,}",
        f"Listings unchanged ............. {unchanged:,}",
        f"Listings with title conflicts .. {conflict_count:,}",
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Canonical selection precedence: occurrence count, "
            "latest source row, normalized title, exact title."
        ),
        (
            "All observed title variants are preserved in the "
            "conflict artifact."
        ),
        "",
    ]

    summary_file.write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
        newline="\n",
    )

    return output_directory


def validate_results(
    cur,
    *,
    listings: list[CanonicalListing],
) -> None:
    """Validate the normalized Assistance Listing dimension."""

    expected_count = len(listings)

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.assistance_listing
        WHERE cfda_number = ANY(%s);
        """,
        (
            [
                listing.cfda_number
                for listing in listings
            ],
        ),
    )

    represented_count = int(
        cur.fetchone()[0]
    )

    if represented_count != expected_count:
        raise ValueError(
            "Assistance Listing validation failed: "
            f"expected={expected_count:,}, "
            f"represented={represented_count:,}."
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.assistance_listing
        WHERE BTRIM(cfda_number) = ''
           OR BTRIM(cfda_title) = ''
           OR BTRIM(cfda_title_normalized) = '';
        """
    )

    invalid_count = int(
        cur.fetchone()[0]
    )

    if invalid_count:
        raise ValueError(
            "Assistance Listing validation found "
            f"{invalid_count:,} blank required values."
        )


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print("ETL-005C.1 — Normalize Assistance Listings")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            (
                raw_row_count,
                observations,
                incomplete_row_count,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
            )

            listings = build_canonical_listings(
                observations
            )

            inserted, updated, unchanged = (
                upsert_listings(
                    cur,
                    listings,
                )
            )

            validate_results(
                cur,
                listings=listings,
            )

        conn.commit()

        evidence_directory = write_evidence(
            load_batch_id=args.load_batch_id,
            raw_row_count=raw_row_count,
            incomplete_row_count=incomplete_row_count,
            listings=listings,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
        )

        conflict_count = sum(
            listing.has_title_conflict
            for listing in listings
        )

        print()
        print("=" * 72)
        print("ETL-005C.1 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Incomplete listing rows ........ "
            f"{incomplete_row_count:,}"
        )
        print(
            "Distinct Assistance Listings ... "
            f"{len(listings):,}"
        )
        print(
            "Listings inserted .............. "
            f"{inserted:,}"
        )
        print(
            "Listings updated ............... "
            f"{updated:,}"
        )
        print(
            "Listings unchanged ............. "
            f"{unchanged:,}"
        )
        print(
            "Listings with title conflicts .. "
            f"{conflict_count:,}"
        )
        print(
            "Validation ..................... PASS"
        )
        print(
            f"Evidence directory ............. "
            f"{evidence_directory}"
        )
        print("=" * 72)
        print()
        print(
            "Assistance Listing normalization "
            "completed successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance Listing normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()