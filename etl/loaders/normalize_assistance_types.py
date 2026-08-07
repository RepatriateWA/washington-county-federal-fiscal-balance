"""Normalize USAspending Assistance Types from one raw load batch."""

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
class DescriptionObservation:
    """One description observed for an Assistance Type code."""

    assistance_type_code: str
    observed_description: str
    normalized_description: str
    occurrence_count: int
    first_source_row_number: int
    last_source_row_number: int


@dataclass(frozen=True)
class CanonicalAssistanceType:
    """One canonical Assistance Type."""

    assistance_type_code: str
    canonical_description: str
    canonical_description_normalized: str
    observations: tuple[DescriptionObservation, ...]

    @property
    def has_description_conflict(self) -> bool:
        return len(self.observations) > 1


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Assistance Types from one raw "
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
    """Trim a source value and normalize blanks to null."""

    if value is None:
        return None

    cleaned = str(value).strip()

    return cleaned or None


def normalize_description(value: str) -> str:
    """Normalize a description conservatively for comparison."""

    return SPACE_PATTERN.sub(
        " ",
        value.strip(),
    ).upper()


def extract_observations(
    cur,
    *,
    load_batch_id: int,
) -> tuple[int, list[DescriptionObservation], int]:
    """
    Extract Assistance Type observations.

    Returns:
        raw row count;
        distinct code-description observations;
        incomplete row count.
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
                    BTRIM(
                        raw_record
                        ->> 'assistance_type_code'
                    ),
                    ''
                ) IS NULL
             OR NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'assistance_type_description'
                    ),
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
            BTRIM(
                raw_record
                ->> 'assistance_type_code'
            ) AS assistance_type_code,

            BTRIM(
                raw_record
                ->> 'assistance_type_description'
            ) AS observed_description,

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
                    ->> 'assistance_type_code'
                ),
                ''
              ) IS NOT NULL

          AND NULLIF(
                BTRIM(
                    raw_record
                    ->> 'assistance_type_description'
                ),
                ''
              ) IS NOT NULL

        GROUP BY
            BTRIM(
                raw_record
                ->> 'assistance_type_code'
            ),
            BTRIM(
                raw_record
                ->> 'assistance_type_description'
            )

        ORDER BY
            BTRIM(
                raw_record
                ->> 'assistance_type_code'
            ),
            COUNT(*) DESC,
            MAX(source_row_number) DESC,
            BTRIM(
                raw_record
                ->> 'assistance_type_description'
            );
        """,
        (load_batch_id,),
    )

    observations: list[
        DescriptionObservation
    ] = []

    for row in cur.fetchall():
        type_code = clean_text(row[0])
        description = clean_text(row[1])

        if type_code is None or description is None:
            continue

        observations.append(
            DescriptionObservation(
                assistance_type_code=type_code,
                observed_description=description,
                normalized_description=(
                    normalize_description(description)
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


def build_canonical_types(
    observations: list[DescriptionObservation],
) -> list[CanonicalAssistanceType]:
    """
    Select one canonical description per Assistance Type code.

    Selection precedence:
        1. highest occurrence count;
        2. latest source-row observation;
        3. normalized description;
        4. exact observed description.
    """

    grouped: dict[
        str,
        list[DescriptionObservation],
    ] = defaultdict(list)

    for observation in observations:
        grouped[
            observation.assistance_type_code
        ].append(observation)

    canonical_types: list[
        CanonicalAssistanceType
    ] = []

    for type_code in sorted(grouped):
        candidates = sorted(
            grouped[type_code],
            key=lambda item: (
                -item.occurrence_count,
                -item.last_source_row_number,
                item.normalized_description,
                item.observed_description,
            ),
        )

        selected = candidates[0]

        canonical_types.append(
            CanonicalAssistanceType(
                assistance_type_code=type_code,
                canonical_description=(
                    selected.observed_description
                ),
                canonical_description_normalized=(
                    selected.normalized_description
                ),
                observations=tuple(candidates),
            )
        )

    return canonical_types


def upsert_types(
    cur,
    assistance_types: list[
        CanonicalAssistanceType
    ],
) -> tuple[int, int, int]:
    """Insert, update, or leave Assistance Types unchanged."""

    inserted = 0
    updated = 0
    unchanged = 0

    for assistance_type in assistance_types:
        cur.execute(
            """
            SELECT
                assistance_type_description,
                assistance_type_description_normalized
            FROM assistance.assistance_type
            WHERE assistance_type_code = %s;
            """,
            (
                assistance_type.assistance_type_code,
            ),
        )

        existing = cur.fetchone()

        proposed = (
            assistance_type.canonical_description,
            (
                assistance_type
                .canonical_description_normalized
            ),
        )

        if existing is None:
            cur.execute(
                """
                INSERT INTO assistance.assistance_type (
                    assistance_type_code,
                    assistance_type_description,
                    assistance_type_description_normalized
                )
                VALUES (%s, %s, %s);
                """,
                (
                    assistance_type.assistance_type_code,
                    assistance_type.canonical_description,
                    (
                        assistance_type
                        .canonical_description_normalized
                    ),
                ),
            )

            inserted += 1

        elif existing == proposed:
            unchanged += 1

        else:
            cur.execute(
                """
                UPDATE assistance.assistance_type
                SET
                    assistance_type_description = %s,
                    assistance_type_description_normalized = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE assistance_type_code = %s;
                """,
                (
                    assistance_type.canonical_description,
                    (
                        assistance_type
                        .canonical_description_normalized
                    ),
                    assistance_type.assistance_type_code,
                ),
            )

            updated += 1

    return inserted, updated, unchanged


def validate_results(
    cur,
    *,
    assistance_types: list[
        CanonicalAssistanceType
    ],
) -> None:
    """Validate the Assistance Type dimension."""

    expected_codes = [
        item.assistance_type_code
        for item in assistance_types
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.assistance_type
        WHERE assistance_type_code = ANY(%s);
        """,
        (expected_codes,),
    )

    represented_count = int(
        cur.fetchone()[0]
    )

    if represented_count != len(
        assistance_types
    ):
        raise ValueError(
            "Assistance Type validation failed: "
            f"expected={len(assistance_types):,}, "
            f"represented={represented_count:,}."
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.assistance_type
        WHERE BTRIM(assistance_type_code) = ''
           OR BTRIM(
                assistance_type_description
              ) = ''
           OR BTRIM(
                assistance_type_description_normalized
              ) = '';
        """
    )

    invalid_count = int(
        cur.fetchone()[0]
    )

    if invalid_count:
        raise ValueError(
            "Assistance Type validation found "
            f"{invalid_count:,} blank required values."
        )


def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    incomplete_row_count: int,
    assistance_types: list[
        CanonicalAssistanceType
    ],
    inserted: int,
    updated: int,
    unchanged: int,
) -> Path:
    """Write Assistance Type normalization evidence."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "normalization"
        / "assistance_types"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_file = (
        output_directory
        / "assistance_type_inventory.csv"
    )

    conflict_file = (
        output_directory
        / "assistance_type_conflicts.csv"
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
                "assistance_type_code",
                "canonical_description",
                "canonical_description_normalized",
                "observed_description_count",
                "description_conflict",
            ]
        )

        for assistance_type in assistance_types:
            writer.writerow(
                [
                    assistance_type.assistance_type_code,
                    assistance_type.canonical_description,
                    (
                        assistance_type
                        .canonical_description_normalized
                    ),
                    len(
                        assistance_type.observations
                    ),
                    str(
                        assistance_type
                        .has_description_conflict
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
                "assistance_type_code",
                "canonical_description",
                "observed_description",
                "normalized_description",
                "occurrence_count",
                "first_source_row_number",
                "last_source_row_number",
                "selected_as_canonical",
            ]
        )

        for assistance_type in assistance_types:
            if not (
                assistance_type
                .has_description_conflict
            ):
                continue

            for observation in (
                assistance_type.observations
            ):
                writer.writerow(
                    [
                        (
                            assistance_type
                            .assistance_type_code
                        ),
                        (
                            assistance_type
                            .canonical_description
                        ),
                        observation.observed_description,
                        observation.normalized_description,
                        observation.occurrence_count,
                        (
                            observation
                            .first_source_row_number
                        ),
                        (
                            observation
                            .last_source_row_number
                        ),
                        str(
                            observation.observed_description
                            == assistance_type
                            .canonical_description
                        ).upper(),
                    ]
                )

    conflict_count = sum(
        item.has_description_conflict
        for item in assistance_types
    )

    summary_lines = [
        "=" * 72,
        "ETL-005C.2 — ASSISTANCE TYPE NORMALIZATION",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        f"Incomplete type rows ........... {incomplete_row_count:,}",
        f"Distinct Assistance Types ...... {len(assistance_types):,}",
        f"Types inserted ................. {inserted:,}",
        f"Types updated .................. {updated:,}",
        f"Types unchanged ................ {unchanged:,}",
        f"Types with description conflicts {conflict_count:,}",
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Canonical selection precedence: occurrence count, "
            "latest source row, normalized description, "
            "exact description."
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
    print("ETL-005C.2 — Normalize Assistance Types")
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

            assistance_types = (
                build_canonical_types(
                    observations
                )
            )

            inserted, updated, unchanged = (
                upsert_types(
                    cur,
                    assistance_types,
                )
            )

            validate_results(
                cur,
                assistance_types=assistance_types,
            )

        conn.commit()

        evidence_directory = write_evidence(
            load_batch_id=args.load_batch_id,
            raw_row_count=raw_row_count,
            incomplete_row_count=incomplete_row_count,
            assistance_types=assistance_types,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
        )

        conflict_count = sum(
            item.has_description_conflict
            for item in assistance_types
        )

        print()
        print("=" * 72)
        print("ETL-005C.2 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Incomplete type rows ........... "
            f"{incomplete_row_count:,}"
        )
        print(
            "Distinct Assistance Types ...... "
            f"{len(assistance_types):,}"
        )
        print(
            "Types inserted ................. "
            f"{inserted:,}"
        )
        print(
            "Types updated .................. "
            f"{updated:,}"
        )
        print(
            "Types unchanged ................ "
            f"{unchanged:,}"
        )
        print(
            "Types with description conflicts "
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
            "Assistance Type normalization "
            "completed successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance Type normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()