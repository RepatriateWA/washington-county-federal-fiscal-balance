/*
ETL-164
Backfill Batch 7 Assistance Transaction Observation Provenance

Purpose
-------
Restore the missing observation-provenance bridge for USAspending
Assistance load_batch_id = 7.

The canonical assistance transaction model is global: a canonical
transaction may have been created by an earlier or later load batch.
Therefore observation provenance must be represented through:

    raw_award_transaction
        -> award_transaction_observation
        -> award_transaction

The backfill is deterministic on assistance_transaction_unique_key.

Pre-backfill evidence established:
    Batch 7 raw observations                  = 391,015
    Batch 7 existing observation bridges      = 0
    Batch 7 canonical matches                 = 391,015
    Batch 7 unmatched observations            = 0
    Batch 7 distinct raw transaction keys     = 391,015
    Batch 7 distinct canonical transactions   = 391,015

This migration is intentionally fail-closed.
*/

BEGIN;

DO $$
DECLARE
    v_raw_count              bigint;
    v_distinct_raw_keys      bigint;
    v_matched_count          bigint;
    v_distinct_matched       bigint;
    v_unmatched_count        bigint;
    v_existing_bridge_count  bigint;
BEGIN
    /*
    ------------------------------------------------------------------
    PRECONDITION 1
    Confirm the historical Batch 7 raw population has not changed.
    ------------------------------------------------------------------
    */
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_unique_key)
    INTO
        v_raw_count,
        v_distinct_raw_keys
    FROM assistance.raw_award_transaction
    WHERE load_batch_id = 7;

    IF v_raw_count <> 391015 THEN
        RAISE EXCEPTION
            'ETL-164 aborted: Batch 7 raw count expected 391015, found %',
            v_raw_count;
    END IF;

    IF v_distinct_raw_keys <> v_raw_count THEN
        RAISE EXCEPTION
            'ETL-164 aborted: Batch 7 contains duplicate transaction keys. raw=%, distinct_keys=%',
            v_raw_count,
            v_distinct_raw_keys;
    END IF;

    /*
    ------------------------------------------------------------------
    PRECONDITION 2
    Confirm every raw observation resolves deterministically to exactly
    one globally canonical assistance transaction.
    ------------------------------------------------------------------
    */
    SELECT
        COUNT(t.assistance_transaction_id),
        COUNT(DISTINCT t.assistance_transaction_id),
        COUNT(*) FILTER (
            WHERE t.assistance_transaction_id IS NULL
        )
    INTO
        v_matched_count,
        v_distinct_matched,
        v_unmatched_count
    FROM assistance.raw_award_transaction AS raw
    LEFT JOIN assistance.award_transaction AS t
        ON t.assistance_transaction_unique_key =
           raw.assistance_transaction_unique_key
    WHERE raw.load_batch_id = 7;

    IF v_matched_count <> v_raw_count
       OR v_unmatched_count <> 0
       OR v_distinct_matched <> v_raw_count THEN
        RAISE EXCEPTION
            'ETL-164 aborted: Batch 7 canonical resolution failed. raw=%, matched=%, distinct_matched=%, unmatched=%',
            v_raw_count,
            v_matched_count,
            v_distinct_matched,
            v_unmatched_count;
    END IF;

    /*
    ------------------------------------------------------------------
    PRECONDITION 3
    Batch 7 is expected to have no observation bridge rows before this
    historical repair.

    On a rerun, however, a completely populated Batch 7 is acceptable.
    Any partial state is rejected.
    ------------------------------------------------------------------
    */
    SELECT COUNT(*)
    INTO v_existing_bridge_count
    FROM assistance.raw_award_transaction AS raw
    JOIN assistance.award_transaction_observation AS obs
        ON obs.raw_assistance_transaction_id =
           raw.raw_assistance_transaction_id
    WHERE raw.load_batch_id = 7;

    IF v_existing_bridge_count NOT IN (0, v_raw_count) THEN
        RAISE EXCEPTION
            'ETL-164 aborted: Batch 7 observation provenance is partially populated. expected 0 or %, found %',
            v_raw_count,
            v_existing_bridge_count;
    END IF;
