/*
ETL-165
Create Assistance Observation-Grain Analytical Ledger

Purpose
-------
Provide a batch-observation analytical view for USAspending Assistance
without changing the semantics of the canonical fiscal ledger.

Canonical grain:
    analysis.v_certified_assistance_ledger
    one row per canonical assistance transaction

Observation grain:
    analysis.v_assistance_transaction_observation_ledger
    one row per raw assistance observation

This separation prevents cross-batch re-observations from becoming
additive fiscal spending while allowing batch certification to operate
on the complete raw observation universe.

The observation bridge is:

    raw_award_transaction
        -> award_transaction_observation
        -> award_transaction
        -> v_certified_assistance_ledger

Important semantics
-------------------
observation_load_batch_id:
    Batch in which this raw source observation was received.

observation_source_row_number:
    Source row number within that observation batch.

canonical_load_batch_id:
    Batch associated with creation of the globally canonical transaction.

These meanings must remain distinct.
*/

BEGIN;

CREATE OR REPLACE VIEW analysis.v_assistance_transaction_observation_ledger AS
SELECT
    raw.raw_assistance_transaction_id,

    raw.load_batch_id
        AS observation_load_batch_id,

    raw.source_row_number
        AS observation_source_row_number,

    raw.assistance_transaction_unique_key
        AS observation_assistance_transaction_unique_key,

    obs.award_transaction_observation_id,

    obs.assistance_transaction_id
        AS observed_assistance_transaction_id,

    ledger.load_batch_id
        AS canonical_load_batch_id,

    ledger.source_row_number
        AS canonical_source_row_number,

    ledger.*
FROM assistance.raw_award_transaction AS raw
JOIN assistance.award_transaction_observation AS obs
    ON obs.raw_assistance_transaction_id =
       raw.raw_assistance_transaction_id
JOIN analysis.v_certified_assistance_ledger AS ledger
    ON ledger.assistance_transaction_id =
       obs.assistance_transaction_id;


/*
----------------------------------------------------------------------
VALIDATION

Require every raw observation to appear exactly once in the new view.
----------------------------------------------------------------------
*/
DO $$
DECLARE
    v_raw_count          bigint;
    v_view_count         bigint;
    v_distinct_raw_count bigint;
    v_missing_count      bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_raw_count
    FROM assistance.raw_award_transaction;

    SELECT
        COUNT(*),
        COUNT(DISTINCT raw_assistance_transaction_id)
    INTO
        v_view_count,
        v_distinct_raw_count
    FROM analysis.v_assistance_transaction_observation_ledger;

    SELECT COUNT(*)
    INTO v_missing_count
    FROM assistance.raw_award_transaction AS raw
    LEFT JOIN analysis.v_assistance_transaction_observation_ledger AS v
        ON v.raw_assistance_transaction_id =
           raw.raw_assistance_transaction_id
    WHERE v.raw_assistance_transaction_id IS NULL;

    IF v_view_count <> v_raw_count
       OR v_distinct_raw_count <> v_raw_count
       OR v_missing_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-165 validation failed. raw=%, view=%, distinct_raw=%, missing=%',
            v_raw_count,
            v_view_count,
            v_distinct_raw_count,
            v_missing_count;
    END IF;

    RAISE NOTICE
        'ETL-165 PASS: observation ledger complete. raw=%, view=%, distinct_raw=%, missing=%',
        v_raw_count,
        v_view_count,
        v_distinct_raw_count,
        v_missing_count;
END
$$;

COMMIT;