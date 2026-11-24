
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212F - HISTORICAL PROCUREMENT REPAIR READINESS'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. FULL-BATCH RAW GEOGRAPHIC FIELD COVERAGE'

WITH fields AS (
    SELECT
        load_batch_id,
        raw_award_transaction_id,
        NULLIF(BTRIM(raw_record ->>
            'primary_place_of_performance_state_code'), '')
            AS state_code,
        NULLIF(BTRIM(raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'), '')
            AS county_fips,
        NULLIF(BTRIM(raw_record ->>
            'primary_place_of_performance_county_name'), '')
            AS county_name,
        NULLIF(BTRIM(raw_record ->>
            'primary_place_of_performance_city_name'), '')
            AS city_name,
        NULLIF(BTRIM(raw_record ->>
            'contract_transaction_unique_key'), '')
            AS transaction_key
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(state_code) AS state_present,
    COUNT(*) FILTER (WHERE state_code = 'WA')
        AS state_wa,
    COUNT(county_fips) AS county_fips_present,
    COUNT(*) FILTER (
        WHERE county_fips ~ '^53[0-9]{3}$'
    ) AS valid_wa_county_fips_format,
    COUNT(county_name) AS county_name_present,
    COUNT(city_name) AS city_name_present,
    COUNT(transaction_key) AS transaction_key_present,
    COUNT(DISTINCT transaction_key)
        AS distinct_transaction_keys
FROM fields
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '2. CANONICAL IDENTITY FIELD COVERAGE'

SELECT
    fiscal_year,
    load_batch_id,
    COUNT(*) AS canonical_rows,
    COUNT(usaspending_transaction_id)
        AS transaction_id_present,
    COUNT(DISTINCT usaspending_transaction_id)
        AS distinct_transaction_ids,
    COUNT(source_row_number)
        AS source_row_number_present,
    COUNT(DISTINCT source_row_number)
        AS distinct_source_row_numbers
FROM procurement.award_transaction
WHERE fiscal_year IN (2018, 2019)
GROUP BY fiscal_year, load_batch_id
ORDER BY fiscal_year, load_batch_id;

\echo ''
\echo '3. RAW-TO-CANONICAL SOURCE ROW MATCHES'

WITH matched AS (
    SELECT
        r.load_batch_id,
        r.raw_award_transaction_id,
        t.award_transaction_id,
        t.load_batch_id AS canonical_batch_id
    FROM procurement.raw_award_transaction r
    LEFT JOIN procurement.award_transaction t
      ON t.load_batch_id = r.load_batch_id
     AND t.source_row_number = r.source_row_number
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(award_transaction_id)
        AS same_batch_matches,
    COUNT(*) FILTER (
        WHERE award_transaction_id IS NULL
    ) AS unmatched_raw_rows,
    COUNT(DISTINCT award_transaction_id)
        AS distinct_matched_canonical
FROM matched
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '4. RAW TRANSACTION KEY MATCHES ACROSS ALL BATCHES'

WITH raw_keys AS (
    SELECT
        load_batch_id,
        raw_award_transaction_id,
        NULLIF(BTRIM(raw_record ->>
            'contract_transaction_unique_key'), '')
            AS transaction_key
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
),
matched AS (
    SELECT
        r.load_batch_id,
        r.raw_award_transaction_id,
        r.transaction_key,
        t.award_transaction_id,
        t.load_batch_id AS canonical_batch_id
    FROM raw_keys r
    LEFT JOIN procurement.award_transaction t
      ON t.usaspending_transaction_id = r.transaction_key
)
SELECT
    load_batch_id,
    COUNT(DISTINCT raw_award_transaction_id)
        AS raw_rows,
    COUNT(DISTINCT raw_award_transaction_id)
        FILTER (WHERE award_transaction_id IS NOT NULL)
        AS raw_rows_with_key_match,
    COUNT(DISTINCT raw_award_transaction_id)
        FILTER (WHERE award_transaction_id IS NULL)
        AS raw_rows_without_key_match,
    COUNT(DISTINCT award_transaction_id)
        AS matched_canonical_rows
FROM matched
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '5. CANONICAL KEY MATCH BATCH DISTRIBUTION'

WITH raw_keys AS (
    SELECT
        load_batch_id,
        NULLIF(BTRIM(raw_record ->>
            'contract_transaction_unique_key'), '')
            AS transaction_key
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    r.load_batch_id AS raw_batch_id,
    t.load_batch_id AS canonical_batch_id,
    COUNT(*) AS key_matches
FROM raw_keys r
JOIN procurement.award_transaction t
  ON t.usaspending_transaction_id = r.transaction_key
GROUP BY r.load_batch_id, t.load_batch_id
ORDER BY r.load_batch_id, t.load_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-212F COMPLETE - NO DATABASE WRITES'
