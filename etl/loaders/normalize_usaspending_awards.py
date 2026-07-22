"""
ETL-004A.3A — Normalize USAspending Awards.
"""

import argparse
from datetime import date, datetime
from typing import Any

from etl.common.db import get_connection


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize USAspending awards from raw JSONB."
    )
    parser.add_argument("--load-batch-id", type=int, default=None)
    return parser.parse_args()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def parse_date(
    value: Any,
    *,
    field_name: str,
    source_row_number: int,
) -> date | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None

    normalized = cleaned.replace("Z", "+00:00")
    try:
        if "T" in normalized or " " in normalized:
            return datetime.fromisoformat(normalized).date()
        return date.fromisoformat(normalized[:10])
    except ValueError as exc:
        raise ValueError(
            f"Invalid {field_name} value {cleaned!r} "
            f"at source row {source_row_number}."
        ) from exc


def get_target_load_batch_id(conn, requested_batch_id: int | None) -> int:
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch lb
                LEFT JOIN procurement.raw_award_transaction raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY lb.load_batch_id, lb.load_status;
                """,
                (requested_batch_id,),
            )
            row = cur.fetchone()

            if row is None:
                raise ValueError(
                    f"Load batch {requested_batch_id} does not exist."
                )

            load_batch_id, load_status, raw_rows = row

            if load_status not in {
                "COMPLETED",
                "COMPLETED_WITH_REJECTIONS",
            }:
                raise ValueError(
                    f"Load batch {load_batch_id} has status "
                    f"{load_status!r}; a completed batch is required."
                )

            if raw_rows == 0:
                raise ValueError(
                    f"Load batch {load_batch_id} contains no raw rows."
                )

            return int(load_batch_id)

        cur.execute(
            """
            SELECT raw.load_batch_id
            FROM procurement.raw_award_transaction raw
            JOIN procurement.load_batch lb
                ON lb.load_batch_id = raw.load_batch_id
            WHERE lb.load_status IN (
                'COMPLETED',
                'COMPLETED_WITH_REJECTIONS'
            )
            GROUP BY raw.load_batch_id
            ORDER BY raw.load_batch_id DESC
            LIMIT 1;
            """
        )
        row = cur.fetchone()

    if row is None:
        raise ValueError(
            "No completed procurement load batch containing raw rows was found."
        )

    return int(row[0])


def read_raw_award_rows(
    conn,
    *,
    load_batch_id: int,
) -> list[tuple[int, dict[str, Any]]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_row_number, raw_record
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s
            ORDER BY source_row_number, raw_award_transaction_id;
            """,
            (load_batch_id,),
        )
        rows = cur.fetchall()

    return [
        (int(source_row_number), raw_record)
        for source_row_number, raw_record in rows
    ]


def build_award_records(
    raw_rows: list[tuple[int, dict[str, Any]]],
    *,
    load_batch_id: int,
) -> dict[str, dict[str, Any]]:
    awards: dict[str, dict[str, Any]] = {}

    for source_row_number, raw_record in raw_rows:
        generated_id = clean_text(
            raw_record.get("contract_award_unique_key")
        )

        if generated_id is None:
            raise ValueError(
                "Missing contract_award_unique_key at source row "
                f"{source_row_number}."
            )

        start_date = parse_date(
            raw_record.get("period_of_performance_start_date"),
            field_name="period_of_performance_start_date",
            source_row_number=source_row_number,
        )
        end_date = parse_date(
            raw_record.get("period_of_performance_current_end_date"),
            field_name="period_of_performance_current_end_date",
            source_row_number=source_row_number,
        )

        if generated_id not in awards:
            awards[generated_id] = {
                "generated_unique_award_id": generated_id,
                "piid": None,
                "parent_award_id": None,
                "award_type_code": None,
                "award_type_description": None,
                "award_description": None,
                "period_of_performance_start": None,
                "period_of_performance_end": None,
                "first_load_batch_id": load_batch_id,
                "last_load_batch_id": load_batch_id,
            }

        award = awards[generated_id]

        values = {
            "piid": clean_text(raw_record.get("award_id_piid")),
            "parent_award_id": clean_text(
                raw_record.get("parent_award_id_piid")
            ),
            "award_type_code": clean_text(
                raw_record.get("award_type_code")
            ),
            "award_type_description": clean_text(
                raw_record.get("award_type")
            ),
            "award_description": clean_text(
                raw_record.get(
                    "prime_award_base_transaction_description"
                )
            ),
        }

        for field_name, value in values.items():
            if value is not None:
                award[field_name] = value

        current_start = award["period_of_performance_start"]
        if start_date is not None and (
            current_start is None or start_date < current_start
        ):
            award["period_of_performance_start"] = start_date

        current_end = award["period_of_performance_end"]
        if end_date is not None and (
            current_end is None or end_date > current_end
        ):
            award["period_of_performance_end"] = end_date

    return awards


