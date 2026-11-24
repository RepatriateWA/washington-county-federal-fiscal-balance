
"""ETL-201O v0.1 - Controlled historical canonical award insertion.

FY2018 batch 20 / FY2019 batch 21.

PERMANENT DATABASE WRITE.
INSERT ONLY. No UPSERT, UPDATE, or DELETE.
Commit only after all pre/post-insertion controls pass.

Requires the validated ETL-201N Stage C module.
"""

from __future__ import annotations

from time import perf_counter

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.loaders.normalize_usaspending_assistance_awards import (
    build_canonical_awards,
)
from etl.validation.assistance.dry_run_historical_award_insertion import (
    COLUMNS,
    INSERT_BATCH_SIZE,
    award_values,
    convert_rows,
    count_awards,
    historical_controls,
)
from etl.validation.assistance.audit_historical_award_canonicalization import (
    extract_candidates,
)


EXPECTED_BASELINE = 812_146
EXPECTED_EXISTING = 10_219
EXPECTED_CANDIDATES = 156_401
EXPECTED_HELD = 90
EXPECTED_SOURCE_ROWS = 174_622

EXPECTED_FINAL = EXPECTED_BASELINE + EXPECTED_CANDIDATES
EXPECTED_REPRESENTED = EXPECTED_EXISTING + EXPECTED_CANDIDATES


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def verify_committed_state():
    """Independent post-commit verification using a new connection."""

    conn = get_connection()

    try:
        conn.set_session(
            isolation_level="REPEATABLE READ",
            readonly=True,
            autocommit=False,
        )

        with conn.cursor() as cur:
            total = count_awards(cur)
            existing, missing, held = historical_controls(cur)

            require(
                total == EXPECTED_FINAL,
                f"Post-commit total mismatch: {total:,}",
            )
            require(
                existing == EXPECTED_REPRESENTED,
                f"Historical representation mismatch: {existing:,}",
            )
            require(
                missing == 0,
                f"Eligible awards remain missing: {missing:,}",
            )
            require(
                held == EXPECTED_HELD,
                f"Held population mismatch: {held:,}",
            )

        print()
        print("INDEPENDENT POST-COMMIT VERIFICATION")
        print(f"Persistent canonical awards: {total:,}")
        print(f"Historical awards represented: {existing:,}")
        print(f"Remaining eligible awards: {missing:,}")
        print(f"Held conflicted awards: {held:,}")
        print("Post-commit verification: PASS")

    finally:
        conn.rollback()
        conn.close()


