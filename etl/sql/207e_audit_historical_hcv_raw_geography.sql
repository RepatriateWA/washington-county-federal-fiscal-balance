\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-207E - HISTORICAL HCV RAW GEOGRAPHY AUDIT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo '=== 1. RAW-TO-CERTIFIED RECONCILIATION ==='

WITH hcv AS (
    SELECT
        load_batch_id,
        source_row_number,
        assistance_transaction_unique_key,
        federal_action_obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE TRIM(cfda_number) = '14.871'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      )
)
SELECT
    h.load_batch_id,
    COUNT(*) AS certified_transactions,
    COUNT(r.raw_assistance_transaction_id) AS raw_matches,
    COUNT(*) FILTER (
        WHERE r.raw_assistance_transaction_id IS NULL
    ) AS missing_raw_matches,
    COUNT(*) FILTER (
        WHERE r.raw_assistance_transaction_id IS NOT NULL
          AND r.assistance_transaction_unique_key
              IS DISTINCT FROM h.assistance_transaction_unique_key
    ) AS transaction_key_mismatches,
    SUM(h.federal_action_obligation) AS certified_net_obligations
FROM hcv h
LEFT JOIN assistance.raw_award_transaction r
    ON r.load_batch_id = h.load_batch_id
   AND r.source_row_number = h.source_row_number
GROUP BY h.load_batch_id
ORDER BY h.load_batch_id;


\echo '=== 2. GEOGRAPHIC AND RECIPIENT JSON FIELD DISCOVERY ==='

WITH hcv AS (
    SELECT
        load_batch_id,
        source_row_number
    FROM analysis.v_certified_assistance_ledger
    WHERE TRIM(cfda_number) = '14.871'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      )
),
keys AS (
    SELECT
        r.load_batch_id,
        k.key
    FROM hcv h
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = h.load_batch_id
     AND r.source_row_number = h.source_row_number
    CROSS JOIN LATERAL jsonb_object_keys(r.raw_record) AS k(key)
)
SELECT
    load_batch_id,
    key AS source_field,
    COUNT(*) AS records_containing_field
FROM keys
WHERE key ~* '(state|county|recipient|performance|location|place|agency)'
GROUP BY load_batch_id, key
ORDER BY load_batch_id, key;


\echo '=== 3. RAW JSON GEOGRAPHY VALUE PROFILE ==='

WITH hcv AS (
    SELECT
        load_batch_id,
        source_row_number
    FROM analysis.v_certified_assistance_ledger
    WHERE TRIM(cfda_number) = '14.871'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      )
),
fields AS (
    SELECT
        r.load_batch_id,
        k.key,
        NULLIF(BTRIM(r.raw_record ->> k.key), '') AS field_value
    FROM hcv h
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = h.load_batch_id
     AND r.source_row_number = h.source_row_number
    CROSS JOIN LATERAL jsonb_object_keys(r.raw_record) AS k(key)
    WHERE k.key ~* '(state|county|recipient|performance|location|place|agency)'
)
SELECT
    load_batch_id,
    key AS source_field,
    COUNT(*) AS records,
    COUNT(field_value) AS nonblank_values,
    COUNT(DISTINCT field_value) AS distinct_values,
    LEFT(MIN(field_value), 100) AS example_min_value,
    LEFT(MAX(field_value), 100) AS example_max_value
FROM fields
GROUP BY load_batch_id, key
ORDER BY load_batch_id, key;

COMMIT;

\echo 'ETL-207E READ-ONLY AUDIT COMPLETE'