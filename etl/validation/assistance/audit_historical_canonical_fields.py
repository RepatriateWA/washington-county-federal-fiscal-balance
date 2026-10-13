
"""ETL-201P Stage B.2 - historical canonical field certification.

Reconstruct the exact ETL-201O insertion cohort from FY2018/FY2019
raw observations and compare all 18 canonical fields.

READ ONLY. No inserts, updates, deletes, or temporary tables.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter

import psycopg2

from etl.loaders.normalize_usaspending_assistance_awards import (
    build_canonical_awards,
)
from etl.validation.assistance.dry_run_historical_award_insertion import (
    COLUMNS,
    EXPECTED_SOURCE_ROWS,
    award_values,
    convert_rows,
    count_awards,
    historical_controls,
)

INSERTED_AT = datetime(2026, 10, 12, 17, 3, 17, 282444)

EXPECTED_INSERTED = 156_401
EXPECTED_TOTAL = 968_547
EXPECTED_REPRESENTED = 166_620
EXPECTED_HELD = 90
EXPECTED_PREEXISTING = 10_219

FETCH_SIZE = 2000
MAX_EXAMPLES = 30

NUMERIC_FIELDS = {
    "total_obligated_amount",
    "total_outlayed_amount",
    "total_non_federal_funding_amount",
    "total_face_value_of_loan",
    "total_loan_subsidy_cost",
}

DATE_FIELDS = {
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "first_action_date",
    "last_action_date",
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def connection():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "wcffbp"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD"),
    )


def extract_inserted_observations(cur):
    """Use original extraction fields, restricted to ETL-201O cohort."""

    cur.execute(
        """
        WITH inserted AS MATERIALIZED (
            SELECT assistance_award_unique_key AS award_key
            FROM assistance.award
            WHERE created_at = %s
        ),
        historical AS MATERIALIZED (
            SELECT
                r.assistance_award_unique_key AS award_key,
                r.load_batch_id,
                r.source_row_number,
                r.raw_record,
                NULLIF(
                    BTRIM(r.raw_record ->> 'cfda_number'), ''
                ) AS listing_code,
                NULLIF(
                    BTRIM(r.raw_record ->> 'assistance_type_code'), ''
                ) AS type_code
            FROM assistance.raw_award_transaction AS r
            JOIN inserted AS i
              ON i.award_key = r.assistance_award_unique_key
            WHERE r.load_batch_id IN (20, 21)
        ),
        eligible AS MATERIALIZED (
            SELECT h.award_key
            FROM historical AS h
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
        """,
        (INSERTED_AT,),
    )

    return cur.fetchall()


def normalize(field, value):
    if value is None:
        return None

    if field in NUMERIC_FIELDS:
        return Decimal(str(value))

    if field in DATE_FIELDS:
        if isinstance(value, (date, datetime)):
            return value.date() if isinstance(value, datetime) else value
        return date.fromisoformat(str(value))

    return value


def main():
    started = perf_counter()
    conn = connection()

    print("=" * 76)
    print("ETL-201P STAGE B.2 - CANONICAL FIELD CERTIFICATION")
    print("FY2018 / FY2019 - READ ONLY")
    print("=" * 76, flush=True)

    try:
        conn.set_session(
            isolation_level="REPEATABLE READ",
            readonly=True,
            autocommit=False,
        )

        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '1800s'")

            print("\nSECTION 1 - POPULATION GUARDRAILS")

            total = count_awards(cur)
            represented, missing, held = historical_controls(cur)

            require(total == EXPECTED_TOTAL, "Total canonical count changed")
            require(
                represented == EXPECTED_REPRESENTED,
                "Represented historical count changed",
            )
            require(missing == 0, "Eligible historical awards missing")
            require(held == EXPECTED_HELD, "Held historical count changed")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM assistance.award
                WHERE created_at = %s
                """,
                (INSERTED_AT,),
            )
            timestamp_total = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM assistance.award AS a
                WHERE a.created_at = %s
                  AND EXISTS (
                      SELECT 1
                      FROM assistance.raw_award_transaction AS r
                      WHERE r.assistance_award_unique_key =
                            a.assistance_award_unique_key
                        AND r.load_batch_id IN (20, 21)
                  )
                """,
                (INSERTED_AT,),
            )
            historical_inserted = cur.fetchone()[0]

            print(f"Total canonical awards: {total:,}")
            print(f"Represented historical: {represented:,}")
            print(f"Eligible historical missing: {missing:,}")
            print(f"Held conflicted: {held:,}")
            print(f"Exact-timestamp canonical: {timestamp_total:,}")
            print(f"Historical insertion cohort: {historical_inserted:,}")

            require(
                historical_inserted == EXPECTED_INSERTED,
                "Historical insertion cohort mismatch",
            )
            require(
                timestamp_total == EXPECTED_INSERTED,
                "Unexpected nonhistorical awards at insertion timestamp",
            )
            require(
                represented - historical_inserted == EXPECTED_PREEXISTING,
                "Pre-existing historical count mismatch",
            )

            print("\nSECTION 2 - RECONSTRUCT SOURCE OBSERVATIONS", flush=True)

            rows = extract_inserted_observations(cur)

            print(f"Source observations: {len(rows):,}", flush=True)

            require(
                len(rows) == EXPECTED_SOURCE_ROWS,
                "Historical source observation count mismatch",
            )

            observations = convert_rows(rows)
            reconstructed = build_canonical_awards(observations)

            print(
                f"Reconstructed awards: {len(reconstructed):,}",
                flush=True,
            )

            require(
                len(reconstructed) == EXPECTED_INSERTED,
                "Reconstructed award count mismatch",
            )
            require(len(COLUMNS) == 18, "Unexpected canonical field count")

            expected = {}

            for award in reconstructed:
                values = award_values(award)
                record = dict(zip(COLUMNS, values, strict=True))
                key = record["assistance_award_unique_key"]

                require(key not in expected, f"Duplicate expected key: {key}")
                expected[key] = record

            print("\nSECTION 3 - FIELD-BY-FIELD COMPARISON", flush=True)

            field_counts = Counter()
            examples = []
            seen = set()
            comparisons = 0

            columns_sql = ", ".join(
                f"a.{column}" for column in COLUMNS
            )

            sql = f"""
                SELECT {columns_sql}
                FROM assistance.award AS a
                WHERE a.assistance_award_unique_key = ANY(%s)
            """

            keys = list(expected)

            for start in range(0, len(keys), FETCH_SIZE):
                batch_keys = keys[start:start + FETCH_SIZE]

                cur.execute(sql, (batch_keys,))
                actual_rows = cur.fetchall()

                for actual_row in actual_rows:
                    actual = dict(zip(COLUMNS, actual_row, strict=True))
                    key = actual["assistance_award_unique_key"]

                    require(key in expected, f"Unexpected award: {key}")
                    require(key not in seen, f"Duplicate canonical key: {key}")

                    seen.add(key)
                    reference = expected[key]

                    for field in COLUMNS:
                        comparisons += 1

                        expected_value = normalize(
                            field, reference[field]
                        )
                        actual_value = normalize(
                            field, actual[field]
                        )

                        if expected_value != actual_value:
                            field_counts[field] += 1

                            if len(examples) < MAX_EXAMPLES:
                                examples.append(
                                    (
                                        key,
                                        field,
                                        expected_value,
                                        actual_value,
                                    )
                                )

                if (
                    (start // FETCH_SIZE + 1) % 10 == 0
                    or start + FETCH_SIZE >= len(keys)
                ):
                    print(
                        f"Compared awards: {len(seen):,}",
                        flush=True,
                    )

            missing_keys = set(expected) - seen
            mismatches = sum(field_counts.values())

            print("\nSECTION 4 - CERTIFICATION SUMMARY")
            print(f"Expected awards: {EXPECTED_INSERTED:,}")
            print(f"Compared awards: {len(seen):,}")
            print(f"Missing canonical keys: {len(missing_keys):,}")
            print(f"Canonical fields: {len(COLUMNS)}")
            print(f"Field comparisons: {comparisons:,}")
            print(f"Total field mismatches: {mismatches:,}")

            print("\nFIELD MISMATCH COUNTS")

            for field in COLUMNS:
                print(f"{field:45s} {field_counts[field]:>10,}")

            if examples:
                print("\nFIRST FIELD MISMATCH EXAMPLES")

                for key, field, expected_value, actual_value in examples:
                    print(f"Key: {key}")
                    print(f"  Field: {field}")
                    print(f"  Expected: {expected_value!r}")
                    print(f"  Actual:   {actual_value!r}")

            if missing_keys:
                print("\nFIRST MISSING KEYS")

                for key in sorted(missing_keys)[:MAX_EXAMPLES]:
                    print(key)

            require(not missing_keys, "Missing canonical records")
            require(
                len(seen) == EXPECTED_INSERTED,
                "Compared award count mismatch",
            )
            require(
                comparisons == EXPECTED_INSERTED * len(COLUMNS),
                "Field comparison count mismatch",
            )
            require(mismatches == 0, "Canonical field mismatches detected")

            print("\nETL-201P STAGE B.2: PASS")
            print("ALL 18 CANONICAL FIELDS MATCH")
            print("ZERO FIELD MISMATCHES")

    finally:
        conn.rollback()
        conn.close()

        print("\nTRANSACTION: ROLLBACK COMPLETE")
        print("NO DATABASE WRITES")
        print(f"Elapsed seconds: {perf_counter() - started:.1f}")
        print("=" * 76)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            f"ETL-201P STAGE B.2: FAIL - "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
