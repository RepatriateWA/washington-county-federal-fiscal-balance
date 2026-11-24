\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221N - HISTORICAL JSON GEOGRAPHY PROFILE'
\echo 'READ ONLY - FY2018-FY2019'

\echo ''
\echo '1. HISTORICAL SOURCE BATCH METADATA'

SELECT
    load_batch_id,
    fiscal_year_start,
    fiscal_year_end,
    source_file,
    source_record_count,
    loaded_record_count,
    rejected_record_count,
    load_status,
    notes
FROM procurement.load_batch
WHERE load_batch_id IN (20, 21)
ORDER BY load_batch_id;

\echo ''
\echo '2. GEOGRAPHY AND RECIPIENT JSON KEY INVENTORY'

WITH keys AS (
    SELECT
        r.load_batch_id,
        k.key
    FROM assistance.raw_award_transaction r
    CROSS JOIN LATERAL
        jsonb_object_keys(r.raw_record) AS k(key)
    WHERE r.load_batch_id IN (20, 21)
)
SELECT
    load_batch_id,
    key,
    COUNT(*) AS raw_rows_with_key
FROM keys
WHERE key ~* '(place|state|county|zip|location|recipient)'
GROUP BY load_batch_id, key
ORDER BY load_batch_id, key;

\echo ''
\echo '3. JSON PAYLOAD STRUCTURE'

SELECT
    load_batch_id,
    jsonb_typeof(raw_record) AS payload_type,
    COUNT(*) AS raw_rows
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '4. SAMPLE NONEMPTY GEOGRAPHIC JSON VALUES'

WITH candidate_fields AS (
    SELECT
        r.load_batch_id,
        r.source_row_number,
        e.key,
        LEFT(e.value, 120) AS sample_value,
        ROW_NUMBER() OVER (
            PARTITION BY r.load_batch_id, e.key
            ORDER BY r.source_row_number
        ) AS sample_rank
    FROM assistance.raw_award_transaction r
    CROSS JOIN LATERAL
        jsonb_each_text(r.raw_record) AS e(key, value)
    WHERE r.load_batch_id IN (20, 21)
      AND e.key ~* '(place.*state|place.*county|place.*zip|recipient.*state|recipient.*county)'
      AND NULLIF(BTRIM(e.value), '') IS NOT NULL
)
SELECT
    load_batch_id,
    source_row_number,
    key,
    sample_value
FROM candidate_fields
WHERE sample_rank <= 2
ORDER BY load_batch_id, key, sample_rank;

ROLLBACK;