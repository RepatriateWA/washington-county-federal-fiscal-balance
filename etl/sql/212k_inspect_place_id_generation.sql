
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212K - PLACE ID AND IDENTITY GENERATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';

\echo ''
\echo '1. PLACE ID COLUMN GENERATION'

SELECT
    column_name,
    data_type,
    is_identity,
    identity_generation,
    column_default
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'place'
  AND column_name = 'place_id';

\echo ''
\echo '2. OWNED SEQUENCE'

SELECT
    pg_get_serial_sequence(
        'procurement.place',
        'place_id'
    ) AS owned_sequence;

\echo ''
\echo '3. SEQUENCES IN PROCUREMENT SCHEMA'

SELECT
    sequence_schema,
    sequence_name,
    data_type,
    start_value,
    increment
FROM information_schema.sequences
WHERE sequence_schema = 'procurement'
ORDER BY sequence_name;

\echo ''
\echo '4. PLACE ID RANGE AND IDENTITY KEY COVERAGE'

SELECT
    COUNT(*) AS places,
    MIN(place_id) AS min_place_id,
    MAX(place_id) AS max_place_id,
    COUNT(place_identity_key) AS keys_present,
    COUNT(*) FILTER (
        WHERE place_identity_key IS NULL
    ) AS keys_missing,
    COUNT(*) FILTER (
        WHERE place_identity_type = 'SOURCE_CONDITION'
    ) AS source_condition_places
FROM procurement.place;

\echo ''
\echo '5. EXISTING IDENTITY KEY EXAMPLES'

SELECT
    place_id,
    country_code,
    state_fips,
    county_fips,
    city_name,
    zip4,
    place_identity_key,
    place_identity_type
FROM procurement.place
WHERE county_fips IS NOT NULL
ORDER BY place_id DESC
LIMIT 15;

\echo ''
\echo '6. PLACE TABLE TRIGGERS'

SELECT
    tgname AS trigger_name,
    pg_get_triggerdef(oid) AS definition
FROM pg_trigger
WHERE tgrelid = 'procurement.place'::regclass
  AND NOT tgisinternal
ORDER BY tgname;

ROLLBACK;

\echo ''
\echo 'ETL-212K COMPLETE - NO DATABASE WRITES'
