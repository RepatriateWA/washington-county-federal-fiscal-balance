
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212E - PROCUREMENT RAW PROVENANCE AND GEOGRAPHY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. SOURCE FILE AND BATCH PROVENANCE'

SELECT
    load_batch_id,
    fiscal_year_start,
    fiscal_year_end,
    source_file,
    source_url,
    file_sha256,
    source_record_count,
    loaded_record_count,
    rejected_record_count,
    load_status,
    notes
FROM procurement.load_batch
WHERE load_batch_id IN (20, 21, 22, 23)
ORDER BY load_batch_id;

\echo ''
\echo '2. RAW JSON TOP-LEVEL KEY INVENTORY'

WITH sampled AS (
    SELECT
        load_batch_id,
        raw_record
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
      AND raw_record IS NOT NULL
    ORDER BY load_batch_id, raw_award_transaction_id
    LIMIT 200
)
SELECT
    s.load_batch_id,
    k.key AS json_key,
    COUNT(*) AS sampled_rows_with_key
FROM sampled s
CROSS JOIN LATERAL jsonb_object_keys(s.raw_record)
    AS k(key)
GROUP BY s.load_batch_id, k.key
ORDER BY s.load_batch_id, k.key;

\echo ''
\echo '3. GEOGRAPHY-RELATED JSON KEYS'

WITH sampled AS (
    SELECT
        load_batch_id,
        raw_record
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
      AND raw_record IS NOT NULL
    ORDER BY load_batch_id, raw_award_transaction_id
    LIMIT 200
)
SELECT
    s.load_batch_id,
    k.key AS json_key,
    COUNT(*) AS sampled_rows_with_key,
    COUNT(*) FILTER (
        WHERE NULLIF(
            BTRIM(s.raw_record ->> k.key), ''
        ) IS NOT NULL
    ) AS nonempty_values,
    LEFT(
        MIN(NULLIF(
            BTRIM(s.raw_record ->> k.key), ''
        )), 100
    ) AS example_value
FROM sampled s
CROSS JOIN LATERAL jsonb_object_keys(s.raw_record)
    AS k(key)
WHERE
    k.key ILIKE '%place%'
    OR k.key ILIKE '%state%'
    OR k.key ILIKE '%county%'
    OR k.key ILIKE '%city%'
    OR k.key ILIKE '%zip%'
    OR k.key ILIKE '%location%'
    OR k.key ILIKE '%performance%'
    OR k.key ILIKE '%fips%'
GROUP BY s.load_batch_id, k.key
ORDER BY s.load_batch_id, k.key;

\echo ''
\echo '4. RAW AND CANONICAL COLUMN INVENTORY'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name IN (
      'raw_award_transaction',
      'award_transaction',
      'award_transaction_observation',
      'place_of_performance'
  )
ORDER BY table_name, ordinal_position;

ROLLBACK;

\echo ''
\echo 'ETL-212E COMPLETE - NO DATABASE WRITES'
