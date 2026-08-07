"""Profile COVID-classified Assistance activity in Washington State."""

from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal

from etl.common.db import get_connection


LINE = "=" * 104
SUBLINE = "-" * 104


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Profile COVID-classified federal Assistance activity "
            "for one normalized load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Normalized Assistance load batch ID.",
    )

    return parser.parse_args()


def money(
    value: Decimal | int | float | None,
) -> str:
    """Format a dollar value consistently."""

    if value is None:
        value = Decimal("0")

    return f"${Decimal(value):,.2f}"


def print_header(
    *,
    load_batch_id: int,
) -> None:
    print(LINE)
    print(
        "EP-002A — WASHINGTON COVID FEDERAL ASSISTANCE ACTIVITY PROFILE"
    )
    print(LINE)
    print(f"Load Batch ......................... {load_batch_id}")
    print("Warehouse Baseline ................. 2.1")
    print(
        "COVID Classification .............. "
        "reference.extraordinary_funding_code.covid_flag = TRUE"
    )
    print()

    print(LINE)
    print("RESEARCH QUESTION")
    print(LINE)
    print(
        "How much COVID-classified federal Assistance activity has been"
    )
    print(
        "observed in Washington State, over what time period, and how is"
    )
    print(
        "that activity distributed by fiscal year, agency, recipient,"
    )
    print(
        "county, and DEFC classification?"
    )
    print()


def create_covid_transaction_cte() -> str:
    """
    Return the canonical distinct COVID-linked transaction CTE.

    A transaction is counted once even if linked to multiple COVID DEFC codes.
    """

    return """
        WITH covid_transaction AS (
            SELECT DISTINCT
                transaction.assistance_transaction_id,
                transaction.assistance_award_id,
                transaction.load_batch_id,
                transaction.source_row_number,
                transaction.assistance_transaction_unique_key,
                transaction.action_date,
                transaction.action_date_fiscal_year,
                transaction.federal_action_obligation,
                transaction.recipient_id,
                transaction.place_of_performance_id,
                transaction.awarding_agency_id

            FROM assistance.award_transaction AS transaction

            JOIN assistance.award_transaction_defc AS relationship
              ON relationship.assistance_transaction_id
                 = transaction.assistance_transaction_id

            JOIN reference.extraordinary_funding_code AS defc
              ON defc.extraordinary_funding_code_id
                 = relationship.extraordinary_funding_code_id

            WHERE transaction.load_batch_id = %s
              AND defc.covid_flag = TRUE
        )
    """


def activity_window(
    cur,
    *,
    load_batch_id: int,
) -> dict[str, object]:
    """Print and return COVID activity-window metrics."""

    sql = create_covid_transaction_cte() + """
        SELECT
            MIN(action_date),
            MAX(action_date),
            MIN(action_date_fiscal_year),
            MAX(action_date_fiscal_year),
            COUNT(DISTINCT assistance_award_id),
            COUNT(*)
        FROM covid_transaction;
    """

    cur.execute(
        sql,
        (load_batch_id,),
    )

    (
        earliest_date,
        latest_date,
        first_fy,
        last_fy,
        award_count,
        transaction_count,
    ) = cur.fetchone()

    print(LINE)
    print("1. COVID ACTIVITY WINDOW")
    print(LINE)
    print(
        "Earliest Action Date ............... "
        f"{earliest_date}"
    )
    print(
        "Latest Action Date ................. "
        f"{latest_date}"
    )
    print(
        "First Fiscal Year .................. "
        f"{first_fy}"
    )
    print(
        "Last Fiscal Year ................... "
        f"{last_fy}"
    )
    print(
        "Distinct Awards .................... "
        f"{award_count:,}"
    )
    print(
        "Distinct Transactions .............. "
        f"{transaction_count:,}"
    )
    print()

    return {
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "first_fy": first_fy,
        "last_fy": last_fy,
        "award_count": int(award_count),
        "transaction_count": int(transaction_count),
    }


