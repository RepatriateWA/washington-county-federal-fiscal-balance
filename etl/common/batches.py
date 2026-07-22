"""
Shared load-batch utilities for ETL workflows.
"""

from __future__ import annotations

from typing import Optional

from psycopg2.extensions import connection


VALID_LOAD_STATUSES = {
    "STARTED",
    "COMPLETED",
    "COMPLETED_WITH_REJECTIONS",
    "FAILED",
}


def create_load_batch(
    conn: connection,
    *,
    source_file: str,
    source_url: Optional[str] = None,
    file_sha256: Optional[str] = None,
    fiscal_year_start: Optional[int] = None,
    fiscal_year_end: Optional[int] = None,
    downloaded_at=None,
    source_record_count: Optional[int] = None,
    notes: Optional[str] = None,
) -> int:
    """
    Create a procurement.load_batch row and return its load_batch_id.
    """
    sql = """
        INSERT INTO procurement.load_batch (
            source_file,
            source_url,
            file_sha256,
            fiscal_year_start,
            fiscal_year_end,
            downloaded_at,
            source_record_count,
            load_status,
            notes
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, 'STARTED', %s
        )
        RETURNING load_batch_id;
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                source_file,
                source_url,
                file_sha256,
                fiscal_year_start,
                fiscal_year_end,
                downloaded_at,
                source_record_count,
                notes,
            ),
        )
        load_batch_id = cur.fetchone()[0]

    conn.commit()
    return load_batch_id


def complete_load_batch(
    conn: connection,
    *,
    load_batch_id: int,
    loaded_record_count: int,
    rejected_record_count: int = 0,
    notes: Optional[str] = None,
) -> None:
    """
    Mark a load batch as completed.
    """
    status = (
        "COMPLETED_WITH_REJECTIONS"
        if rejected_record_count > 0
        else "COMPLETED"
    )

    sql = """
        UPDATE procurement.load_batch
        SET
            loaded_record_count = %s,
            rejected_record_count = %s,
            load_completed_at = CURRENT_TIMESTAMP,
            load_status = %s,
            notes = COALESCE(%s, notes)
        WHERE load_batch_id = %s;
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                loaded_record_count,
                rejected_record_count,
                status,
                notes,
                load_batch_id,
            ),
        )

        if cur.rowcount != 1:
            conn.rollback()
            raise ValueError(
                f"Load batch {load_batch_id} was not found."
            )

    conn.commit()


def fail_load_batch(
    conn: connection,
    *,
    load_batch_id: int,
    notes: Optional[str] = None,
) -> None:
    """
    Mark a load batch as failed.
    """
    sql = """
        UPDATE procurement.load_batch
        SET
            load_completed_at = CURRENT_TIMESTAMP,
            load_status = 'FAILED',
            notes = COALESCE(%s, notes)
        WHERE load_batch_id = %s;
    """

    with conn.cursor() as cur:
        cur.execute(sql, (notes, load_batch_id))

        if cur.rowcount != 1:
            conn.rollback()
            raise ValueError(
                f"Load batch {load_batch_id} was not found."
            )

    conn.commit()