def upsert_awards(
    conn,
    *,
    awards: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    sql = """
        INSERT INTO procurement.award (
            generated_unique_award_id,
            piid,
            parent_award_id,
            award_type_code,
            award_type_description,
            recipient_id,
            awarding_agency_id,
            awarding_subagency_id,
            funding_agency_id,
            funding_subagency_id,
            award_description,
            period_of_performance_start,
            period_of_performance_end,
            first_load_batch_id,
            last_load_batch_id
        )
        VALUES (
            %s, %s, %s, %s, %s,
            NULL, NULL, NULL, NULL, NULL,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (generated_unique_award_id)
        DO UPDATE SET
            piid = COALESCE(EXCLUDED.piid, procurement.award.piid),
            parent_award_id = COALESCE(
                EXCLUDED.parent_award_id,
                procurement.award.parent_award_id
            ),
            award_type_code = COALESCE(
                EXCLUDED.award_type_code,
                procurement.award.award_type_code
            ),
            award_type_description = COALESCE(
                EXCLUDED.award_type_description,
                procurement.award.award_type_description
            ),
            award_description = COALESCE(
                EXCLUDED.award_description,
                procurement.award.award_description
            ),
            period_of_performance_start =
                CASE
                    WHEN procurement.award.period_of_performance_start IS NULL
                        THEN EXCLUDED.period_of_performance_start
                    WHEN EXCLUDED.period_of_performance_start IS NULL
                        THEN procurement.award.period_of_performance_start
                    ELSE LEAST(
                        procurement.award.period_of_performance_start,
                        EXCLUDED.period_of_performance_start
                    )
                END,
            period_of_performance_end =
                CASE
                    WHEN procurement.award.period_of_performance_end IS NULL
                        THEN EXCLUDED.period_of_performance_end
                    WHEN EXCLUDED.period_of_performance_end IS NULL
                        THEN procurement.award.period_of_performance_end
                    ELSE GREATEST(
                        procurement.award.period_of_performance_end,
                        EXCLUDED.period_of_performance_end
                    )
                END,
            first_load_batch_id =
                CASE
                    WHEN procurement.award.first_load_batch_id IS NULL
                        THEN EXCLUDED.first_load_batch_id
                    ELSE LEAST(
                        procurement.award.first_load_batch_id,
                        EXCLUDED.first_load_batch_id
                    )
                END,
            last_load_batch_id =
                CASE
                    WHEN procurement.award.last_load_batch_id IS NULL
                        THEN EXCLUDED.last_load_batch_id
                    ELSE GREATEST(
                        procurement.award.last_load_batch_id,
                        EXCLUDED.last_load_batch_id
                    )
                END,
            updated_at = CURRENT_TIMESTAMP
        RETURNING (xmax = 0) AS inserted;
    """

    inserted_count = 0
    updated_count = 0

    with conn.cursor() as cur:
        for generated_id in sorted(awards):
            award = awards[generated_id]
            cur.execute(
                sql,
                (
                    award["generated_unique_award_id"],
                    award["piid"],
                    award["parent_award_id"],
                    award["award_type_code"],
                    award["award_type_description"],
                    award["award_description"],
                    award["period_of_performance_start"],
                    award["period_of_performance_end"],
                    award["first_load_batch_id"],
                    award["last_load_batch_id"],
                ),
            )
            inserted = bool(cur.fetchone()[0])
            if inserted:
                inserted_count += 1
            else:
                updated_count += 1

    return inserted_count, updated_count


def validate_awards(
    conn,
    *,
    expected_award_ids: set[str],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT generated_unique_award_id
            FROM procurement.award
            WHERE generated_unique_award_id = ANY(%s);
            """,
            (list(expected_award_ids),),
        )
        normalized_ids = {row[0] for row in cur.fetchall()}

    missing = expected_award_ids - normalized_ids
    if missing:
        raise ValueError(
            "Missing normalized awards: " + ", ".join(sorted(missing))
        )


def main() -> None:
    args = parse_arguments()

    print("=" * 68)
    print("ETL-004A.3A — Normalize USAspending Awards")
    print("=" * 68)

    conn = get_connection()

    try:
        load_batch_id = get_target_load_batch_id(
            conn,
            args.load_batch_id,
        )
        print(f"Target raw load batch: {load_batch_id}")

        raw_rows = read_raw_award_rows(
            conn,
            load_batch_id=load_batch_id,
        )
        print(f"Raw observations read: {len(raw_rows):,}")

        awards = build_award_records(
            raw_rows,
            load_batch_id=load_batch_id,
        )
        print(f"Distinct awards derived: {len(awards):,}")

        inserted_count, updated_count = upsert_awards(
            conn,
            awards=awards,
        )

        validate_awards(
            conn,
            expected_award_ids=set(awards),
        )

        conn.commit()

        print(f"Awards inserted: {inserted_count:,}")
        print(f"Awards updated: {updated_count:,}")
        print("Award validation: PASS")
        print()
        print("ETL-004A.3A completed successfully.")

    except Exception as exc:
        conn.rollback()
        print()
        print("ETL-004A.3A failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()