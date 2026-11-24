
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212Q v0.1 - HISTORICAL PROCUREMENT GEOGRAPHY PREFLIGHT'
\echo 'FY2018-FY2019 - STRICTLY READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '120s';
SET LOCAL max_parallel_workers_per_gather = 0;

\echo ''
\echo '1. RAW SOURCE COVERAGE'

SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(DISTINCT raw_record ->>
        'contract_transaction_unique_key') AS distinct_transaction_keys
FROM procurement.raw_award_transaction
WHERE load_batch_id IN (22, 23)
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '2. NORMALIZED GEOGRAPHIC IDENTITY COVERAGE'

WITH extracted AS MATERIALIZED (
    SELECT
        raw.load_batch_id,

        UPPER(NULLIF(BTRIM(
            raw.raw_record ->>
            'primary_place_of_performance_country_code'
        ), '')) AS country_code,

        UPPER(NULLIF(BTRIM(
            raw.raw_record ->>
            'primary_place_of_performance_state_code'
        ), '')) AS state_code,

        NULLIF(BTRIM(
            raw.raw_record ->>
            'prime_award_transaction_place_of_performance_state_fips_code'
        ), '') AS state_fips,

        NULLIF(BTRIM(
            raw.raw_record ->>
            'prime_award_transaction_place_of_performance_county_fips_code'
        ), '') AS county_fips,

        UPPER(NULLIF(
            REGEXP_REPLACE(
                BTRIM(raw.raw_record ->>
                    'primary_place_of_performance_city_name'),
                '\s+', ' ', 'g'
            ), ''
        )) AS city_name,

        NULLIF(
            REGEXP_REPLACE(
                BTRIM(raw.raw_record ->>
                    'primary_place_of_performance_zip_4'),
                '[^0-9]', '', 'g'
            ), ''
        ) AS zip4

    FROM procurement.raw_award_transaction AS raw
    WHERE raw.load_batch_id IN (22, 23)
),
cleaned AS MATERIALIZED (
    SELECT
        load_batch_id,

        CASE
            WHEN country_code IN
                ('NULL','NONE','N/A','NA','NAN')
            THEN NULL ELSE country_code
        END AS country_code,

        CASE
            WHEN state_code IN
                ('NULL','NONE','N/A','NA','NAN')
            THEN NULL ELSE state_code
        END AS state_code,

        CASE
            WHEN state_fips ~ '^[0-9]{2}$'
            THEN state_fips ELSE NULL
        END AS state_fips,

        CASE
            WHEN county_fips ~ '^[0-9]{5}$'
            THEN county_fips ELSE NULL
        END AS county_fips,

        CASE
            WHEN city_name IN
                ('NULL','NONE','N/A','NA','NAN')
            THEN NULL ELSE city_name
        END AS city_name,

        CASE
            WHEN zip4 ~ '^[0-9]{5}([0-9]{4})?$'
            THEN zip4 ELSE NULL
        END AS zip4

    FROM extracted
),
identities AS MATERIALIZED (
    SELECT DISTINCT
        country_code,
        state_fips,
        county_fips,
        city_name,
        zip4
    FROM cleaned
),
resolved AS MATERIALIZED (
    SELECT
        i.*,
        p.place_id
    FROM identities AS i
    LEFT JOIN procurement.place AS p
      ON p.country_code IS NOT DISTINCT FROM i.country_code
     AND p.state_fips IS NOT DISTINCT FROM i.state_fips
     AND p.county_fips IS NOT DISTINCT FROM i.county_fips
     AND p.city_name IS NOT DISTINCT FROM i.city_name
     AND p.zip4 IS NOT DISTINCT FROM i.zip4
)
SELECT
    COUNT(*) AS normalized_unique_identities,
    COUNT(place_id) AS existing_places,
    COUNT(*) FILTER (
        WHERE place_id IS NULL
    ) AS new_places_required,
    COUNT(*) FILTER (
        WHERE country_code IS NULL
           OR state_fips IS NULL
           OR county_fips IS NULL
    ) AS incomplete_geographic_identities,
    COUNT(*) FILTER (
        WHERE city_name IS NULL
    ) AS identities_without_city,
    COUNT(*) FILTER (
        WHERE zip4 IS NULL
    ) AS identities_without_valid_zip
FROM resolved;

\echo ''
\echo '3. RAW ZIP VALIDATION BY BATCH'

WITH z AS MATERIALIZED (
    SELECT
        load_batch_id,
        NULLIF(
            REGEXP_REPLACE(
                BTRIM(raw_record ->>
                    'primary_place_of_performance_zip_4'),
                '[^0-9]', '', 'g'
            ), ''
        ) AS cleaned_zip
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(*) FILTER (
        WHERE cleaned_zip IS NULL
    ) AS missing_zip,
    COUNT(*) FILTER (
        WHERE cleaned_zip IS NOT NULL
          AND cleaned_zip !~ '^[0-9]{5}([0-9]{4})?$'
    ) AS invalid_zip,
    COUNT(*) FILTER (
        WHERE LENGTH(cleaned_zip) = 5
    ) AS five_digit_zip,
    COUNT(*) FILTER (
        WHERE LENGTH(cleaned_zip) = 9
    ) AS nine_digit_zip
FROM z
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '4. OBSERVATION TABLE CONSTRAINTS'

SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.conrelid =
    'procurement.award_transaction_observation'::regclass
ORDER BY con.conname;

\echo ''
\echo '5. OBSERVATION TABLE COLUMNS'

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'award_transaction_observation'
ORDER BY ordinal_position;

\echo ''
\echo '6. OBSERVATION COVERAGE FOR HISTORICAL RAW BATCHES'

SELECT
    raw.load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(obs.raw_award_transaction_id)
        AS existing_observation_links,
    COUNT(*) FILTER (
        WHERE obs.raw_award_transaction_id IS NULL
    ) AS missing_observation_links
FROM procurement.raw_award_transaction AS raw
LEFT JOIN procurement.award_transaction_observation AS obs
  ON obs.raw_award_transaction_id =
     raw.raw_award_transaction_id
WHERE raw.load_batch_id IN (22, 23)
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-212Q v0.1 COMPLETE - NO DATABASE WRITES'
