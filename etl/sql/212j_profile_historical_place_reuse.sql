
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212J v0.2 - OPTIMIZED HISTORICAL PLACE REUSE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '60s';
SET LOCAL max_parallel_workers_per_gather = 0;

\echo ''
\echo '1. SOURCE PLACE IDENTITY COUNTS'

WITH source_places AS MATERIALIZED (
    SELECT DISTINCT
        r.load_batch_id,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_country_code'), '')
            AS country_code,
        NULLIF(BTRIM(r.raw_record ->>
            'prime_award_transaction_place_of_performance_state_fips_code'), '')
            AS state_fips,
        NULLIF(BTRIM(r.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'), '')
            AS county_fips,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_city_name'), '')
            AS city_name,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_zip_4'), '')
            AS zip4
    FROM procurement.raw_award_transaction r
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    load_batch_id,
    COUNT(*) AS distinct_source_places,
    COUNT(*) FILTER (WHERE city_name IS NULL)
        AS places_without_city,
    COUNT(*) FILTER (WHERE zip4 IS NULL)
        AS places_without_zip
FROM source_places
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '2. EXISTING PLACE REUSE BY BATCH'

WITH source_places AS MATERIALIZED (
    SELECT DISTINCT
        r.load_batch_id,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_country_code'), '')
            AS country_code,
        NULLIF(BTRIM(r.raw_record ->>
            'prime_award_transaction_place_of_performance_state_fips_code'), '')
            AS state_fips,
        NULLIF(BTRIM(r.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'), '')
            AS county_fips,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_city_name'), '')
            AS city_name,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_zip_4'), '')
            AS zip4
    FROM procurement.raw_award_transaction r
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    s.load_batch_id,
    COUNT(*) AS distinct_source_places,
    COUNT(p.place_id) AS existing_places,
    COUNT(*) FILTER (WHERE p.place_id IS NULL)
        AS new_places_required
FROM source_places s
LEFT JOIN procurement.place p
  ON p.country_code = s.country_code
 AND p.state_fips = s.state_fips
 AND p.county_fips = s.county_fips
 AND p.zip4 = s.zip4
 AND p.city_name IS NOT DISTINCT FROM s.city_name
GROUP BY s.load_batch_id
ORDER BY s.load_batch_id;

\echo ''
\echo '3. UNIQUE NEW PLACES ACROSS BOTH YEARS'

WITH source_places AS MATERIALIZED (
    SELECT DISTINCT
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_country_code'), '')
            AS country_code,
        NULLIF(BTRIM(r.raw_record ->>
            'prime_award_transaction_place_of_performance_state_fips_code'), '')
            AS state_fips,
        NULLIF(BTRIM(r.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'), '')
            AS county_fips,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_city_name'), '')
            AS city_name,
        NULLIF(BTRIM(r.raw_record ->>
            'primary_place_of_performance_zip_4'), '')
            AS zip4
    FROM procurement.raw_award_transaction r
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    COUNT(*) AS unique_historical_places,
    COUNT(p.place_id) AS existing_places,
    COUNT(*) FILTER (WHERE p.place_id IS NULL)
        AS new_places_required
FROM source_places s
LEFT JOIN procurement.place p
  ON p.country_code = s.country_code
 AND p.state_fips = s.state_fips
 AND p.county_fips = s.county_fips
 AND p.zip4 = s.zip4
 AND p.city_name IS NOT DISTINCT FROM s.city_name;

ROLLBACK;

\echo ''
\echo 'ETL-212J v0.2 COMPLETE - NO DATABASE WRITES'