END
$$;


/*
----------------------------------------------------------------------
BACKFILL

The UNIQUE constraint on raw_assistance_transaction_id guarantees that
one raw observation cannot map to multiple canonical transactions.

ON CONFLICT makes the operation idempotent.
----------------------------------------------------------------------
*/
INSERT INTO assistance.award_transaction_observation (
    raw_assistance_transaction_id,
    assistance_transaction_id
)
SELECT
    raw.raw_assistance_transaction_id,
    t.assistance_transaction_id
FROM assistance.raw_award_transaction AS raw
JOIN assistance.award_transaction AS t
    ON t.assistance_transaction_unique_key =
       raw.assistance_transaction_unique_key
WHERE raw.load_batch_id = 7
ON CONFLICT (raw_assistance_transaction_id) DO NOTHING;


/*
----------------------------------------------------------------------
POSTCONDITION

Require complete one-to-one provenance coverage after the operation.
----------------------------------------------------------------------
*/
DO $$
DECLARE
    v_raw_count             bigint;
    v_bridge_count          bigint;
    v_distinct_raw_bridge   bigint;
    v_distinct_transaction  bigint;
    v_unbridged_count       bigint;
    v_wrong_mapping_count   bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_raw_count
    FROM assistance.raw_award_transaction
    WHERE load_batch_id = 7;

    SELECT
        COUNT(obs.award_transaction_observation_id),
        COUNT(DISTINCT obs.raw_assistance_transaction_id),
        COUNT(DISTINCT obs.assistance_transaction_id),
        COUNT(*) FILTER (
            WHERE obs.award_transaction_observation_id IS NULL
        )
    INTO
        v_bridge_count,
        v_distinct_raw_bridge,
        v_distinct_transaction,
        v_unbridged_count
    FROM assistance.raw_award_transaction AS raw
    LEFT JOIN assistance.award_transaction_observation AS obs
        ON obs.raw_assistance_transaction_id =
           raw.raw_assistance_transaction_id
    WHERE raw.load_batch_id = 7;

    /*
    Confirm that an existing bridge cannot merely satisfy the UNIQUE
    constraint while pointing at the wrong canonical transaction.
    */
    SELECT COUNT(*)
    INTO v_wrong_mapping_count
    FROM assistance.raw_award_transaction AS raw
    JOIN assistance.award_transaction_observation AS obs
        ON obs.raw_assistance_transaction_id =
           raw.raw_assistance_transaction_id
    JOIN assistance.award_transaction AS expected
        ON expected.assistance_transaction_unique_key =
           raw.assistance_transaction_unique_key
    WHERE raw.load_batch_id = 7
      AND obs.assistance_transaction_id <>
          expected.assistance_transaction_id;

    IF v_bridge_count <> v_raw_count
       OR v_distinct_raw_bridge <> v_raw_count
       OR v_distinct_transaction <> v_raw_count
       OR v_unbridged_count <> 0
       OR v_wrong_mapping_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-164 postcondition failed. raw=%, bridges=%, distinct_raw_bridges=%, distinct_transactions=%, unbridged=%, wrong_mappings=%',
            v_raw_count,
            v_bridge_count,
            v_distinct_raw_bridge,
            v_distinct_transaction,
            v_unbridged_count,
            v_wrong_mapping_count;
    END IF;

    RAISE NOTICE
        'ETL-164 PASS: Batch 7 provenance restored. raw=%, bridges=%, canonical_transactions=%, unbridged=%, wrong_mappings=%',
        v_raw_count,
        v_bridge_count,
        v_distinct_transaction,
        v_unbridged_count,
        v_wrong_mapping_count;
END
$$;

COMMIT;