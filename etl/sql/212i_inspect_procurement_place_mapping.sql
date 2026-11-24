
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212I - NORMALIZED PLACE MAPPING READINESS'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. NORMALIZED PLACE TABLE COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'place'
ORDER BY ordinal_position;

\echo ''
\echo '2. NORMALIZED PLACE CONSTRAINTS'

SELECT
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'procurement.place'::regclass
ORDER BY contype, conname;

\echo ''
\echo '3. NORMALIZED PLACE INDEXES'

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'procurement'
  AND tablename = 'place'
ORDER BY indexname;

\echo ''
\echo '4. SAMPLE NORMALIZED PLACE RECORDS'

SELECT *
FROM procurement.place
ORDER BY place_id
LIMIT 12;

\echo ''
\echo '5. HISTORICAL SOURCE GEOGRAPHY COMBINATIONS'

WITH source_geography AS (
    SELECT
        r.load_batch_id,
        r.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'
            AS county_fips,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_city_name'), '')
            AS city_name,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_zip_4'), '')
            AS zip_code
    FROM procurement.raw_award_transaction r
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(DISTINCT county_fips) AS counties,
    COUNT(DISTINCT (county_fips, city_name))
        AS county_city_combinations,
    COUNT(DISTINCT (county_fips, city_name, zip_code))
        AS county_city_zip_combinations,
    COUNT(*) FILTER (WHERE city_name IS NULL)
        AS missing_city,
    COUNT(*) FILTER (WHERE zip_code IS NULL)
        AS missing_zip
FROM source_geography
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '6. CURRENT PLACE LINK CARDINALITY'

SELECT
    COUNT(*) AS linked_transactions,
    COUNT(DISTINCT place_id) AS distinct_places,
    COUNT(*) FILTER (WHERE place_id IS NULL)
        AS missing_place_id
FROM procurement.place_of_performance;

ROLLBACK;

\echo ''
\echo 'ETL-212I COMPLETE - NO DATABASE WRITES'
