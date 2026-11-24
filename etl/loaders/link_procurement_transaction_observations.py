"""ETL-202B.9E: inspect or apply procurement raw-to-canonical provenance links.

Default mode is READ ONLY. --apply writes links, but must NOT be used until
migration and canonical normalization have been separately approved/completed.
Requires an explicit completed procurement --load-batch-id.
"""
from __future__ import annotations

import argparse
from etl.common.db import get_connection

# Both identifiers are official USAspending contract source keys.
TX_KEY = "contract_transaction_unique_key"
AWARD_KEY = "contract_award_unique_key"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-batch-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="WRITE links (requires prior authorization)")
    args = parser.parse_args()
    if args.load_batch_id <= 0:
        parser.error("--load-batch-id must be positive")

    conn = get_connection()
    try:
        conn.set_session(readonly=not args.apply, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lb.load_status, COUNT(r.raw_award_transaction_id)
                FROM procurement.load_batch lb
                LEFT JOIN procurement.raw_award_transaction r
                    ON r.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY lb.load_status
            """, (args.load_batch_id,))
            batch = cur.fetchone()
            if batch is None or batch[0] not in ('COMPLETED', 'COMPLETED_WITH_REJECTIONS') or batch[1] == 0:
                raise ValueError("Batch must exist, be completed, and contain raw observations")
            print(f"Batch {args.load_batch_id}: {batch[1]:,} raw observations")

            # Match by the authoritative transaction key, not by load batch.
            # Check award identity independently to prevent a false association.
            cur.execute("""
                SELECT
                    COUNT(*) AS raw_count,
                    COUNT(*) FILTER (WHERE NULLIF(BTRIM(r.raw_record->>%s), '') IS NULL) AS missing_key,
                    COUNT(*) FILTER (WHERE tx.award_transaction_id IS NULL) AS missing_canonical,
                    COUNT(*) FILTER (
                        WHERE tx.award_transaction_id IS NOT NULL
                          AND aw.generated_unique_award_id IS DISTINCT FROM r.raw_record->>%s
                    ) AS award_key_mismatch,
                    COUNT(*) FILTER (WHERE obs.raw_award_transaction_id IS NOT NULL) AS already_linked,
                    COUNT(*) FILTER (
                        WHERE obs.raw_award_transaction_id IS NOT NULL
                          AND obs.award_transaction_id IS DISTINCT FROM tx.award_transaction_id
                    ) AS conflicting_link
                FROM procurement.raw_award_transaction r
                LEFT JOIN procurement.award_transaction tx
                  ON tx.usaspending_transaction_id = r.raw_record->>%s
                LEFT JOIN procurement.award aw ON aw.award_id = tx.award_id
                LEFT JOIN procurement.award_transaction_observation obs
                  ON obs.raw_award_transaction_id = r.raw_award_transaction_id
                WHERE r.load_batch_id = %s
            """, (TX_KEY, AWARD_KEY, TX_KEY, args.load_batch_id))
            raw_count, missing_key, missing_canonical, mismatch, already_linked, conflict = cur.fetchone()
            print(f"Missing source transaction keys: {missing_key:,}")
            print(f"Missing canonical transactions: {missing_canonical:,}")
            print(f"Award-key mismatches: {mismatch:,}")
            print(f"Already linked: {already_linked:,}")
            print(f"Conflicting existing links: {conflict:,}")
            if any((missing_key, missing_canonical, mismatch, conflict)):
                raise ValueError("Linkage validation failed; no changes committed")

            if args.apply:
                cur.execute("""
                    INSERT INTO procurement.award_transaction_observation
                        (raw_award_transaction_id, award_transaction_id)
                    SELECT r.raw_award_transaction_id, tx.award_transaction_id
                    FROM procurement.raw_award_transaction r
                    JOIN procurement.award_transaction tx
                      ON tx.usaspending_transaction_id = r.raw_record->>%s
                    JOIN procurement.award aw ON aw.award_id = tx.award_id
                    WHERE r.load_batch_id = %s
                      AND aw.generated_unique_award_id = r.raw_record->>%s
                    ON CONFLICT (raw_award_transaction_id) DO NOTHING
                """, (TX_KEY, args.load_batch_id, AWARD_KEY))
                print(f"New provenance links inserted: {cur.rowcount:,}")
                cur.execute("""
                    SELECT COUNT(*)
                    FROM procurement.raw_award_transaction r
                    LEFT JOIN procurement.award_transaction_observation o
                      ON o.raw_award_transaction_id = r.raw_award_transaction_id
                    WHERE r.load_batch_id = %s AND o.raw_award_transaction_id IS NULL
                """, (args.load_batch_id,))
                if cur.fetchone()[0]:
                    raise ValueError("Unlinked raw observations remain; rolling back")
                conn.commit()
                print("Linkage validation PASS; committed")
            else:
                conn.rollback()
                print("READ ONLY: no changes made; linkage appears eligible")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
