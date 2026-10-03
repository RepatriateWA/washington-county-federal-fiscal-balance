"""
ETL-174B-5Y-2D-1
USAspending AL 14.871 monthly obligation profile for Washington.

PURPOSE
-------
Construct the transaction-action-month obligation series needed for
subsequent reconciliation with HUD VMS HAP expenditures.

READ ONLY.

NO:
    HUD VMS reconciliation,
    accounting classification,
    county allocation,
    ledger inclusion decision,
    database writes.

IMPORTANT SEMANTICS
-------------------
* federal_action_obligation is the transaction action amount.
* action_date defines transaction timing.
* action_date_fiscal_year supplies the USAspending fiscal-year control.
* DEFC relationships are preserved as diagnostics.
* covid_overall_award_obligation is NOT summed as transaction COVID flow,
  because it is an overall-award amount rather than the transaction action.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from etl.db import get_connection


CHECKPOINT = "ETL-174B-5Y-2D-1"
CFDA_NUMBER = "14.871"
FISCAL_YEARS = (2020, 2021, 2022, 2023, 2024)

REPO_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "hud"
    / "vms"
    / "validation"
    / "usaspending_14871_monthly_obligations"
)


def money(value: Decimal | None) -> str:
    if value is None:
        return "NULL"
    return f"${value:,.2f}"


def decimal_or_zero(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def fetch_program_identity(cur):
    cur.execute(
        """
        SELECT
            assistance_listing_id,
            cfda_number,
            cfda_title
        FROM assistance.assistance_listing
        WHERE cfda_number = %s
        ORDER BY assistance_listing_id
        """,
        (CFDA_NUMBER,),
    )

    return cur.fetchall()


def fetch_transaction_controls(cur):
    cur.execute(
        """
        SELECT
            COUNT(*) AS transaction_count,
            COUNT(DISTINCT t.assistance_award_id) AS award_count,
            COUNT(DISTINCT t.recipient_id) AS recipient_count,
            MIN(t.action_date) AS first_action_date,
            MAX(t.action_date) AS last_action_date,
            SUM(t.federal_action_obligation) AS net_obligation,
            SUM(
                CASE
                    WHEN t.federal_action_obligation > 0
                    THEN t.federal_action_obligation
                    ELSE 0
                END
            ) AS positive_obligation,
            SUM(
                CASE
                    WHEN t.federal_action_obligation < 0
                    THEN t.federal_action_obligation
                    ELSE 0
                END
            ) AS negative_obligation,
            COUNT(*) FILTER (
                WHERE t.federal_action_obligation IS NULL
            ) AS null_obligation_count,
            COUNT(*) FILTER (
                WHERE t.action_date IS NULL
            ) AS null_action_date_count,
            COUNT(*) FILTER (
                WHERE t.action_date_fiscal_year IS NULL
            ) AS null_fiscal_year_count
        FROM assistance.award_transaction AS t
        JOIN assistance.assistance_listing AS al
          ON al.assistance_listing_id = t.assistance_listing_id
        WHERE al.cfda_number = %s
          AND t.action_date_fiscal_year = ANY(%s)
        """,
        (CFDA_NUMBER, list(FISCAL_YEARS)),
    )

    return cur.fetchone()


def fetch_annual(cur):
    cur.execute(
        """
        SELECT
            t.action_date_fiscal_year AS fiscal_year,
            COUNT(*) AS transaction_count,
            COUNT(DISTINCT t.assistance_award_id) AS award_count,
            COUNT(DISTINCT t.recipient_id) AS recipient_count,
            SUM(
                CASE
                    WHEN t.federal_action_obligation > 0
                    THEN t.federal_action_obligation
                    ELSE 0
                END
            ) AS positive_obligation,
            SUM(
                CASE
                    WHEN t.federal_action_obligation < 0
                    THEN t.federal_action_obligation
                    ELSE 0
                END
            ) AS negative_obligation,
            SUM(t.federal_action_obligation) AS net_obligation
        FROM assistance.award_transaction AS t
        JOIN assistance.assistance_listing AS al
          ON al.assistance_listing_id = t.assistance_listing_id
        WHERE al.cfda_number = %s
          AND t.action_date_fiscal_year = ANY(%s)
        GROUP BY t.action_date_fiscal_year
        ORDER BY t.action_date_fiscal_year
        """,
        (CFDA_NUMBER, list(FISCAL_YEARS)),
    )

    return cur.fetchall()


def fetch_monthly(cur):
    cur.execute(
        """
        SELECT
            DATE_TRUNC('month', t.action_date)::date AS action_month,
            t.action_date_fiscal_year AS fiscal_year,
            COUNT(*) AS transaction_count,
            COUNT(DISTINCT t.assistance_award_id) AS award_count,
            COUNT(DISTINCT t.recipient_id) AS recipient_count,
            SUM(
                CASE
                    WHEN t.federal_action_obligation > 0
                    THEN t.federal_action_obligation
                    ELSE 0
                END
            ) AS positive_obligation,
            SUM(
                CASE
                    WHEN t.federal_action_obligation < 0
                    THEN t.federal_action_obligation
                    ELSE 0
                END
            ) AS negative_obligation,
            SUM(t.federal_action_obligation) AS net_obligation
        FROM assistance.award_transaction AS t
        JOIN assistance.assistance_listing AS al
          ON al.assistance_listing_id = t.assistance_listing_id
        WHERE al.cfda_number = %s
          AND t.action_date_fiscal_year = ANY(%s)
        GROUP BY
            DATE_TRUNC('month', t.action_date)::date,
            t.action_date_fiscal_year
        ORDER BY
            DATE_TRUNC('month', t.action_date)::date,
            t.action_date_fiscal_year
        """,
        (CFDA_NUMBER, list(FISCAL_YEARS)),
    )

    return cur.fetchall()


def fetch_defc_profile(cur):
    # DISTINCT transaction-DEFC pairs protect this diagnostic from
    # accidental duplicate bridge observations.
    cur.execute(
        """
        WITH focal AS (
            SELECT
                t.assistance_transaction_id,
                t.action_date,
                t.action_date_fiscal_year,
                t.federal_action_obligation
            FROM assistance.award_transaction AS t
            JOIN assistance.assistance_listing AS al
              ON al.assistance_listing_id = t.assistance_listing_id
            WHERE al.cfda_number = %s
              AND t.action_date_fiscal_year = ANY(%s)
        ),
        pairs AS (
            SELECT DISTINCT
                d.assistance_transaction_id,
                d.extraordinary_funding_code_id,
                d.raw_defc_value,
                d.observed_description
            FROM assistance.award_transaction_defc AS d
            JOIN focal AS f
              ON f.assistance_transaction_id =
                 d.assistance_transaction_id
        )
        SELECT
            p.extraordinary_funding_code_id,
            p.raw_defc_value,
            p.observed_description,
            COUNT(DISTINCT p.assistance_transaction_id)
                AS transaction_count
        FROM pairs AS p
        GROUP BY
            p.extraordinary_funding_code_id,
            p.raw_defc_value,
            p.observed_description
        ORDER BY
            p.raw_defc_value NULLS LAST,
            p.observed_description NULLS LAST,
            p.extraordinary_funding_code_id
        """,
        (CFDA_NUMBER, list(FISCAL_YEARS)),
    )

    return cur.fetchall()


def fetch_defc_transaction_control(cur):
    cur.execute(
        """
        WITH focal AS (
            SELECT
                t.assistance_transaction_id,
                t.federal_action_obligation
            FROM assistance.award_transaction AS t
            JOIN assistance.assistance_listing AS al
              ON al.assistance_listing_id = t.assistance_listing_id
            WHERE al.cfda_number = %s
              AND t.action_date_fiscal_year = ANY(%s)
        ),
        defc_tx AS (
            SELECT DISTINCT
                d.assistance_transaction_id
            FROM assistance.award_transaction_defc AS d
            JOIN focal AS f
              ON f.assistance_transaction_id =
                 d.assistance_transaction_id
        )
        SELECT
            COUNT(*) AS transaction_count_with_defc,
            SUM(f.federal_action_obligation)
                AS net_obligation_on_transactions_with_defc
        FROM focal AS f
        JOIN defc_tx AS d
          ON d.assistance_transaction_id =
             f.assistance_transaction_id
        """,
        (CFDA_NUMBER, list(FISCAL_YEARS)),
    )

    return cur.fetchone()


def validate_monthly_vs_annual(monthly, annual):
    monthly_by_fy = defaultdict(
        lambda: {
            "transaction_count": 0,
            "positive": Decimal("0"),
            "negative": Decimal("0"),
            "net": Decimal("0"),
        }
    )

    for row in monthly:
        (
            action_month,
            fiscal_year,
            transaction_count,
            award_count,
            recipient_count,
            positive,
            negative,
            net,
        ) = row

        bucket = monthly_by_fy[fiscal_year]
        bucket["transaction_count"] += transaction_count
        bucket["positive"] += decimal_or_zero(positive)
        bucket["negative"] += decimal_or_zero(negative)
        bucket["net"] += decimal_or_zero(net)

    results = []

    for row in annual:
        (
            fiscal_year,
            transaction_count,
            award_count,
            recipient_count,
            positive,
            negative,
            net,
        ) = row

        bucket = monthly_by_fy[fiscal_year]

        results.append(
            {
                "fiscal_year": fiscal_year,
                "transaction_count_match":
                    bucket["transaction_count"] == transaction_count,
                "positive_match":
                    bucket["positive"] == decimal_or_zero(positive),
                "negative_match":
                    bucket["negative"] == decimal_or_zero(negative),
                "net_match":
                    bucket["net"] == decimal_or_zero(net),
                "monthly_net":
                    bucket["net"],
                "annual_net":
                    decimal_or_zero(net),
            }
        )

    return results


def write_monthly_csv(path, rows):
    fieldnames = [
        "action_month",
        "fiscal_year",
        "transaction_count",
        "award_count",
        "recipient_count",
        "positive_obligation",
        "negative_obligation",
        "net_obligation",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.writer(handle)
        writer.writerow(fieldnames)

        for row in rows:
            writer.writerow(row)


def render_report(
    identity,
    controls,
    annual,
    monthly,
    monthly_validation,
    defc_profile,
    defc_control,
):
    lines = []

    def emit(text=""):
        lines.append(text)

    emit("=" * 100)
    emit("USASPENDING AL 14.871 MONTHLY OBLIGATION PROFILE")
    emit(CHECKPOINT)
    emit("=" * 100)
    emit()
    emit("READ ONLY. NO HUD VMS reconciliation or accounting decision.")
    emit()

    emit("PROGRAM IDENTITY")
    emit("-" * 100)

    for row in identity:
        emit(
            f"assistance_listing_id={row[0]} | "
            f"CFDA={row[1]} | {row[2]}"
        )

    emit()
    emit("FIVE-YEAR TRANSACTION CONTROL")
    emit("-" * 100)

    (
        transaction_count,
        award_count,
        recipient_count,
        first_action_date,
        last_action_date,
        net_obligation,
        positive_obligation,
        negative_obligation,
        null_obligation_count,
        null_action_date_count,
        null_fiscal_year_count,
    ) = controls

    emit(f"Transactions             : {transaction_count:,}")
    emit(f"Awards                   : {award_count:,}")
    emit(f"Recipients               : {recipient_count:,}")
    emit(f"First action date         : {first_action_date}")
    emit(f"Last action date          : {last_action_date}")
    emit(f"Positive obligations      : {money(positive_obligation)}")
    emit(f"Negative obligations      : {money(negative_obligation)}")
    emit(f"Net obligations           : {money(net_obligation)}")
    emit(f"NULL obligation rows      : {null_obligation_count:,}")
    emit(f"NULL action dates         : {null_action_date_count:,}")
    emit(f"NULL fiscal years         : {null_fiscal_year_count:,}")

    emit()
    emit("ANNUAL CONTROLS")
    emit("-" * 100)

    for row in annual:
        (
            fiscal_year,
            tx_count,
            aw_count,
            rec_count,
            positive,
            negative,
            net,
        ) = row

        emit(
            f"FY{fiscal_year}: "
            f"tx={tx_count:,} "
            f"awards={aw_count:,} "
            f"recipients={rec_count:,} "
            f"positive={money(positive)} "
            f"negative={money(negative)} "
            f"net={money(net)}"
        )

    emit()
    emit("MONTHLY -> ANNUAL RECONCILIATION")
    emit("-" * 100)

    for item in monthly_validation:
        emit(
            f"FY{item['fiscal_year']}: "
            f"transactions={'PASS' if item['transaction_count_match'] else 'FAIL'} | "
            f"positive={'PASS' if item['positive_match'] else 'FAIL'} | "
            f"negative={'PASS' if item['negative_match'] else 'FAIL'} | "
            f"net={'PASS' if item['net_match'] else 'FAIL'} | "
            f"monthly={money(item['monthly_net'])} | "
            f"annual={money(item['annual_net'])}"
        )

    emit()
    emit("MONTHLY SERIES")
    emit("-" * 100)

    for row in monthly:
        (
            action_month,
            fiscal_year,
            tx_count,
            aw_count,
            rec_count,
            positive,
            negative,
            net,
        ) = row

        emit(
            f"{action_month} | "
            f"FY{fiscal_year} | "
            f"tx={tx_count:,} | "
            f"awards={aw_count:,} | "
            f"recipients={rec_count:,} | "
            f"positive={money(positive)} | "
            f"negative={money(negative)} | "
            f"net={money(net)}"
        )

    emit()
    emit("DEFC DIAGNOSTIC")
    emit("-" * 100)
    emit(
        "DEFC presence is diagnostic only. No DEFC code is classified "
        "as COVID or extraordinary by this profiler."
    )
    emit()

    emit(
        f"Transactions carrying >=1 DEFC : "
        f"{defc_control[0]:,}"
    )
    emit(
        f"Net obligation on DEFC tx      : "
        f"{money(defc_control[1])}"
    )
    emit()

    for row in defc_profile:
        (
            code_id,
            raw_value,
            description,
            tx_count,
        ) = row

        emit(
            f"id={code_id} | "
            f"raw={raw_value!r} | "
            f"transactions={tx_count:,} | "
            f"description={description!r}"
        )

    emit()
    emit("METHODOLOGICAL STOP")
    emit("-" * 100)
    emit("No HUD VMS comparison was performed.")
    emit("No obligation/expenditure equivalence was assumed.")
    emit("No DEFC-to-COVID classification was imposed.")
    emit("No county allocation was performed.")
    emit("No database writes occurred.")
    emit("No ledger decision was made.")

    return "\n".join(lines) + "\n"


def main():
    print("=" * 88)
    print("USASPENDING AL 14.871 MONTHLY OBLIGATION PROFILE")
    print(CHECKPOINT)
    print("=" * 88)
    print()
    print("Mode : READ ONLY")
    print("CFDA : 14.871")
    print("Years: FY2020-FY2024")
    print()

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    with get_connection() as conn:
        with conn.cursor() as cur:

            identity = fetch_program_identity(cur)

            if len(identity) != 1:
                print(
                    "HOLD: expected exactly one "
                    "assistance_listing row for 14.871; "
                    f"found {len(identity)}."
                )
                return 2

            controls = fetch_transaction_controls(cur)
            annual = fetch_annual(cur)
            monthly = fetch_monthly(cur)
            defc_profile = fetch_defc_profile(cur)
            defc_control = fetch_defc_transaction_control(cur)

    validation = validate_monthly_vs_annual(
        monthly,
        annual,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    report_path = (
        OUTPUT_ROOT
        / f"profile_14871_monthly_{timestamp}.txt"
    )

    csv_path = (
        OUTPUT_ROOT
        / f"profile_14871_monthly_{timestamp}.csv"
    )

    json_path = (
        OUTPUT_ROOT
        / f"profile_14871_monthly_{timestamp}.json"
    )

    write_monthly_csv(
        csv_path,
        monthly,
    )

    report_path.write_text(
        render_report(
            identity,
            controls,
            annual,
            monthly,
            validation,
            defc_profile,
            defc_control,
        ),
        encoding="utf-8",
    )

    json_path.write_text(
        json.dumps(
            {
                "checkpoint": CHECKPOINT,
                "generated_utc":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                "cfda_number": CFDA_NUMBER,
                "fiscal_years": FISCAL_YEARS,
                "program_identity": [
                    {
                        "assistance_listing_id": row[0],
                        "cfda_number": row[1],
                        "cfda_title": row[2],
                    }
                    for row in identity
                ],
                "five_year_control": {
                    "transaction_count": controls[0],
                    "award_count": controls[1],
                    "recipient_count": controls[2],
                    "first_action_date":
                        str(controls[3]),
                    "last_action_date":
                        str(controls[4]),
                    "net_obligation":
                        str(controls[5]),
                    "positive_obligation":
                        str(controls[6]),
                    "negative_obligation":
                        str(controls[7]),
                    "null_obligation_count":
                        controls[8],
                    "null_action_date_count":
                        controls[9],
                    "null_fiscal_year_count":
                        controls[10],
                },
                "monthly_annual_validation":
                    [
                        {
                            **item,
                            "monthly_net":
                                str(item["monthly_net"]),
                            "annual_net":
                                str(item["annual_net"]),
                        }
                        for item in validation
                    ],
                "defc_profile": [
                    {
                        "extraordinary_funding_code_id":
                            row[0],
                        "raw_defc_value":
                            row[1],
                        "observed_description":
                            row[2],
                        "transaction_count":
                            row[3],
                    }
                    for row in defc_profile
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    all_reconciled = all(
        item["transaction_count_match"]
        and item["positive_match"]
        and item["negative_match"]
        and item["net_match"]
        for item in validation
    )

    print("Program identity rows :", len(identity))
    print("Transactions          :", f"{controls[0]:,}")
    print("Awards                :", f"{controls[1]:,}")
    print("Recipients            :", f"{controls[2]:,}")
    print("Net obligations       :", money(controls[5]))
    print("Monthly rows          :", f"{len(monthly):,}")
    print()

    for row in annual:
        print(
            f"FY{row[0]} net             : "
            f"{money(row[6])}"
        )

    print()
    print(
        "Monthly -> annual     :",
        "PASS" if all_reconciled else "FAIL",
    )
    print()
    print(
        "Report :",
        report_path.relative_to(REPO_ROOT),
    )
    print(
        "CSV    :",
        csv_path.relative_to(REPO_ROOT),
    )
    print(
        "JSON   :",
        json_path.relative_to(REPO_ROOT),
    )
    print()

    if not all_reconciled:
        print(
            "RESULT: HOLD — MONTHLY SERIES DOES NOT "
            "RECONCILE TO ANNUAL CONTROLS"
        )
        return 2

    print(
        "RESULT: PASS — AL 14.871 MONTHLY OBLIGATION "
        "SERIES RECONCILES TO ANNUAL CONTROLS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())