from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from etl.common.db import get_connection


ROOT = Path(__file__).resolve().parents[2]

EVIDENCE_CSV = (
    ROOT
    / "data"
    / "interim"
    / "omb"
    / "omb_federal_wage_object_class_actuals_2015_2024.csv"
)

ARCHIVE_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "object_class"
)

EXPECTED_OBSERVATIONS = 60

EXPECTED_YEARS = set(
    range(2015, 2025)
)

EXPECTED_CODES = {
    "11.1",
    "11.3",
    "11.5",
    "11.6",
    "11.7",
    "11.8",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def find_latest_archive_manifest() -> Path:
    matches = sorted(
        ARCHIVE_ROOT.glob(
            "omb_object_class_archive_inventory_*.json"
        )
    )

    if not matches:
        raise RuntimeError(
            "No OMB object-class archive inventory manifest found."
        )

    return matches[-1]


def load_evidence_rows() -> list[dict]:
    if not EVIDENCE_CSV.exists():
        raise RuntimeError(
            f"Evidence CSV not found: {EVIDENCE_CSV}"
        )

    with EVIDENCE_CSV.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as f:
        rows = list(
            csv.DictReader(f)
        )

    if len(rows) != EXPECTED_OBSERVATIONS:
        raise RuntimeError(
            "Expected exactly "
            f"{EXPECTED_OBSERVATIONS} evidence rows; "
            f"found {len(rows)}."
        )

    return rows


def validate_evidence_rows(
    rows: list[dict],
) -> None:
    seen_keys = set()
    years_seen = set()
    codes_by_year = {}

    for row_number, row in enumerate(
        rows,
        start=2,
    ):
        fiscal_year = int(
            row["target_fiscal_year"]
        )

        budget_vintage = int(
            row["budget_vintage"]
        )

        object_class_code = (
            row["object_class_code"].strip()
        )

        obligation_millions = int(
            row["obligation_millions"]
        )

        obligation_dollars = int(
            row["obligation_dollars"]
        )

        if fiscal_year not in EXPECTED_YEARS:
            raise RuntimeError(
                f"Row {row_number}: unexpected fiscal year "
                f"{fiscal_year}."
            )

        if budget_vintage != fiscal_year + 2:
            raise RuntimeError(
                f"Row {row_number}: FFY{fiscal_year} "
                f"maps to FY{budget_vintage}; "
                f"expected FY{fiscal_year + 2}."
            )

        if row["value_status"] != "ACTUAL":
            raise RuntimeError(
                f"Row {row_number}: value_status must be ACTUAL."
            )

        if (
            row["accounting_measure"]
            != "OBLIGATIONS_BY_OBJECT_CLASS"
        ):
            raise RuntimeError(
                f"Row {row_number}: unexpected accounting_measure."
            )

        if row["scope"] != "GOVERNMENT_WIDE":
            raise RuntimeError(
                f"Row {row_number}: scope must be GOVERNMENT_WIDE."
            )

        if object_class_code not in EXPECTED_CODES:
            raise RuntimeError(
                f"Row {row_number}: unexpected object class "
                f"{object_class_code}."
            )

        if (
            obligation_dollars
            != obligation_millions * 1_000_000
        ):
            raise RuntimeError(
                f"Row {row_number}: dollar conversion does not "
                "reconcile."
            )

        if (
            row["source_verification"]
            != "MANUALLY_VERIFIED"
        ):
            raise RuntimeError(
                f"Row {row_number}: source_verification is not "
                "MANUALLY_VERIFIED."
            )

        source_path = (
            ROOT
            / row["source_file"]
        )

        if not source_path.exists():
            raise RuntimeError(
                f"Row {row_number}: source PDF not found: "
                f"{source_path}"
            )

        actual_source_sha256 = (
            sha256_file(source_path)
        )

        expected_source_sha256 = (
            row["source_sha256"].strip()
        )

        if (
            actual_source_sha256
            != expected_source_sha256
        ):
            raise RuntimeError(
                f"Row {row_number}: SHA-256 mismatch for "
                f"{source_path}"
            )

        key = (
            fiscal_year,
            budget_vintage,
            object_class_code,
        )

        if key in seen_keys:
            raise RuntimeError(
                f"Duplicate evidence key: {key}"
            )

        seen_keys.add(
            key
        )

        years_seen.add(
            fiscal_year
        )

        codes_by_year.setdefault(
            fiscal_year,
            set(),
        ).add(
            object_class_code
        )

    if years_seen != EXPECTED_YEARS:
        raise RuntimeError(
            "Evidence does not contain exactly "
            "FFY2015-FFY2024."
        )

    for fiscal_year in sorted(
        EXPECTED_YEARS
    ):
        if (
            codes_by_year.get(
                fiscal_year,
                set(),
            )
            != EXPECTED_CODES
        ):
            raise RuntimeError(
                f"FFY{fiscal_year}: object-class "
                "coverage failure."
            )


def create_load_batch(
    conn,
    *,
    archive_manifest: Path,
    archive_sha256: str,
    evidence_sha256: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO omb.object_class_load_batch (
                source_dataset,
                source_file,
                source_sha256,
                evidence_file,
                evidence_sha256,
                fiscal_year_start,
                fiscal_year_end,
                expected_observation_count,
                source_verification,
                load_status,
                notes
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                2015,
                2024,
                60,
                'MANUALLY_VERIFIED_AND_AUTOMATED_VALIDATED',
                'STARTED',
                %s
            )
            RETURNING load_batch_id
            """,
            (
                "OMB_OBJECT_CLASS_ANALYSIS",
                str(
                    archive_manifest.relative_to(
                        ROOT
                    )
                ),
                archive_sha256,
                str(
                    EVIDENCE_CSV.relative_to(
                        ROOT
                    )
                ),
                evidence_sha256,
                (
                    "Initial WCFFBP load of certified "
                    "government-wide OMB wage object-class "
                    "actual observations for FFY2015-FFY2024. "
                    "Six atomic object classes per fiscal year; "
                    "derived wage controls are not stored here."
                ),
            ),
        )

        return cur.fetchone()[0]


def insert_observations(
    conn,
    *,
    load_batch_id: int,
    rows: list[dict],
) -> int:
    inserted = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO omb.object_class_observation (
                    load_batch_id,
                    target_fiscal_year,
                    budget_vintage,
                    value_status,
                    accounting_measure,
                    scope,
                    object_class_code,
                    object_class_description,
                    obligation_millions,
                    obligation_dollars,
                    source_page,
                    source_file,
                    source_sha256,
                    source_verification
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    load_batch_id,
                    int(
                        row["target_fiscal_year"]
                    ),
                    int(
                        row["budget_vintage"]
                    ),
                    row["value_status"],
                    row["accounting_measure"],
                    row["scope"],
                    row["object_class_code"],
                    row[
                        "object_class_description"
                    ],
                    int(
                        row["obligation_millions"]
                    ),
                    int(
                        row["obligation_dollars"]
                    ),
                    int(
                        row["source_page"]
                    ),
                    row["source_file"],
                    row["source_sha256"],
                    row["source_verification"],
                ),
            )

            inserted += 1

    return inserted


def validate_database_rows(
    conn,
    load_batch_id: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT target_fiscal_year)
                    AS fiscal_years,
                COUNT(DISTINCT object_class_code)
                    AS object_classes
            FROM omb.object_class_observation
            WHERE load_batch_id = %s
            """,
            (load_batch_id,),
        )

        (
            total_rows,
            fiscal_years,
            object_classes,
        ) = cur.fetchone()

        if total_rows != 60:
            raise RuntimeError(
                "Database validation failed: "
                f"expected 60 rows, found {total_rows}."
            )

        if fiscal_years != 10:
            raise RuntimeError(
                "Database validation failed: "
                f"expected 10 fiscal years, found "
                f"{fiscal_years}."
            )

        if object_classes != 6:
            raise RuntimeError(
                "Database validation failed: "
                f"expected 6 object classes, found "
                f"{object_classes}."
            )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    target_fiscal_year
                FROM omb.object_class_observation
                WHERE load_batch_id = %s
                GROUP BY target_fiscal_year
                HAVING
                    COUNT(*) <> 6
                    OR COUNT(DISTINCT object_class_code) <> 6
            ) bad
            """,
            (load_batch_id,),
        )

        bad_year_count = (
            cur.fetchone()[0]
        )

        if bad_year_count != 0:
            raise RuntimeError(
                "Database validation failed: "
                f"{bad_year_count} fiscal-year groups "
                "do not contain exactly six unique "
                "object classes."
            )


def mark_batch_completed(
    conn,
    *,
    load_batch_id: int,
    inserted_rows: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE omb.object_class_load_batch
            SET
                actual_observation_count = %s,
                load_status = 'COMPLETED',
                completed_at = CURRENT_TIMESTAMP
            WHERE load_batch_id = %s
            """,
            (
                inserted_rows,
                load_batch_id,
            ),
        )


