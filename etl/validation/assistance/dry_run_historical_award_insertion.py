
"""ETL-201N Stage C: rollback-only historical award insertion.

Tests actual PostgreSQL INSERT statements for the FY2018/FY2019
approved historical cohort.

NO PERMANENT DATABASE WRITES.
Every execution path rolls back the insertion transaction.
"""

from __future__ import annotations

from collections import Counter
from time import perf_counter

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.common.normalization.text import clean_optional_text
from etl.loaders.normalize_usaspending_assistance_awards import (
    AwardObservation,
    build_canonical_awards,
    parse_date,
    parse_decimal,
)
from etl.validation.assistance.audit_historical_award_canonicalization import (
    extract_candidates,
)

EXPECTED_SOURCE_ROWS = 174_622
EXPECTED_AWARDS = 156_401
EXPECTED_EXISTING_HISTORICAL = 10_219
EXPECTED_HELD = 90

ROW_MULTIPLIER = 1_000_000_000
INSERT_BATCH_SIZE = 2_000

COLUMNS = (
    "assistance_award_unique_key",
    "award_id_fain",
    "award_id_uri",
    "sai_number",
    "assistance_listing_id",
    "assistance_type_id",
    "funding_opportunity_id",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "total_obligated_amount",
    "total_outlayed_amount",
    "total_non_federal_funding_amount",
    "total_face_value_of_loan",
    "total_loan_subsidy_cost",
    "canonical_recipient_name",
    "canonical_award_description",
    "first_action_date",
    "last_action_date",
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def count_awards(cur):
    cur.execute("SELECT COUNT(*) FROM assistance.award")
    return int(cur.fetchone()[0])


def historical_controls(cur):
    cur.execute(
        """
        WITH historical AS MATERIALIZED (
            SELECT
                assistance_award_unique_key AS award_key,
                COUNT(DISTINCT NULLIF(
                    BTRIM(raw_record ->> 'cfda_number'), ''
                )) AS listing_count,
                COUNT(DISTINCT NULLIF(
                    BTRIM(raw_record ->> 'assistance_type_code'), ''
                )) AS type_count
            FROM assistance.raw_award_transaction
            WHERE load_batch_id IN (20, 21)
            GROUP BY assistance_award_unique_key
        )
        SELECT
            COUNT(*) FILTER (
                WHERE a.assistance_award_unique_key IS NOT NULL
            ),
            COUNT(*) FILTER (
                WHERE a.assistance_award_unique_key IS NULL
                  AND h.listing_count <= 1
                  AND h.type_count <= 1
            ),
            COUNT(*) FILTER (
                WHERE a.assistance_award_unique_key IS NULL
                  AND (
                      h.listing_count > 1
                      OR h.type_count > 1
                  )
            )
        FROM historical AS h
        LEFT JOIN assistance.award AS a
          ON a.assistance_award_unique_key = h.award_key
        """
    )
    return tuple(int(value) for value in cur.fetchone())


def convert_rows(rows):
    observations = []
    identities = set()
    batch_counts = Counter()

    for row in rows:
        (
            award_key,
            batch_id,
            source_row,
            action_text,
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

        identity = (batch_id, source_row)

        require(
            identity not in identities,
            f"Duplicate source identity: {identity}",
        )
        identities.add(identity)

        require(
            0 <= source_row < ROW_MULTIPLIER,
            f"Invalid source row: {identity}",
        )

        require(
            listing_id is not None and type_id is not None,
            f"Missing required dimension: {identity}",
        )

        require(
            opportunity_code is None
            or opportunity_id is not None,
            f"Missing opportunity reference: {identity}",
        )

        for field, value in (
            ("action_date", action_text),
            ("performance_start", start_text),
            ("performance_end", end_text),
        ):
            if clean_optional_text(value) is not None:
                require(
                    parse_date(value) is not None,
                    f"Invalid {field}: {identity}: {value!r}",
                )

        action_date = parse_date(action_text)

        require(
            action_date is not None,
            f"Missing action date: {identity}",
        )

        batch_counts[batch_id] += 1

        observations.append(
            AwardObservation(
                assistance_award_unique_key=award_key,
                source_row_number=(
                    batch_id * ROW_MULTIPLIER + source_row
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
                performance_start_date=parse_date(start_text),
                performance_end_date=parse_date(end_text),
                total_obligated_amount=parse_decimal(obligated),
                total_outlayed_amount=parse_decimal(outlayed),
                total_non_federal_funding_amount=(
                    parse_decimal(nonfederal)
                ),
                total_face_value_of_loan=parse_decimal(loan_face),
                total_loan_subsidy_cost=parse_decimal(loan_subsidy),
            )
        )

    require(
        len(observations) == EXPECTED_SOURCE_ROWS,
        "Source observation count mismatch",
    )

    require(
        batch_counts[20] == 87_316
        and batch_counts[21] == 87_306,
        f"Unexpected batch counts: {batch_counts}",
    )

    return observations


def award_values(award):
    return tuple(getattr(award, column) for column in COLUMNS)


def verify_after_rollback(expected_count):
    """Use a separate connection to verify persistent state."""

    conn = get_connection()

    try:
        conn.set_session(
            isolation_level="REPEATABLE READ",
            readonly=True,
            autocommit=False,
        )

        with conn.cursor() as cur:
            actual_count = count_awards(cur)
            existing, missing, held = historical_controls(cur)

            require(
                actual_count == expected_count,
                "Persistent canonical award count changed",
            )

            require(
                existing == EXPECTED_EXISTING_HISTORICAL,
                "Existing historical population changed",
            )

            require(
                missing == EXPECTED_AWARDS,
                "Historical insertion candidates changed",
            )

            require(
                held == EXPECTED_HELD,
                "Held historical population changed",
            )

        conn.rollback()

        print()
        print("INDEPENDENT POST-ROLLBACK VERIFICATION")
        print(f"Persistent award count: {actual_count:,}")
        print(f"Existing historical awards: {existing:,}")
        print(f"Missing candidate awards: {missing:,}")
        print(f"Held conflicted awards: {held:,}")
        print("Post-rollback verification: PASS")

    finally:
        conn.rollback()
        conn.close()


def main():
    started = perf_counter()
    conn = get_connection()

    baseline_count = None
    rolled_back = False

    print("=" * 72)
    print("ETL-201N STAGE C - HISTORICAL AWARD INSERTION DRY RUN")
    print("ROLLBACK ONLY - NO PERMANENT DATABASE WRITES")
    print("=" * 72)

    try:
        conn.set_session(
            isolation_level="REPEATABLE READ",
            readonly=False,
            autocommit=False,
        )

        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '1800s'")
            cur.execute("SET LOCAL lock_timeout = '30s'")

            # Prevent concurrent canonical award modifications
            # during the dry-run transaction.
            cur.execute(
                """
                LOCK TABLE assistance.award
                IN SHARE ROW EXCLUSIVE MODE
                """
            )

            baseline_count = count_awards(cur)

            existing, missing, held = historical_controls(cur)

            print()
            print("PRE-INSERTION CONTROLS")
            print(f"Baseline canonical awards: {baseline_count:,}")
            print(f"Existing historical awards: {existing:,}")
            print(f"Missing eligible awards: {missing:,}")
            print(f"Held conflicted awards: {held:,}")

            require(
                existing == EXPECTED_EXISTING_HISTORICAL,
                "Existing historical count mismatch",
            )
            require(
                missing == EXPECTED_AWARDS,
                "Eligible cohort count mismatch",
            )
            require(
                held == EXPECTED_HELD,
                "Held cohort count mismatch",
            )

            rows = extract_candidates(cur)

            require(
                len(rows) == EXPECTED_SOURCE_ROWS,
                "Candidate source count mismatch",
            )

            observations = convert_rows(rows)
            awards = build_canonical_awards(observations)

            require(
                len(awards) == EXPECTED_AWARDS,
                "Canonical award count mismatch",
            )

            keys = {
                award.assistance_award_unique_key
                for award in awards
            }

            require(
                len(keys) == EXPECTED_AWARDS,
                "Duplicate canonical award keys",
            )

            require(
                all(
                    award.award_id_fain is not None
                    or award.award_id_uri is not None
                    for award in awards
                ),
                "Missing canonical identifier",
            )

            print()
            print("CANONICALIZATION")
            print(f"Source observations: {len(observations):,}")
            print(f"Canonical awards: {len(awards):,}")
            print(f"Unique canonical keys: {len(keys):,}")

            insert_sql = (
                "INSERT INTO assistance.award ("
                + ", ".join(COLUMNS)
                + ") VALUES %s"
            )

            inserted = 0

            print()
            print("ROLLBACK-ONLY INSERTION TEST")

            for start in range(
                0, len(awards), INSERT_BATCH_SIZE
            ):
                batch = awards[
                    start:start + INSERT_BATCH_SIZE
                ]

                values = [
                    award_values(award)
                    for award in batch
                ]

                execute_values(
                    cur,
                    insert_sql,
                    values,
                    page_size=1_000,
                )

                inserted += len(batch)

                if (
                    inserted % 20_000 == 0
                    or inserted == len(awards)
                ):
                    print(
                        f"Temporarily inserted: {inserted:,}",
                        flush=True,
                    )

            require(
                inserted == EXPECTED_AWARDS,
                "Insertion total mismatch",
            )

            in_transaction_count = count_awards(cur)

            require(
                in_transaction_count
                == baseline_count + EXPECTED_AWARDS,
                "In-transaction award count mismatch",
            )

            existing_after, missing_after, held_after = (
                historical_controls(cur)
            )

            require(
                existing_after
                == EXPECTED_EXISTING_HISTORICAL
                + EXPECTED_AWARDS,
                "Historical representation mismatch",
            )

            require(
                missing_after == 0,
                "Eligible awards remain missing",
            )

            require(
                held_after == EXPECTED_HELD,
                "Held population changed",
            )

            print()
            print("IN-TRANSACTION VALIDATION")
            print(
                f"Canonical award count: "
                f"{in_transaction_count:,}"
            )
            print(
                f"Historical awards represented: "
                f"{existing_after:,}"
            )
            print(
                f"Remaining eligible awards: "
                f"{missing_after:,}"
            )
            print(
                f"Held conflicted awards: "
                f"{held_after:,}"
            )
            print("Insertion constraints: PASS")

        # Unconditional rollback. There is no commit path.
        conn.rollback()
        rolled_back = True

        print()
        print("TRANSACTION: ROLLBACK COMPLETE")
        print("No historical canonical awards committed.")

    except Exception as exc:
        conn.rollback()
        rolled_back = True

        print()
        print("DRY RUN FAILED - TRANSACTION ROLLED BACK")
        print(f"{type(exc).__name__}: {exc}")
        raise

    finally:
        if not rolled_back:
            conn.rollback()
        conn.close()

    require(
        baseline_count is not None,
        "Baseline count was not established",
    )

    verify_after_rollback(baseline_count)

    print()
    print("=" * 72)
    print("ETL-201N STAGE C: PASS")
    print("ROLLBACK VERIFIED - NO PERMANENT DATABASE WRITES")
    print(f"Elapsed seconds: {perf_counter() - started:.1f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
