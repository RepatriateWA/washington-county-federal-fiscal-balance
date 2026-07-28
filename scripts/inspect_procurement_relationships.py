"""
Inspect procurement table columns and normalized entity relationships.
"""

from __future__ import annotations

from etl.common.db import get_connection


TABLES = (
    "award",
    "award_transaction",
    "recipient",
    "agency",
    "place_of_performance",
)


def print_table_columns(cur, table_name: str) -> None:
    """
    Print the columns and data types for one procurement table.
    """
    print()
    print("=" * 76)
    print(f"procurement.{table_name}")
    print("=" * 76)

    cur.execute(
        """
        SELECT
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema = 'procurement'
          AND table_name = %s
        ORDER BY ordinal_position;
        """,
        (table_name,),
    )

    for column_name, data_type in cur.fetchall():
        print(f"{column_name:<40} {data_type}")


def print_batch_award_relationships(
    cur,
    load_batch_id: int,
) -> None:
    """
    Print award, recipient, and agency relationships for one load batch.
    """
    print()
    print("=" * 76)
    print(f"BATCH {load_batch_id} AWARD RELATIONSHIPS")
    print("=" * 76)

    cur.execute(
        """
        SELECT DISTINCT
            aw.award_id,
            aw.piid,
            aw.recipient_id,
            r.recipient_name,
            aw.awarding_agency_id,
            awarding.agency_name AS awarding_agency_name,
            aw.awarding_subagency_id,
            awarding_sub.agency_name AS awarding_subagency_name,
            aw.funding_agency_id,
            funding.agency_name AS funding_agency_name,
            aw.funding_subagency_id,
            funding_sub.agency_name AS funding_subagency_name
        FROM procurement.award_transaction AS at
        JOIN procurement.award AS aw
          ON aw.award_id = at.award_id
        LEFT JOIN procurement.recipient AS r
          ON r.recipient_id = aw.recipient_id
        LEFT JOIN procurement.agency AS awarding
          ON awarding.agency_id = aw.awarding_agency_id
        LEFT JOIN procurement.agency AS awarding_sub
          ON awarding_sub.agency_id = aw.awarding_subagency_id
        LEFT JOIN procurement.agency AS funding
          ON funding.agency_id = aw.funding_agency_id
        LEFT JOIN procurement.agency AS funding_sub
          ON funding_sub.agency_id = aw.funding_subagency_id
        WHERE at.load_batch_id = %s
        ORDER BY aw.award_id;
        """,
        (load_batch_id,),
    )

    columns = [description[0] for description in cur.description]
    rows = cur.fetchall()

    if not rows:
        print(f"No awards were found for load batch {load_batch_id}.")
        return

    for row in rows:
        for column_name, value in zip(columns, row):
            print(f"{column_name:<32} {value}")

        print("-" * 76)


def print_normalized_entity_totals(cur) -> None:
    """
    Print database-wide counts for normalized procurement entities.
    """
    print()
    print("=" * 76)
    print("NORMALIZED ENTITY TOTALS")
    print("=" * 76)

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.recipient;
        """
    )
    recipient_count = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.agency;
        """
    )
    agency_count = cur.fetchone()[0]

    print(f"{'Recipients':<32} {recipient_count}")
    print(f"{'Agencies':<32} {agency_count}")


def main() -> None:
    """
    Run the procurement relationship inspection report.
    """
    load_batch_id = 4
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            for table_name in TABLES:
                print_table_columns(
                    cur,
                    table_name,
                )

            print_batch_award_relationships(
                cur,
                load_batch_id,
            )

            print_normalized_entity_totals(cur)

    finally:
        conn.close()


if __name__ == "__main__":
    main()