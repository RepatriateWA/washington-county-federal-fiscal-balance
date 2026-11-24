
"""ETL-201N Stage B: historical canonical award dry audit.

READ ONLY. No canonical award inserts, updates, or deletes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date
from decimal import Decimal
from time import perf_counter

from etl.common.db import get_connection
from etl.loaders.normalize_usaspending_assistance_awards import (
    AwardObservation,
    build_canonical_awards,
    parse_date,
    parse_decimal,
)
from etl.common.normalization.text import clean_optional_text


EXPECTED_SOURCE_ROWS = 174_622
EXPECTED_AWARDS = 156_401
EXPECTED_MISSING_REFERENCES = 0

BATCH_IDS = (20, 21)
ROW_NUMBER_MULTIPLIER = 1_000_000_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract_candidates(cur):
    """Extract only the approved missing, nonconflicted cohort."""

    cur.execute(
        """
        WITH historical AS MATERIALIZED (
            SELECT
                r.assistance_award_unique_key AS award_key,
                r.load_batch_id,
                r.source_row_number,
                r.raw_record,
                NULLIF(
                    BTRIM(r.raw_record ->> 'cfda_number'), ''
                ) AS listing_code,
                NULLIF(
                    BTRIM(
                        r.raw_record ->> 'assistance_type_code'
                    ), ''
                ) AS type_code
            FROM assistance.raw_award_transaction AS r
            WHERE r.load_batch_id IN (20, 21)
        ),
        eligible AS MATERIALIZED (
            SELECT h.award_key
            FROM historical AS h
            LEFT JOIN assistance.award AS a
              ON a.assistance_award_unique_key = h.award_key
            WHERE a.assistance_award_unique_key IS NULL
            GROUP BY h.award_key
            HAVING COUNT(DISTINCT h.listing_code) <= 1
               AND COUNT(DISTINCT h.type_code) <= 1
        )
        SELECT
            h.award_key,
            h.load_batch_id,
            h.source_row_number,
            h.raw_record ->> 'action_date',
            h.raw_record ->> 'award_id_fain',
            h.raw_record ->> 'award_id_uri',
            h.raw_record ->> 'sai_number',
            h.raw_record ->> 'recipient_name',
            h.raw_record
                ->> 'prime_award_base_transaction_description',
            l.assistance_listing_id,
            t.assistance_type_id,
            f.funding_opportunity_id,
            h.raw_record
                ->> 'period_of_performance_start_date',
            h.raw_record
                ->> 'period_of_performance_current_end_date',
            h.raw_record ->> 'total_obligated_amount',
            h.raw_record
                ->> 'total_outlayed_amount_for_overall_award',
            h.raw_record
                ->> 'total_non_federal_funding_amount',
            h.raw_record ->> 'total_face_value_of_loan',
            h.raw_record ->> 'total_loan_subsidy_cost',
            h.listing_code,
            h.type_code,
            NULLIF(
                BTRIM(
                    h.raw_record ->> 'funding_opportunity_number'
                ), ''
            )
        FROM historical AS h
        JOIN eligible AS e
          ON e.award_key = h.award_key
        LEFT JOIN assistance.assistance_listing AS l
          ON l.cfda_number = h.listing_code
        LEFT JOIN assistance.assistance_type AS t
          ON t.assistance_type_code = h.type_code
        LEFT JOIN assistance.funding_opportunity AS f
          ON f.funding_opportunity_number = NULLIF(
              BTRIM(
                  h.raw_record ->> 'funding_opportunity_number'
              ), ''
          )
        ORDER BY
            h.award_key,
            h.load_batch_id,
            h.source_row_number
        """
    )

    return cur.fetchall()


def checked_date(value, field, identity):
    cleaned = clean_optional_text(value)
    result = parse_date(value)

    if cleaned is not None:
        require(
            result is not None,
            f"Invalid {field}: {identity}: {value!r}",
        )

    return result


def main():
    started = perf_counter()
    conn = get_connection()

    try:
        conn.set_session(
            isolation_level="REPEATABLE READ",
            readonly=True,
            autocommit=False,
        )

        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '600s'")

            rows = extract_candidates(cur)

            print("=" * 72)
            print("ETL-201N STAGE B - CANONICALIZATION AUDIT")
            print("READ ONLY - NO DATABASE WRITES")
            print("=" * 72)

            print(f"Extracted source observations: {len(rows):,}")

            require(
                len(rows) == EXPECTED_SOURCE_ROWS,
                "Source observation count mismatch",
            )

            observations = []
            batch_counts = Counter()
            invalid_references = 0
            source_identities = set()
            cross_batch_ties = Counter()

            for row in rows:
                (
                    award_key,
                    batch_id,
                    source_row_number,
                    action_date_text,
                    fain,
                    uri,
                    sai,
                    recipient,
                    description,
                    listing_id,
                    type_id,
                    opportunity_id,
                    start_text,
                    end_text,
                    obligated,
                    outlayed,
                    nonfederal,
                    loan_face,
                    loan_subsidy,
                    listing_code,
                    type_code,
                    opportunity_code,
                ) = row

                identity = (batch_id, source_row_number)

                require(
                    identity not in source_identities,
                    f"Duplicate source identity: {identity}",
                )
                source_identities.add(identity)

                require(
                    0 <= source_row_number < ROW_NUMBER_MULTIPLIER,
                    f"Source row outside tie-break range: {identity}",
                )

                batch_counts[batch_id] += 1

                if (
                    listing_id is None
                    or type_id is None
                    or (
                        opportunity_code is not None
                        and opportunity_id is None
                    )
                ):
                    invalid_references += 1
                    continue

                action_date = checked_date(
                    action_date_text, "action_date", identity
                )
                start_date = checked_date(
                    start_text, "performance_start", identity
                )
                end_date = checked_date(
                    end_text, "performance_end", identity
                )

                require(
                    action_date is not None,
                    f"Missing action date: {identity}",
                )

                cross_batch_ties[
                    (award_key, action_date, source_row_number)
                ] += 1

                observation = AwardObservation(
                    assistance_award_unique_key=award_key,
                    source_row_number=(
                        batch_id * ROW_NUMBER_MULTIPLIER
                        + source_row_number
                    ),
                    action_date=action_date,
                    award_id_fain=clean_optional_text(fain),
                    award_id_uri=clean_optional_text(uri),
                    sai_number=clean_optional_text(sai),
                    recipient_name=clean_optional_text(recipient),
                    award_description=clean_optional_text(description),
                    assistance_listing_id=int(listing_id),
                    assistance_type_id=int(type_id),
                    funding_opportunity_id=(
                        int(opportunity_id)
                        if opportunity_id is not None
                        else None
                    ),
                    performance_start_date=start_date,
                    performance_end_date=end_date,
                    total_obligated_amount=parse_decimal(obligated),
                    total_outlayed_amount=parse_decimal(outlayed),
                    total_non_federal_funding_amount=(
                        parse_decimal(nonfederal)
                    ),
                    total_face_value_of_loan=parse_decimal(loan_face),
                    total_loan_subsidy_cost=parse_decimal(loan_subsidy),
                )
                observations.append(observation)

            require(
                invalid_references == EXPECTED_MISSING_REFERENCES,
                f"Unresolved dimension rows: {invalid_references}",
            )

            require(
                len(observations) == EXPECTED_SOURCE_ROWS,
                "Observation conversion did not reconcile",
            )

            awards = build_canonical_awards(observations)

            require(
                len(awards) == EXPECTED_AWARDS,
                f"Expected {EXPECTED_AWARDS:,} canonical awards; "
                f"found {len(awards):,}",
            )

            keys = {
                award.assistance_award_unique_key
                for award in awards
            }

            require(
                len(keys) == EXPECTED_AWARDS,
                "Duplicate canonical award keys",
            )

            missing_identifiers = sum(
                award.award_id_fain is None
                and award.award_id_uri is None
                for award in awards
            )

            inverted_action_dates = sum(
                award.first_action_date is not None
                and award.last_action_date is not None
                and award.first_action_date > award.last_action_date
                for award in awards
            )

            require(
                missing_identifiers == 0,
                "Canonical awards without FAIN or URI",
            )
            require(
                inverted_action_dates == 0,
                "Inverted canonical action-date ranges",
            )

            print()
            print("SOURCE RECONCILIATION")
            print(f"FY2018 observations: {batch_counts[20]:,}")
            print(f"FY2019 observations: {batch_counts[21]:,}")
            print(f"Unique source identities: {len(source_identities):,}")

            tie_groups = sum(
                count > 1
                for count in cross_batch_ties.values()
            )
            print(f"Equal-date/row tie groups: {tie_groups:,}")

            print()
            print("CANONICAL RECONCILIATION")
            print(f"Canonical awards: {len(awards):,}")
            print(f"Unique canonical keys: {len(keys):,}")
            print(f"Missing identifiers: {missing_identifiers:,}")
            print(f"Inverted action dates: {inverted_action_dates:,}")
            print(f"Unresolved dimension rows: {invalid_references:,}")

            print()
            print("ETL-201N STAGE B: PASS")
            print("No canonical award writes performed.")

        conn.rollback()

        print("Transaction: ROLLBACK")
        print(f"Elapsed seconds: {perf_counter() - started:.1f}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
