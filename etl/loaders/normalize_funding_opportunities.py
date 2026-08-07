"""Normalize funding opportunities from a raw USAspending Assistance batch."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from etl.common.db import get_connection
from etl.common.normalization.canonical import (
    select_canonical,
)
from etl.common.normalization.text import (
    clean_optional_text,
    normalize_comparison_text,
)


EVIDENCE_ROOT = Path("evidence/assistance")


@dataclass(frozen=True)
class GoalsObservation:
    """One goals-text observation for a funding opportunity."""

    funding_opportunity_number: str
    observed_goals_text: str | None
    normalized_goals_text: str
    occurrence_count: int
    first_source_row_number: int
    last_source_row_number: int


@dataclass(frozen=True)
class CanonicalFundingOpportunity:
    """One canonical funding opportunity."""

    funding_opportunity_number: str
    canonical_goals_text: str | None
    observations: tuple[GoalsObservation, ...]

    @property
    def has_goals_conflict(self) -> bool:
        populated = {
            observation.normalized_goals_text
            for observation in self.observations
            if observation.observed_goals_text is not None
        }

        return len(populated) > 1


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize funding opportunities from one raw "
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


def extract_observations(
    cur,
    *,
    load_batch_id: int,
) -> tuple[int, int, list[GoalsObservation]]:
    """
    Extract opportunity-number and goals-text observations.

    Returns:
        raw row count;
        rows missing opportunity number;
        distinct observations.
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
          AND NULLIF(
                BTRIM(
                    raw_record
                    ->> 'funding_opportunity_number'
                ),
                ''
              ) IS NULL;
        """,
        (load_batch_id,),
    )

    missing_number_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT
            BTRIM(
                raw_record
                ->> 'funding_opportunity_number'
            ) AS funding_opportunity_number,

            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'funding_opportunity_goals_text'
                ),
                ''
            ) AS observed_goals_text,

            COUNT(*) AS occurrence_count,

            MIN(source_row_number)
                AS first_source_row_number,

            MAX(source_row_number)
                AS last_source_row_number

        FROM assistance.raw_award_transaction

        WHERE load_batch_id = %s

          AND NULLIF(
                BTRIM(
                    raw_record
                    ->> 'funding_opportunity_number'
                ),
                ''
              ) IS NOT NULL

        GROUP BY
            BTRIM(
                raw_record
                ->> 'funding_opportunity_number'
            ),
            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'funding_opportunity_goals_text'
                ),
                ''
            )

        ORDER BY
            BTRIM(
                raw_record
                ->> 'funding_opportunity_number'
            ),
            COUNT(*) DESC,
            MAX(source_row_number) DESC;
        """,
        (load_batch_id,),
    )

    observations: list[GoalsObservation] = []

    for row in cur.fetchall():
        opportunity_number = clean_optional_text(
            row[0]
        )

        if opportunity_number is None:
            continue

        goals_text = clean_optional_text(
            row[1]
        )

        observations.append(
            GoalsObservation(
                funding_opportunity_number=(
                    opportunity_number
                ),
                observed_goals_text=goals_text,
                normalized_goals_text=(
                    normalize_comparison_text(
                        goals_text
                    )
                    if goals_text is not None
                    else ""
                ),
                occurrence_count=int(row[2]),
                first_source_row_number=int(row[3]),
                last_source_row_number=int(row[4]),
            )
        )

    return (
        raw_row_count,
        missing_number_count,
        observations,
    )


def build_canonical_opportunities(
    observations: list[GoalsObservation],
) -> list[CanonicalFundingOpportunity]:
    """Select one canonical goals text per opportunity number."""

    grouped: dict[
        str,
        list[GoalsObservation],
    ] = defaultdict(list)

    for observation in observations:
        grouped[
            observation.funding_opportunity_number
        ].append(observation)

    opportunities: list[
        CanonicalFundingOpportunity
    ] = []

    for opportunity_number in sorted(grouped):
        selection = select_canonical(
            grouped[opportunity_number],
            key=lambda item: (
                -item.occurrence_count,
                -item.last_source_row_number,
                # Prefer populated goals text over null in a tie.
                item.observed_goals_text is None,
                item.normalized_goals_text,
                item.observed_goals_text or "",
            ),
        )

        opportunities.append(
            CanonicalFundingOpportunity(
                funding_opportunity_number=(
                    opportunity_number
                ),
                canonical_goals_text=(
                    selection.selected
                    .observed_goals_text
                ),
                observations=(
                    selection.ordered_candidates
                ),
            )
        )

    return opportunities


def upsert_opportunities(
    cur,
    opportunities: list[
        CanonicalFundingOpportunity
    ],
) -> tuple[int, int, int]:
    """Insert, update, or leave opportunities unchanged."""

    inserted = 0
    updated = 0
    unchanged = 0

    for opportunity in opportunities:
        cur.execute(
            """
            SELECT funding_opportunity_goals_text
            FROM assistance.funding_opportunity
            WHERE funding_opportunity_number = %s;
            """,
            (
                opportunity
                .funding_opportunity_number,
            ),
        )

        existing = cur.fetchone()

        if existing is None:
            cur.execute(
                """
                INSERT INTO assistance.funding_opportunity (
                    funding_opportunity_number,
                    funding_opportunity_goals_text
                )
                VALUES (%s, %s);
                """,
                (
                    opportunity
                    .funding_opportunity_number,
                    opportunity.canonical_goals_text,
                ),
            )

            inserted += 1

        elif existing[0] == opportunity.canonical_goals_text:
            unchanged += 1

        else:
            cur.execute(
                """
                UPDATE assistance.funding_opportunity
                SET
                    funding_opportunity_goals_text = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE funding_opportunity_number = %s;
                """,
                (
                    opportunity.canonical_goals_text,
                    opportunity
                    .funding_opportunity_number,
                ),
            )

            updated += 1

    return inserted, updated, unchanged