def main() -> None:
    archive_manifest = (
        find_latest_archive_manifest()
    )

    evidence_sha256 = sha256_file(
        EVIDENCE_CSV
    )

    archive_sha256 = sha256_file(
        archive_manifest
    )

    rows = load_evidence_rows()

    validate_evidence_rows(
        rows
    )

    print(
        f"Evidence CSV:      {EVIDENCE_CSV}"
    )

    print(
        f"Evidence SHA-256:  {evidence_sha256}"
    )

    print(
        f"Archive manifest:  {archive_manifest}"
    )

    print(
        f"Archive SHA-256:   {archive_sha256}"
    )

    print()
    print(
        "Pre-load evidence validation: PASSED"
    )

    conn = get_connection()

    try:
        load_batch_id = create_load_batch(
            conn,
            archive_manifest=archive_manifest,
            archive_sha256=archive_sha256,
            evidence_sha256=evidence_sha256,
        )

        print(
            f"Created OMB load_batch_id="
            f"{load_batch_id}"
        )

        inserted_rows = insert_observations(
            conn,
            load_batch_id=load_batch_id,
            rows=rows,
        )

        if (
            inserted_rows
            != EXPECTED_OBSERVATIONS
        ):
            raise RuntimeError(
                "Expected to insert 60 rows; "
                f"inserted {inserted_rows}."
            )

        validate_database_rows(
            conn,
            load_batch_id,
        )

        mark_batch_completed(
            conn,
            load_batch_id=load_batch_id,
            inserted_rows=inserted_rows,
        )

        conn.commit()

        print()
        print("=" * 72)
        print(
            "OMB WAGE OBJECT-CLASS LOAD COMPLETE"
        )
        print("=" * 72)

        print(
            f"Load batch ID:      {load_batch_id}"
        )

        print(
            f"Rows loaded:        {inserted_rows}"
        )

        print(
            "Fiscal years:       FFY2015-FFY2024"
        )

        print(
            "Object classes:     "
            "11.1, 11.3, 11.5, 11.6, 11.7, 11.8"
        )

        print(
            "Value status:       ACTUAL"
        )

        print(
            "Scope:              GOVERNMENT_WIDE"
        )

        print(
            "Database validation: PASSED"
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()