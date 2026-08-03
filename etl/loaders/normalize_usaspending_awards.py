"""
ETL-004A.3A — Normalize USAspending Awards.

This loader reads immutable observations from
procurement.raw_award_transaction and creates or updates one normalized
procurement.award row per USAspending contract award key.

The USAspending source-field names and basic parsing rules are centralized
in etl.common.usaspending.
"""

import argparse
from typing import Any

from etl.common.db import get_connection
from etl.common.usaspending import (
    get_optional,
    get_required,
    parse_date,
)

from etl.validation.common.normalization_exception_recorder import (
    NormalizationExceptionRecorder,
)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Normalize USAspending awards from raw JSONB."
    )
    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Raw procurement load batch to normalize. "
            "Defaults to the latest completed batch containing raw rows."
        ),
    )
    return parser.parse_args()


def get_target_load_batch_id(
    conn,
    requested_batch_id: int | None,
) -> int:
    """Resolve and validate the raw load batch to normalize."""
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
    """Read raw observations in deterministic source-row order."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                source_row_number,
                raw_record
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


def parse_optional_date(
    raw_record: dict[str, Any],
    field_name: str,
    *,
    source_row_number: int,
):
    """Read and parse an optional USAspending date with row context."""
    raw_value = get_optional(raw_record, field_name)

    try:
        return parse_date(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid {field_name} at source row "
            f"{source_row_number}: {raw_value!r}."
        ) from exc


def build_award_records(
    raw_rows: list[tuple[int, dict[str, Any]]],
    *,
    load_batch_id: int,
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Derive normalized awards and auditable source-data anomalies.

    Later nonblank descriptive values replace earlier values.

    The normalized performance start is the earliest observed start date.
    The normalized performance end is the latest valid current-end date.

    A source row whose end date precedes its start date is preserved in the
    raw layer, excluded from normalized end-date aggregation, and returned
    as a structured warning.
    """
    awards: dict[str, dict[str, Any]] = {}
    anomaly_groups: dict[str, dict[str, Any]] = {}

    for source_row_number, raw_record in raw_rows:
        try:
            generated_id = get_required(raw_record, "AWARD_KEY")
        except ValueError as exc:
            raise ValueError(
                f"{exc} Source row: {source_row_number}."
            ) from exc

        start_date = parse_optional_date(
            raw_record,
            "POP_START",
            source_row_number=source_row_number,
        )
        end_date = parse_optional_date(
            raw_record,
            "POP_CURRENT_END",
            source_row_number=source_row_number,
        )

        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            anomaly = anomaly_groups.setdefault(
                generated_id,
                {
                    "load_batch_id": load_batch_id,
                    "entity_type": "award",
                    "entity_key": generated_id,
                    "anomaly_code": (
                        "PERFORMANCE_END_BEFORE_START"
                    ),
                    "severity": "WARNING",
                    "source_row_numbers": [],
                    "raw_values": {
                        "observations": [],
                    },
                    "normalized_action": {
                        "period_of_performance_end": None,
                        "rule": (
                            "Exclude reversed source end dates "
                            "from normalized end-date aggregation."
                        ),
                    },
                    "message": (
                        "USAspending reported one or more "
                        "performance end dates earlier than "
                        "their corresponding start dates. "
                        "The raw values were preserved and the "
                        "invalid end dates were excluded from "
                        "normalization."
                    ),
                },
            )

            anomaly["source_row_numbers"].append(
                source_row_number
            )

            anomaly["raw_values"]["observations"].append(
                {
                    "source_row_number": source_row_number,
                    "period_of_performance_start": (
                        start_date.isoformat()
                    ),
                    "period_of_performance_current_end": (
                        end_date.isoformat()
                    ),
                }
            )

            # Preserve the start date but do not normalize an end date
            # that precedes it.
            end_date = None

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

        latest_values = {
            "piid": get_optional(raw_record, "PIID"),
            "parent_award_id": get_optional(
                raw_record,
                "PARENT_PIID",
            ),
            "award_type_code": get_optional(
                raw_record,
                "AWARD_TYPE_CODE",
            ),
            "award_type_description": get_optional(
                raw_record,
                "AWARD_TYPE",
            ),
            "award_description": get_optional(
                raw_record,
                "AWARD_DESCRIPTION",
            ),
        }

        for field_name, value in latest_values.items():
            if value is not None:
                award[field_name] = value

        current_start = award["period_of_performance_start"]

        if start_date is not None and (
            current_start is None
            or start_date < current_start
        ):
            award["period_of_performance_start"] = start_date

        current_end = award["period_of_performance_end"]

        if end_date is not None and (
            current_end is None
            or end_date > current_end
        ):
            award["period_of_performance_end"] = end_date

    for award in awards.values():
        start_date = award["period_of_performance_start"]
        end_date = award["period_of_performance_end"]

        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            raise ValueError(
                "Invalid normalized performance-date range for award "
                f"{award['generated_unique_award_id']!r}: "
                f"{start_date} > {end_date}."
            )

    anomalies = [
        anomaly_groups[key]
        for key in sorted(anomaly_groups)
    ]

    return awards, anomalies


def upsert_awards(
    conn,
    *,
    awards: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    """Insert new awards and update awards already present."""
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
            piid = COALESCE(
                EXCLUDED.piid,
                procurement.award.piid
            ),
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

def record_normalization_exceptions(
    conn,
    *,
    anomalies: list[dict[str, Any]],
) -> int:
    """Persist all structured normalization anomalies."""
    recorder = NormalizationExceptionRecorder()

    for anomaly in anomalies:
        recorder.record(
            conn,
            load_batch_id=anomaly["load_batch_id"],
            entity_type=anomaly["entity_type"],
            entity_key=anomaly["entity_key"],
            anomaly_code=anomaly["anomaly_code"],
            severity=anomaly["severity"],
            source_row_numbers=(
                anomaly["source_row_numbers"]
            ),
            raw_values=anomaly["raw_values"],
            normalized_action=(
                anomaly["normalized_action"]
            ),
            message=anomaly["message"],
        )

    return len(anomalies)

def validate_awards(
    conn,
    *,
    expected_award_ids: set[str],
) -> None:
    """Confirm that all derived award identifiers exist after the upsert."""
    if not expected_award_ids:
        raise ValueError("No normalized awards were derived.")

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
            "Missing normalized awards: "
            + ", ".join(sorted(missing))
        )


def main() -> None:
    """Run ETL-004A.3A."""
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

        awards, anomalies = build_award_records(
           raw_rows,
            load_batch_id=load_batch_id,
        )

        print(f"Distinct awards derived: {len(awards):,}")
        print(
            f"Normalization anomalies detected: "
            f"{len(anomalies):,}"
        )

        inserted_count, updated_count = upsert_awards(
            conn,
            awards=awards,
        )

        exception_count = record_normalization_exceptions(
            conn,
            anomalies=anomalies,
        )

        validate_awards(
            conn,
            expected_award_ids=set(awards),
        )

        conn.commit()

        print(f"Awards inserted: {inserted_count:,}")
        print(f"Awards updated: {updated_count:,}")

        print(
           f"Normalization exceptions recorded: "
           f"{exception_count:,}"
        )

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