def validate_results(
    cur,
    *,
    opportunities: list[
        CanonicalFundingOpportunity
    ],
) -> None:
    """Validate normalized funding opportunities."""

    expected_numbers = [
        item.funding_opportunity_number
        for item in opportunities
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.funding_opportunity
        WHERE funding_opportunity_number = ANY(%s);
        """,
        (expected_numbers,),
    )

    represented_count = int(
        cur.fetchone()[0]
    )

    if represented_count != len(opportunities):
        raise ValueError(
            "Funding Opportunity validation failed: "
            f"expected={len(opportunities):,}, "
            f"represented={represented_count:,}."
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.funding_opportunity
        WHERE BTRIM(
            funding_opportunity_number
        ) = '';
        """
    )

    blank_number_count = int(
        cur.fetchone()[0]
    )

    if blank_number_count:
        raise ValueError(
            "Funding Opportunity validation found "
            f"{blank_number_count:,} blank identifiers."
        )


def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    missing_number_count: int,
    opportunities: list[
        CanonicalFundingOpportunity
    ],
    inserted: int,
    updated: int,
    unchanged: int,
) -> Path:
    """Write deterministic normalization evidence."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "normalization"
        / "funding_opportunities"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_file = (
        output_directory
        / "funding_opportunity_inventory.csv"
    )

    conflict_file = (
        output_directory
        / "funding_opportunity_conflicts.csv"
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
                "funding_opportunity_number",
                "canonical_goals_text",
                "observed_variant_count",
                "goals_conflict",
            ]
        )

        for opportunity in opportunities:
            writer.writerow(
                [
                    opportunity
                    .funding_opportunity_number,
                    opportunity.canonical_goals_text,
                    len(opportunity.observations),
                    str(
                        opportunity.has_goals_conflict
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
                "funding_opportunity_number",
                "canonical_goals_text",
                "observed_goals_text",
                "normalized_goals_text",
                "occurrence_count",
                "first_source_row_number",
                "last_source_row_number",
                "selected_as_canonical",
            ]
        )

        for opportunity in opportunities:
            if not opportunity.has_goals_conflict:
                continue

            for observation in opportunity.observations:
                writer.writerow(
                    [
                        opportunity
                        .funding_opportunity_number,
                        opportunity
                        .canonical_goals_text,
                        observation.observed_goals_text,
                        observation.normalized_goals_text,
                        observation.occurrence_count,
                        observation
                        .first_source_row_number,
                        observation
                        .last_source_row_number,
                        str(
                            observation.observed_goals_text
                            == opportunity
                            .canonical_goals_text
                        ).upper(),
                    ]
                )

    conflict_count = sum(
        opportunity.has_goals_conflict
        for opportunity in opportunities
    )

    summary_lines = [
        "=" * 72,
        "ETL-005C.3 — FUNDING OPPORTUNITY NORMALIZATION",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        f"Rows missing opportunity number  {missing_number_count:,}",
        f"Distinct funding opportunities . {len(opportunities):,}",
        f"Opportunities inserted ......... {inserted:,}",
        f"Opportunities updated .......... {updated:,}",
        f"Opportunities unchanged ........ {unchanged:,}",
        f"Opportunities with conflicts ... {conflict_count:,}",
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Missing opportunity numbers do not create "
            "placeholder dimension rows."
        ),
        (
            "Canonical selection precedence: occurrence count, "
            "latest source row, populated goals text, "
            "normalized goals text, exact goals text."
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
    print(
        "ETL-005C.3 — Normalize Funding Opportunities"
    )
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            (
                raw_row_count,
                missing_number_count,
                observations,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
            )

            opportunities = (
                build_canonical_opportunities(
                    observations
                )
            )

            inserted, updated, unchanged = (
                upsert_opportunities(
                    cur,
                    opportunities,
                )
            )

            validate_results(
                cur,
                opportunities=opportunities,
            )

        conn.commit()

        evidence_directory = write_evidence(
            load_batch_id=args.load_batch_id,
            raw_row_count=raw_row_count,
            missing_number_count=(
                missing_number_count
            ),
            opportunities=opportunities,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
        )

        conflict_count = sum(
            opportunity.has_goals_conflict
            for opportunity in opportunities
        )

        print()
        print("=" * 72)
        print("ETL-005C.3 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Rows missing opportunity number  "
            f"{missing_number_count:,}"
        )
        print(
            "Distinct funding opportunities . "
            f"{len(opportunities):,}"
        )
        print(
            "Opportunities inserted ......... "
            f"{inserted:,}"
        )
        print(
            "Opportunities updated .......... "
            f"{updated:,}"
        )
        print(
            "Opportunities unchanged ........ "
            f"{unchanged:,}"
        )
        print(
            "Opportunities with conflicts ... "
            f"{conflict_count:,}"
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
            "Funding Opportunity normalization "
            "completed successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Funding Opportunity normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()