
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213F v0.1 - HISTORICAL RAW AGENCY EVIDENCE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '1. Agency-related raw JSON keys'

WITH sample AS (
    SELECT raw_record
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
    ORDER BY raw_award_transaction_id
    LIMIT 200
)
SELECT
    key,
    COUNT(*) AS sample_occurrences
FROM sample
CROSS JOIN LATERAL jsonb_object_keys(raw_record) AS key
WHERE key ~* 'agency|subagency|department'
GROUP BY key
ORDER BY key;

\echo ''
\echo '2. Sample missing-agency historical transactions'

WITH missing AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.federal_action_obligation,
        r.raw_record
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id =
         r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id =
         o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    WHERE r.load_batch_id IN (22, 23)
      AND a.funding_agency_id IS NULL
    ORDER BY r.raw_award_transaction_id
    LIMIT 12
)
SELECT
    fiscal_year,
    award_transaction_id,
    federal_action_obligation,
    (
        SELECT jsonb_object_agg(key, value)
        FROM jsonb_each(raw_record)
        WHERE key ~* 'agency|subagency|department'
    ) AS raw_agency_fields
FROM missing
ORDER BY fiscal_year, award_transaction_id;

ROLLBACK;

\echo ''
\echo 'ETL-213F v0.1 COMPLETE - NO DATABASE WRITES'
