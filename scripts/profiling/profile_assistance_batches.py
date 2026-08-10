"""Inventory normalized and raw Assistance load batches."""

from __future__ import annotations

from decimal import Decimal

from etl.common.db import get_connection


LINE = "=" * 120
SUBLINE = "-" * 120


def money(value: object) -> str:
    """Format a database numeric value as currency."""

    if value is None:
        value = Decimal("0")

    return f"${Decimal(value):,.2f}"


def main() -> None:
    conn = get_connection()

    print(LINE)
    print("ETL-006A — ASSISTANCE WAREHOUSE BATCH INVENTORY")
    print(LINE)
    print("Architecture Baseline ............... 2.1")
    print("Methodology Version ................. 1.0")
    print()

    try:
        with conn.cursor() as cur:
            #
            # ------------------------------------------------------------
            # 1. RAW BATCH INVENTORY
            # ------------------------------------------------------------
            #
            cur.execute(
                """
                SELECT
                    load_batch_id,
                    COUNT(*) AS raw_rows,

                    MIN(
                        NULLIF(
                            raw_record ->> 'action_date',
                            ''
                        )::date
                    ) AS earliest_action_date,

                    MAX(
                        NULLIF(
                            raw_record ->> 'action_date',
                            ''
                        )::date
                    ) AS latest_action_date

                FROM assistance.raw_award_transaction

                GROUP BY load_batch_id

                ORDER BY load_batch_id;
                """
            )

            raw_rows = cur.fetchall()

            raw_by_batch = {
                int(row[0]): {
                    "raw_rows": int(row[1]),
                    "earliest_action_date": row[2],
                    "latest_action_date": row[3],
                }
                for row in raw_rows
            }

            #
            # ------------------------------------------------------------
            # 2. NORMALIZED BATCH INVENTORY
            # ------------------------------------------------------------
            #
            cur.execute(
                """
                SELECT
                    load_batch_id,

                    COUNT(*) AS transaction_count,

                    COUNT(
                        DISTINCT assistance_award_id
                    ) AS award_count,

                    MIN(action_date) AS earliest_action_date,

                    MAX(action_date) AS latest_action_date,

                    MIN(action_date_fiscal_year) AS first_fy,

                    MAX(action_date_fiscal_year) AS last_fy

                FROM assistance.award_transaction

                GROUP BY load_batch_id

                ORDER BY load_batch_id;
                """
            )

            normalized_rows = cur.fetchall()

            normalized_by_batch = {
                int(row[0]): {
                    "transaction_count": int(row[1]),
                    "award_count": int(row[2]),
                    "earliest_action_date": row[3],
                    "latest_action_date": row[4],
                    "first_fy": row[5],
                    "last_fy": row[6],
                }
                for row in normalized_rows
            }

            all_batches = sorted(
                set(raw_by_batch)
                | set(normalized_by_batch)
            )

            #
            # ------------------------------------------------------------
            # 3. COVID / IIJA ACTIVITY
            # ------------------------------------------------------------
            #
            funding_by_batch: dict[int, dict[str, object]] = {}

            for load_batch_id in all_batches:
                cur.execute(
                    """
                    WITH classified_transaction AS (
                        SELECT DISTINCT
                            transaction.assistance_transaction_id,
                            transaction.federal_action_obligation,
                            defc.covid_flag,
                            defc.iija_flag

                        FROM assistance.award_transaction AS transaction

                        JOIN assistance.award_transaction_defc
                            AS relationship
                          ON relationship.assistance_transaction_id
                             = transaction.assistance_transaction_id

                        JOIN reference.extraordinary_funding_code
                            AS defc
                          ON defc.extraordinary_funding_code_id
                             = relationship.extraordinary_funding_code_id

                        WHERE transaction.load_batch_id = %s
                    ),

                    covid_transaction AS (
                        SELECT DISTINCT
                            assistance_transaction_id,
                            federal_action_obligation
                        FROM classified_transaction
                        WHERE covid_flag = TRUE
                    ),

                    iija_transaction AS (
                        SELECT DISTINCT
                            assistance_transaction_id,
                            federal_action_obligation
                        FROM classified_transaction
                        WHERE iija_flag = TRUE
                    )

                    SELECT
                        (
                            SELECT COUNT(*)
                            FROM covid_transaction
                        ) AS covid_transactions,

                        (
                            SELECT COALESCE(
                                SUM(federal_action_obligation),
                                0
                            )
                            FROM covid_transaction
                        ) AS covid_net_obligations,

                        (
                            SELECT COUNT(*)
                            FROM iija_transaction
                        ) AS iija_transactions,

                        (
                            SELECT COALESCE(
                                SUM(federal_action_obligation),
                                0
                            )
                            FROM iija_transaction
                        ) AS iija_net_obligations;
                    """,
                    (load_batch_id,),
                )

                row = cur.fetchone()

                funding_by_batch[load_batch_id] = {
                    "covid_transactions": int(row[0]),
                    "covid_net_obligations": Decimal(row[1]),
                    "iija_transactions": int(row[2]),
                    "iija_net_obligations": Decimal(row[3]),
                }

            #
            # ------------------------------------------------------------
            # 4. PRINT INVENTORY
            # ------------------------------------------------------------
            #
            print(LINE)
            print("1. LOAD BATCH INVENTORY")
            print(LINE)

            print(
                f"{'Batch':<8}"
                f"{'Raw Rows':>14}"
                f"{'Transactions':>16}"
                f"{'Awards':>12}"
                f"{'Earliest':>14}"
                f"{'Latest':>14}"
                f"{'First FY':>10}"
                f"{'Last FY':>10}"
            )

            print(SUBLINE)

            for load_batch_id in all_batches:
                raw = raw_by_batch.get(
                    load_batch_id,
                    {},
                )

                normalized = normalized_by_batch.get(
                    load_batch_id,
                    {},
                )

                print(
                    f"{load_batch_id:<8}"
                    f"{raw.get('raw_rows', 0):>14,}"
                    f"{normalized.get('transaction_count', 0):>16,}"
                    f"{normalized.get('award_count', 0):>12,}"
                    f"{str(normalized.get('earliest_action_date', '')):>14}"
                    f"{str(normalized.get('latest_action_date', '')):>14}"
                    f"{str(normalized.get('first_fy', '')):>10}"
                    f"{str(normalized.get('last_fy', '')):>10}"
                )

            print()

            #
            # ------------------------------------------------------------
            # 5. EXTRAORDINARY FUNDING INVENTORY
            # ------------------------------------------------------------
            #
            print(LINE)
            print("2. EXTRAORDINARY FUNDING INVENTORY")
            print(LINE)

            for load_batch_id in all_batches:
                funding = funding_by_batch[
                    load_batch_id
                ]

                print(f"Load Batch {load_batch_id}")
                print(SUBLINE)
                print(
                    "COVID transactions ................. "
                    f"{funding['covid_transactions']:,}"
                )
                print(
                    "COVID net obligations .............. "
                    f"{money(funding['covid_net_obligations'])}"
                )
                print(
                    "IIJA transactions .................. "
                    f"{funding['iija_transactions']:,}"
                )
                print(
                    "IIJA net obligations ............... "
                    f"{money(funding['iija_net_obligations'])}"
                )
                print()

            #
            # ------------------------------------------------------------
            # 6. RAW / NORMALIZED RECONCILIATION
            # ------------------------------------------------------------
            #
            print(LINE)
            print("3. RAW / NORMALIZED RECONCILIATION")
            print(LINE)

            overall_pass = True

            for load_batch_id in all_batches:
                raw_count = int(
                    raw_by_batch
                    .get(load_batch_id, {})
                    .get("raw_rows", 0)
                )

                normalized_count = int(
                    normalized_by_batch
                    .get(load_batch_id, {})
                    .get("transaction_count", 0)
                )

                passed = (
                    raw_count
                    == normalized_count
                )

                overall_pass = (
                    overall_pass
                    and passed
                )

                print(
                    f"Batch {load_batch_id:<4} "
                    f"raw={raw_count:>10,}  "
                    f"normalized={normalized_count:>10,}  "
                    f"{'PASS' if passed else 'FAIL'}"
                )

            print()

            #
            # ------------------------------------------------------------
            # 7. FISCAL-YEAR COVERAGE
            # ------------------------------------------------------------
            #
            fiscal_years: set[int] = set()

            cur.execute(
                """
                SELECT DISTINCT
                    action_date_fiscal_year
                FROM assistance.award_transaction
                WHERE action_date_fiscal_year IS NOT NULL
                ORDER BY action_date_fiscal_year;
                """
            )

            for (fiscal_year,) in cur.fetchall():
                fiscal_years.add(
                    int(fiscal_year)
                )

            print(LINE)
            print("4. FISCAL-YEAR COVERAGE")
            print(LINE)

            for fiscal_year in range(
                2020,
                2026,
            ):
                print(
                    f"FY{fiscal_year} "
                    f"{'PRESENT' if fiscal_year in fiscal_years else 'MISSING'}"
                )

            print()

            #
            # ------------------------------------------------------------
            # 8. ACQUISITION RECOMMENDATION
            # ------------------------------------------------------------
            #
            print(LINE)
            print("5. HISTORICAL ACQUISITION REQUIREMENTS")
            print(LINE)

            required_years = [
                fiscal_year
                for fiscal_year in range(
                    2020,
                    2025,
                )
                if fiscal_year
                not in fiscal_years
            ]

            if required_years:
                for fiscal_year in required_years:
                    print(
                        f"FY{fiscal_year} Assistance ........ REQUIRED"
                    )
            else:
                print(
                    "FY2020–FY2024 Assistance ........ COMPLETE"
                )

            print()
            print(
                "FY2025 Assistance ................ "
                "CHECK CURRENT USAspending AVAILABILITY"
            )

            print()

            print(LINE)
            print(
                "OVERALL INVENTORY VALIDATION ........ "
                f"{'PASS' if overall_pass else 'FAIL'}"
            )
            print(LINE)

    finally:
        conn.close()


if __name__ == "__main__":
    main()