def main():
    started = perf_counter()
    conn = get_connection()
    committed = False

    print("=" * 72)
    print("ETL-201O v0.1 - HISTORICAL CANONICAL AWARD INSERTION")
    print("FY2018 / FY2019 - CONTROLLED PERMANENT WRITE")
    print("INSERT ONLY - NO EXISTING AWARD UPDATES")
    print("=" * 72, flush=True)

    try:
        conn.set_session(
            isolation_level="REPEATABLE READ",
            readonly=False,
            autocommit=False,
        )

        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '1800s'")
            cur.execute("SET LOCAL lock_timeout = '30s'")

            # Protect the canonical table against concurrent writes.
            cur.execute(
                """
                LOCK TABLE assistance.award
                IN SHARE ROW EXCLUSIVE MODE
                """
            )

            baseline = count_awards(cur)
            existing, missing, held = historical_controls(cur)

            print()
            print("PRE-INSERTION CONTROLS")
            print(f"Canonical award baseline: {baseline:,}")
            print(f"Existing historical awards: {existing:,}")
            print(f"Eligible missing awards: {missing:,}")
            print(f"Held conflicted awards: {held:,}", flush=True)

            require(
                baseline == EXPECTED_BASELINE,
                "Canonical award baseline changed",
            )
            require(
                existing == EXPECTED_EXISTING,
                "Existing historical population changed",
            )
            require(
                missing == EXPECTED_CANDIDATES,
                "Eligible candidate population changed",
            )
            require(
                held == EXPECTED_HELD,
                "Held conflict population changed",
            )

            # Reuse the approved Stage B/C extraction and transformation.
            rows = extract_candidates(cur)

            require(
                len(rows) == EXPECTED_SOURCE_ROWS,
                "Candidate source observation count mismatch",
            )

            observations = convert_rows(rows)
            awards = build_canonical_awards(observations)

            require(
                len(awards) == EXPECTED_CANDIDATES,
                "Canonical award count mismatch",
            )

            keys = {
                award.assistance_award_unique_key
                for award in awards
            }

            require(
                len(keys) == EXPECTED_CANDIDATES,
                "Duplicate canonical award keys",
            )

            require(
                all(
                    a.award_id_fain is not None
                    or a.award_id_uri is not None
                    for a in awards
                ),
                "Canonical award missing FAIN and URI",
            )

            print()
            print("CANONICALIZATION")
            print(f"Source observations: {len(observations):,}")
            print(f"Canonical awards: {len(awards):,}")
            print(f"Unique canonical keys: {len(keys):,}", flush=True)

            insert_sql = (
                "INSERT INTO assistance.award ("
                + ", ".join(COLUMNS)
                + ") VALUES %s"
            )

            inserted = 0

            print()
            print("CONTROLLED INSERTION", flush=True)

            for start in range(
                0, len(awards), INSERT_BATCH_SIZE
            ):
                batch = awards[
                    start:start + INSERT_BATCH_SIZE
                ]

                execute_values(
                    cur,
                    insert_sql,
                    [award_values(a) for a in batch],
                    page_size=1_000,
                )

                inserted += len(batch)

                if (
                    inserted % 20_000 == 0
                    or inserted == len(awards)
                ):
                    print(
                        f"Inserted in transaction: {inserted:,}",
                        flush=True,
                    )

            require(
                inserted == EXPECTED_CANDIDATES,
                "Inserted award count mismatch",
            )

            final_total = count_awards(cur)
            represented, remaining, held_after = (
                historical_controls(cur)
            )

            require(
                final_total == EXPECTED_FINAL,
                f"Final award population mismatch: {final_total:,}",
            )
            require(
                represented == EXPECTED_REPRESENTED,
                f"Historical representation mismatch: {represented:,}",
            )
            require(
                remaining == 0,
                f"Eligible awards remain missing: {remaining:,}",
            )
            require(
                held_after == EXPECTED_HELD,
                f"Held population changed: {held_after:,}",
            )

            print()
            print("PRE-COMMIT ASSERTIONS")
            print(f"Inserted canonical awards: {inserted:,}")
            print(f"Final canonical population: {final_total:,}")
            print(f"Historical awards represented: {represented:,}")
            print(f"Remaining eligible awards: {remaining:,}")
            print(f"Held conflicted awards: {held_after:,}")
            print("Pre-commit validation: PASS", flush=True)

        # The only commit in the entire insertion procedure.
        # Reached only after every assertion has passed.
        conn.commit()
        committed = True

        print()
        print("TRANSACTION: COMMIT COMPLETE", flush=True)

    except Exception as exc:
        if not committed:
            conn.rollback()

        print()
        print("ETL-201O INSERTION FAILED", flush=True)
        print(f"{type(exc).__name__}: {exc}", flush=True)

        if not committed:
            print("Transaction rolled back.", flush=True)

        raise

    finally:
        if not committed:
            conn.rollback()
        conn.close()

    # This verification is independent of the write transaction.
    # If it fails, the prior commit is NOT automatically undone.
    verify_committed_state()

    print()
    print("=" * 72)
    print("ETL-201O: PASS")
    print("HISTORICAL CANONICAL AWARD INSERTION VERIFIED")
    print(f"Elapsed seconds: {perf_counter() - started:.1f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