def transaction_inventory(
    cur,
    *,
    load_batch_id: int,
) -> dict[str, int]:
    """Print COVID transaction inventory."""

    sql = create_covid_transaction_cte() + """
        SELECT
            COUNT(*) FILTER (
                WHERE federal_action_obligation IS NOT NULL
            ),
            COUNT(*) FILTER (
                WHERE federal_action_obligation = 0
            ),
            COUNT(*) FILTER (
                WHERE federal_action_obligation IS NULL
            ),
            COUNT(*) FILTER (
                WHERE federal_action_obligation > 0
            ),
            COUNT(*) FILTER (
                WHERE federal_action_obligation < 0
            )
        FROM covid_transaction;
    """

    cur.execute(
        sql,
        (load_batch_id,),
    )

    (
        populated_count,
        zero_count,
        null_count,
        positive_count,
        negative_count,
    ) = [
        int(value)
        for value in cur.fetchone()
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                relationship.assistance_transaction_id
            FROM assistance.award_transaction_defc AS relationship
            JOIN assistance.award_transaction AS transaction
              ON transaction.assistance_transaction_id
                 = relationship.assistance_transaction_id
            JOIN reference.extraordinary_funding_code AS defc
              ON defc.extraordinary_funding_code_id
                 = relationship.extraordinary_funding_code_id
            WHERE transaction.load_batch_id = %s
              AND defc.covid_flag = TRUE
            GROUP BY
                relationship.assistance_transaction_id
            HAVING COUNT(*) > 1
        ) AS multiple_codes;
        """,
        (load_batch_id,),
    )

    multi_code_count = int(
        cur.fetchone()[0]
    )

    print(LINE)
    print("2. COVID TRANSACTION INVENTORY")
    print(LINE)
    print(
        "Transactions with obligation ....... "
        f"{populated_count:,}"
    )
    print(
        "Positive-obligation transactions ... "
        f"{positive_count:,}"
    )
    print(
        "Negative-obligation transactions ... "
        f"{negative_count:,}"
    )
    print(
        "Zero-dollar transactions ........... "
        f"{zero_count:,}"
    )
    print(
        "Null-obligation transactions ....... "
        f"{null_count:,}"
    )
    print(
        "Multiple COVID-DEFC transactions ... "
        f"{multi_code_count:,}"
    )
    print()

    return {
        "populated_count": populated_count,
        "zero_count": zero_count,
        "null_count": null_count,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "multi_code_count": multi_code_count,
    }


def statewide_obligation_summary(
    cur,
    *,
    load_batch_id: int,
) -> dict[str, Decimal]:
    """Print statewide additive obligation totals."""

    sql = create_covid_transaction_cte() + """
        SELECT
            COALESCE(
                SUM(federal_action_obligation)
                FILTER (
                    WHERE federal_action_obligation > 0
                ),
                0
            ),
            COALESCE(
                SUM(federal_action_obligation)
                FILTER (
                    WHERE federal_action_obligation < 0
                ),
                0
            ),
            COALESCE(
                SUM(federal_action_obligation),
                0
            )
        FROM covid_transaction;
    """

    cur.execute(
        sql,
        (load_batch_id,),
    )

    positive, negative, net = [
        Decimal(value)
        for value in cur.fetchone()
    ]

    print(LINE)
    print("3. STATEWIDE COVID OBLIGATION LEDGER")
    print(LINE)
    print(
        "Positive Obligations ............... "
        f"{money(positive)}"
    )
    print(
        "Negative Obligations ............... "
        f"{money(negative)}"
    )
    print(
        "Net Obligations .................... "
        f"{money(net)}"
    )
    print()
    print("RECONCILIATION")
    print(SUBLINE)
    print(
        "Positive + Negative ................ "
        f"{money(positive + negative)}"
    )
    print(
        "Reported Net ....................... "
        f"{money(net)}"
    )
    print(
        "Validation ......................... "
        f"{'PASS' if positive + negative == net else 'FAIL'}"
    )
    print()

    return {
        "positive": positive,
        "negative": negative,
        "net": net,
    }


def fiscal_year_ledger(
    cur,
    *,
    load_batch_id: int,
) -> list[tuple[int, int, Decimal, Decimal, Decimal]]:
    """Print additive COVID obligations by fiscal year."""

    sql = create_covid_transaction_cte() + """
        SELECT
            action_date_fiscal_year,
            COUNT(*) AS transaction_count,

            COALESCE(
                SUM(federal_action_obligation)
                FILTER (
                    WHERE federal_action_obligation > 0
                ),
                0
            ) AS positive_obligations,

            COALESCE(
                SUM(federal_action_obligation)
                FILTER (
                    WHERE federal_action_obligation < 0
                ),
                0
            ) AS negative_obligations,

            COALESCE(
                SUM(federal_action_obligation),
                0
            ) AS net_obligations

        FROM covid_transaction

        GROUP BY action_date_fiscal_year

        ORDER BY action_date_fiscal_year;
    """

    cur.execute(
        sql,
        (load_batch_id,),
    )

    rows = [
        (
            int(row[0]),
            int(row[1]),
            Decimal(row[2]),
            Decimal(row[3]),
            Decimal(row[4]),
        )
        for row in cur.fetchall()
    ]

    print(LINE)
    print("4. FISCAL YEAR LEDGER")
    print(LINE)
    print(
        f"{'FY':<8}"
        f"{'Transactions':>14}"
        f"{'Positive':>22}"
        f"{'Negative':>22}"
        f"{'Net':>22}"
    )
    print(SUBLINE)

    for fy, count, positive, negative, net in rows:
        print(
            f"{fy:<8}"
            f"{count:>14,}"
            f"{money(positive):>22}"
            f"{money(negative):>22}"
            f"{money(net):>22}"
        )

    print()

    return rows


def defc_ledger(
    cur,
    *,
    load_batch_id: int,
) -> None:
    """Print intentionally non-additive COVID DEFC ledger."""

    cur.execute(
        """
        SELECT
            defc.defc_code,
            defc.official_description,
            defc.public_law_reference,
            defc.funding_family,

            COUNT(
                DISTINCT transaction.assistance_transaction_id
            ) AS transaction_count,

            COALESCE(
                SUM(transaction.federal_action_obligation),
                0
            ) AS net_obligations

        FROM assistance.award_transaction_defc AS relationship

        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = relationship.assistance_transaction_id

        JOIN reference.extraordinary_funding_code AS defc
          ON defc.extraordinary_funding_code_id
             = relationship.extraordinary_funding_code_id

        WHERE transaction.load_batch_id = %s
          AND defc.covid_flag = TRUE

        GROUP BY
            defc.defc_code,
            defc.official_description,
            defc.public_law_reference,
            defc.funding_family

        ORDER BY defc.defc_code;
        """,
        (load_batch_id,),
    )

    rows = cur.fetchall()

    print(LINE)
    print("5. COVID DEFC LEDGER — NON-ADDITIVE")
    print(LINE)

    for row in rows:
        (
            code,
            description,
            public_law,
            family,
            transaction_count,
            net_obligations,
        ) = row

        print(f"Code ............................... {code}")
        print(f"Funding Family ..................... {family}")
        print(f"Public Law ......................... {public_law or '(none)'}")
        print(f"Description ........................ {description}")
        print(
            "Transactions ....................... "
            f"{int(transaction_count):,}"
        )
        print(
            "Net Obligations .................... "
            f"{money(net_obligations)}"
        )
        print(SUBLINE)

    print(
        "NOTE: Transactions carrying multiple COVID DEFC codes appear in"
    )
    print(
        "multiple code rows. DEFC-code dollar totals are therefore"
    )
    print(
        "NON-ADDITIVE. Statewide totals count each transaction once."
    )
    print()


def top_agencies(
    cur,
    *,
    load_batch_id: int,
    limit: int = 25,
) -> None:
    """Print top awarding agencies by net COVID obligations."""

    sql = create_covid_transaction_cte() + """
        SELECT
            agency.agency_name,
            COUNT(*) AS transaction_count,
            COALESCE(
                SUM(covid_transaction.federal_action_obligation),
                0
            ) AS net_obligations

        FROM covid_transaction

        LEFT JOIN procurement.agency AS agency
          ON agency.agency_id
             = covid_transaction.awarding_agency_id

        GROUP BY agency.agency_name

        ORDER BY
            net_obligations DESC,
            agency.agency_name

        LIMIT %s;
    """

    cur.execute(
        sql,
        (
            load_batch_id,
            limit,
        ),
    )

    print(LINE)
    print("6. TOP AWARDING AGENCIES")
    print(LINE)

    for agency_name, transaction_count, net in cur.fetchall():
        print(
            f"{(agency_name or '(missing)')[:60]:<62}"
            f"{int(transaction_count):>10,}   "
            f"{money(net):>22}"
        )

    print()


def top_recipients(
    cur,
    *,
    load_batch_id: int,
    limit: int = 50,
) -> None:
    """Print top recipients by net COVID obligations."""

    sql = create_covid_transaction_cte() + """
        SELECT
            recipient.recipient_name,
            COUNT(*) AS transaction_count,
            COALESCE(
                SUM(covid_transaction.federal_action_obligation),
                0
            ) AS net_obligations

        FROM covid_transaction

        LEFT JOIN procurement.recipient AS recipient
          ON recipient.recipient_id
             = covid_transaction.recipient_id

        GROUP BY recipient.recipient_name

        ORDER BY
            net_obligations DESC,
            recipient.recipient_name

        LIMIT %s;
    """

    cur.execute(
        sql,
        (
            load_batch_id,
            limit,
        ),
    )

    print(LINE)
    print("7. TOP RECIPIENTS")
    print(LINE)

    for recipient_name, transaction_count, net in cur.fetchall():
        print(
            f"{(recipient_name or '(missing)')[:68]:<70}"
            f"{int(transaction_count):>10,}   "
            f"{money(net):>22}"
        )

    print()


def county_ledger(
    cur,
    *,
    load_batch_id: int,
) -> tuple[list[tuple[str, int, Decimal]], Decimal]:
    """Print Washington county and unspecified COVID obligations."""

    sql = create_covid_transaction_cte() + """
        SELECT
            geography,
            transaction_count,
            net_obligations

        FROM (
            SELECT
                CASE
                    WHEN place.place_source_condition
                         = 'WASHINGTON_UNSPECIFIED'
                    THEN 'WASHINGTON UNSPECIFIED'
                    ELSE COALESCE(
                        place.county_name,
                        'WASHINGTON UNSPECIFIED'
                    )
                END AS geography,

                COUNT(*) AS transaction_count,

                COALESCE(
                    SUM(
                        covid_transaction
                        .federal_action_obligation
                    ),
                    0
                ) AS net_obligations

            FROM covid_transaction

            LEFT JOIN procurement.place AS place
              ON place.place_id
                 = covid_transaction.place_of_performance_id

            GROUP BY
                CASE
                    WHEN place.place_source_condition
                         = 'WASHINGTON_UNSPECIFIED'
                    THEN 'WASHINGTON UNSPECIFIED'
                    ELSE COALESCE(
                        place.county_name,
                        'WASHINGTON UNSPECIFIED'
                    )
                END
        ) AS geography_summary

        ORDER BY
            CASE
                WHEN geography = 'WASHINGTON UNSPECIFIED'
                THEN 1
                ELSE 0
            END,
            geography;
    """

    cur.execute(
        sql,
        (load_batch_id,),
    )

    rows = [
        (
            str(row[0]),
            int(row[1]),
            Decimal(row[2]),
        )
        for row in cur.fetchall()
    ]

    print(LINE)
    print("8. COUNTY LEDGER")
    print(LINE)
    print(
        f"{'Geography':<40}"
        f"{'Transactions':>16}"
        f"{'Net Obligations':>28}"
    )
    print(SUBLINE)

    for geography, transaction_count, net in rows:
        print(
            f"{geography:<40}"
            f"{transaction_count:>16,}"
            f"{money(net):>28}"
        )

    county_total = sum(
        (
            net
            for geography, _, net in rows
            if geography != "WASHINGTON UNSPECIFIED"
        ),
        Decimal("0"),
    )

    unspecified_total = sum(
        (
            net
            for geography, _, net in rows
            if geography == "WASHINGTON UNSPECIFIED"
        ),
        Decimal("0"),
    )

    print()
    print("GEOGRAPHIC RECONCILIATION")
    print(SUBLINE)
    print(
        "County-resolved obligations ........ "
        f"{money(county_total)}"
    )
    print(
        "Washington unspecified ............. "
        f"{money(unspecified_total)}"
    )
    print(
        "Geographic grand total ............. "
        f"{money(county_total + unspecified_total)}"
    )
    print()

    return rows, county_total + unspecified_total


def data_quality(
    cur,
    *,
    load_batch_id: int,
) -> dict[str, int]:
    """Print DEFC and transaction-quality metrics."""

    cur.execute(
        """
        SELECT
            COUNT(*)
        FROM (
            SELECT
                transaction.assistance_transaction_id
            FROM assistance.award_transaction AS transaction
            WHERE transaction.load_batch_id = %s
            GROUP BY transaction.assistance_transaction_id
            HAVING COUNT(*) > 1
        ) AS duplicates;
        """,
        (load_batch_id,),
    )

    duplicate_transactions = int(
        cur.fetchone()[0]
    )

    # These figures are generated by the completed ETL-005D.6 evidence-mode
    # classification. They are reproduced from the normalized transaction
    # source rather than assumed.
    cur.execute(
        """
        SELECT
            disaster_emergency_fund_codes_raw
        FROM assistance.award_transaction
        WHERE load_batch_id = %s
          AND NULLIF(
                BTRIM(disaster_emergency_fund_codes_raw),
                ''
              ) IS NOT NULL;
        """,
        (load_batch_id,),
    )

    from etl.common.extraordinary_funding.defc_parser import (
        parse_defc_value,
    )

    cur.execute(
        """
        SELECT defc_code
        FROM reference.extraordinary_funding_code;
        """
    )

    known_codes = {
        str(row[0]).upper()
        for row in cur.fetchall()
    }

    unknown_observation_count = 0
    unknown_codes: set[str] = set()
    unparsed_segment_count = 0
    parsed_observation_count = 0

    # Need a new cursor result because the reference query above replaced
    # the previous result set.
    cur.execute(
        """
        SELECT
            disaster_emergency_fund_codes_raw
        FROM assistance.award_transaction
        WHERE load_batch_id = %s
          AND NULLIF(
                BTRIM(disaster_emergency_fund_codes_raw),
                ''
              ) IS NOT NULL;
        """,
        (load_batch_id,),
    )

    for (raw_value,) in cur.fetchall():
        result = parse_defc_value(
            raw_value
        )

        parsed_observation_count += len(
            result.observations
        )

        unparsed_segment_count += len(
            result.unparsed_segments
        )

        for observation in result.observations:
            if observation.code not in known_codes:
                unknown_observation_count += 1
                unknown_codes.add(
                    observation.code
                )

    print(LINE)
    print("9. DATA QUALITY")
    print(LINE)
    print(
        "Duplicate normalized transactions ... "
        f"{duplicate_transactions:,}"
    )
    print(
        "Unknown DEFC observations ........... "
        f"{unknown_observation_count:,}"
    )
    print(
        "Distinct unknown DEFC codes ......... "
        f"{len(unknown_codes):,}"
    )
    print(
        "Unparsed DEFC segments .............. "
        f"{unparsed_segment_count:,}"
    )
    print(
        "Parsed DEFC observations ............ "
        f"{parsed_observation_count:,}"
    )
    print(
        "Validation ......................... "
        f"{'PASS' if duplicate_transactions == 0 and unparsed_segment_count == 0 else 'FAIL'}"
    )
    print()

    return {
        "duplicate_transactions": duplicate_transactions,
        "unknown_observation_count": unknown_observation_count,
        "unknown_code_count": len(unknown_codes),
        "unparsed_segment_count": unparsed_segment_count,
        "parsed_observation_count": parsed_observation_count,
    }


def print_reconciliation(
    *,
    activity: dict[str, object],
    statewide: dict[str, Decimal],
    fiscal_year_rows: list[
        tuple[int, int, Decimal, Decimal, Decimal]
    ],
    geographic_total: Decimal,
    data_quality_result: dict[str, int],
) -> None:
    """Print final internal reconciliation."""

    fy_transaction_count = sum(
        row[1]
        for row in fiscal_year_rows
    )

    fy_net_total = sum(
        (
            row[4]
            for row in fiscal_year_rows
        ),
        Decimal("0"),
    )

    expected_transactions = int(
        activity["transaction_count"]
    )

    transaction_pass = (
        fy_transaction_count
        == expected_transactions
    )

    fiscal_year_pass = (
        fy_net_total
        == statewide["net"]
    )

    geographic_pass = (
        geographic_total
        == statewide["net"]
    )

    overall_pass = all(
        [
            transaction_pass,
            fiscal_year_pass,
            geographic_pass,
            data_quality_result[
                "duplicate_transactions"
            ] == 0,
            data_quality_result[
                "unparsed_segment_count"
            ] == 0,
        ]
    )

    print(LINE)
    print("10. FINAL RECONCILIATION")
    print(LINE)

    print("TRANSACTION RECONCILIATION")
    print(SUBLINE)
    print(
        "Distinct COVID transactions ......... "
        f"{expected_transactions:,}"
    )
    print(
        "Fiscal-year transaction sum ......... "
        f"{fy_transaction_count:,}"
    )
    print(
        "Validation ......................... "
        f"{'PASS' if transaction_pass else 'FAIL'}"
    )
    print()

    print("FISCAL-YEAR DOLLAR RECONCILIATION")
    print(SUBLINE)
    print(
        "Fiscal-year net total ............... "
        f"{money(fy_net_total)}"
    )
    print(
        "Statewide net total ................. "
        f"{money(statewide['net'])}"
    )
    print(
        "Validation ......................... "
        f"{'PASS' if fiscal_year_pass else 'FAIL'}"
    )
    print()

    print("GEOGRAPHIC DOLLAR RECONCILIATION")
    print(SUBLINE)
    print(
        "County + unspecified total .......... "
        f"{money(geographic_total)}"
    )
    print(
        "Statewide net total ................. "
        f"{money(statewide['net'])}"
    )
    print(
        "Validation ......................... "
        f"{'PASS' if geographic_pass else 'FAIL'}"
    )
    print()

    print(
        "OVERALL PROFILE VALIDATION .......... "
        f"{'PASS' if overall_pass else 'FAIL'}"
    )
    print(LINE)


def print_ascii_timeline(
    fiscal_year_rows: list[
        tuple[int, int, Decimal, Decimal, Decimal]
    ],
) -> None:
    """Print a compact proportional ASCII timeline."""

    print()
    print(LINE)
    print("11. COVID ASSISTANCE TIMELINE")
    print(LINE)

    if not fiscal_year_rows:
        print("(no fiscal-year observations)")
        return

    maximum = max(
        abs(row[4])
        for row in fiscal_year_rows
    )

    if maximum == 0:
        maximum = Decimal("1")

    width = 50

    for fy, _, _, _, net in fiscal_year_rows:
        bar_length = int(
            (
                abs(net)
                / maximum
            )
            * width
        )

        bar = "█" * bar_length

        print(
            f"FY{fy}  "
            f"{bar:<50}  "
            f"{money(net)}"
        )

    print()


def main() -> None:
    args = parse_arguments()

    print_header(
        load_batch_id=args.load_batch_id,
    )

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            activity = activity_window(
                cur,
                load_batch_id=args.load_batch_id,
            )

            transaction_inventory(
                cur,
                load_batch_id=args.load_batch_id,
            )

            statewide = statewide_obligation_summary(
                cur,
                load_batch_id=args.load_batch_id,
            )

            fiscal_year_rows = fiscal_year_ledger(
                cur,
                load_batch_id=args.load_batch_id,
            )

            defc_ledger(
                cur,
                load_batch_id=args.load_batch_id,
            )

            top_agencies(
                cur,
                load_batch_id=args.load_batch_id,
            )

            top_recipients(
                cur,
                load_batch_id=args.load_batch_id,
            )

            (
                _county_rows,
                geographic_total,
            ) = county_ledger(
                cur,
                load_batch_id=args.load_batch_id,
            )

            quality = data_quality(
                cur,
                load_batch_id=args.load_batch_id,
            )

            print_reconciliation(
                activity=activity,
                statewide=statewide,
                fiscal_year_rows=fiscal_year_rows,
                geographic_total=geographic_total,
                data_quality_result=quality,
            )

            print_ascii_timeline(
                fiscal_year_rows
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
