
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212G - HISTORICAL PROCUREMENT COUNTY VALIDATION'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. COUNTY REGISTRY COLUMN INVENTORY'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'county_registry'
ORDER BY ordinal_position;

\echo ''
\echo '2. SOURCE COUNTY FIPS DISTRIBUTION'

WITH source_rows AS (
    SELECT
        load_batch_id,
        raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'
            AS county_fips
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(DISTINCT county_fips) AS distinct_county_fips,
    COUNT(*) FILTER (
        WHERE county_fips !~ '^53[0-9]{3}$'
    ) AS invalid_wa_fips_format
FROM source_rows
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '3. SOURCE COUNTY FIPS VS REFERENCE REGISTRY'

WITH source_counties AS (
    SELECT
        load_batch_id,
        raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'
            AS county_fips,
        COUNT(*) AS transactions
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
    GROUP BY
        load_batch_id,
        raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'
)
SELECT
    s.load_batch_id,
    COUNT(*) AS distinct_source_counties,
    SUM(s.transactions) AS source_rows,
    COUNT(c.county_id) AS matched_registry_counties,
    COALESCE(
        SUM(s.transactions) FILTER (
            WHERE c.county_id IS NULL
        ), 0
    ) AS unmatched_source_rows
FROM source_counties s
LEFT JOIN reference.county_registry c
  ON c.full_fips = s.county_fips
GROUP BY s.load_batch_id
ORDER BY s.load_batch_id;

\echo ''
\echo '4. PREVIOUSLY LINKED TRANSACTION GEOGRAPHY CONFLICTS'

WITH source_rows AS (
    SELECT
        r.load_batch_id,
        r.raw_award_transaction_id,
        r.raw_record ->>
            'contract_transaction_unique_key'
            AS transaction_key,
        r.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'
            AS raw_county_fips
    FROM procurement.raw_award_transaction r
    WHERE r.load_batch_id IN (22, 23)
),
matched AS (
    SELECT
        s.load_batch_id,
        s.raw_award_transaction_id,
        s.raw_county_fips,
        t.award_transaction_id,
        t.load_batch_id AS canonical_batch_id,
        p.county_id,
        c.full_fips AS linked_county_fips
    FROM source_rows s
    JOIN procurement.award_transaction t
      ON t.usaspending_transaction_id = s.transaction_key
    LEFT JOIN procurement.place_of_performance p
      ON p.award_transaction_id = t.award_transaction_id
    LEFT JOIN reference.county_registry c
      ON c.county_id = p.county_id
)
SELECT
    load_batch_id,
    canonical_batch_id,
    COUNT(*) AS observations,
    COUNT(*) FILTER (
        WHERE county_id IS NOT NULL
    ) AS already_county_linked,
    COUNT(*) FILTER (
        WHERE county_id IS NOT NULL
          AND linked_county_fips = raw_county_fips
    ) AS matching_existing_counties,
    COUNT(*) FILTER (
        WHERE county_id IS NOT NULL
          AND linked_county_fips IS DISTINCT FROM raw_county_fips
    ) AS conflicting_existing_counties
FROM matched
GROUP BY load_batch_id, canonical_batch_id
ORDER BY load_batch_id, canonical_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-212G COMPLETE - NO DATABASE WRITES'
