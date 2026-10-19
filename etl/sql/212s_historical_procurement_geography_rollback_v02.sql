
\set ON_ERROR_STOP on
\pset pager off
\timing on

\echo '============================================================'
\echo 'ETL-212S v0.1 - PROCUREMENT GEOGRAPHY REPAIR'
\echo 'FY2018-FY2019 - ROLLBACK ONLY'
\echo '============================================================'

BEGIN;

SET LOCAL statement_timeout = '300s';
SET LOCAL lock_timeout = '15s';
SET LOCAL max_parallel_workers_per_gather = 0;

-- Prevent simultaneous changes to the three destination tables.
LOCK TABLE
    procurement.place,
    procurement.award_transaction_observation,
    procurement.place_of_performance
IN SHARE ROW EXCLUSIVE MODE;

\echo '1. Building normalized historical observations'

CREATE TEMP TABLE tmp_212s_raw ON COMMIT DROP AS
WITH extracted AS (
    SELECT
        r.raw_award_transaction_id,
        r.load_batch_id,
        NULLIF(BTRIM(r.raw_record ->> 'contract_transaction_unique_key'), '')
            AS transaction_key,
        UPPER(NULLIF(BTRIM(r.raw_record ->> 'primary_place_of_performance_country_code'), ''))
            AS country_code,
        UPPER(NULLIF(BTRIM(r.raw_record ->> 'primary_place_of_performance_country_name'), ''))
            AS country_name,
        UPPER(NULLIF(BTRIM(r.raw_record ->> 'primary_place_of_performance_state_code'), ''))
            AS state_code,
        UPPER(NULLIF(BTRIM(r.raw_record ->> 'primary_place_of_performance_state_name'), ''))
            AS state_name,
        NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_state_fips_code'), '')
            AS state_fips,
        UPPER(NULLIF(BTRIM(r.raw_record ->> 'primary_place_of_performance_county_name'), ''))
            AS county_name,
        NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_county_fips_code'), '')
            AS county_fips,
        UPPER(NULLIF(
            REGEXP_REPLACE(
                BTRIM(r.raw_record ->> 'primary_place_of_performance_city_name'),
                '\s+', ' ', 'g'), ''))
            AS city_name,
        NULLIF(
            REGEXP_REPLACE(
                BTRIM(r.raw_record ->> 'primary_place_of_performance_zip_4'),
                '[^0-9]', '', 'g'), '')
            AS zip4,
        UPPER(NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_cd_current'), ''))
            AS cd_current,
        UPPER(NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_cd_original'), ''))
            AS cd_original
    FROM procurement.raw_award_transaction r
    WHERE r.load_batch_id IN (22, 23)
),
cleaned AS (
    SELECT
        *,
        CASE WHEN country_code IN
            ('NULL','NONE','N/A','NA','NAN')
            THEN NULL ELSE country_code END AS clean_country,
        CASE WHEN state_code IN
            ('NULL','NONE','N/A','NA','NAN')
            THEN NULL ELSE state_code END AS clean_state,
        CASE WHEN county_name IN
            ('NULL','NONE','N/A','NA','NAN')
            THEN NULL ELSE county_name END AS clean_county_name,
        CASE WHEN city_name IN
            ('NULL','NONE','N/A','NA','NAN')
            THEN NULL ELSE city_name END AS clean_city,
        CASE WHEN zip4 ~ '^[0-9]{5}([0-9]{4})?$'
            THEN zip4 ELSE NULL END AS clean_zip
    FROM extracted
)
SELECT
    raw_award_transaction_id,
    load_batch_id,
    transaction_key,
    clean_country AS country_code,
    CASE WHEN country_name IN
        ('NULL','NONE','N/A','NA','NAN')
        THEN NULL ELSE country_name END AS country_name,
    clean_state AS state_code,
    CASE WHEN state_name IN
        ('NULL','NONE','N/A','NA','NAN')
        THEN NULL ELSE state_name END AS state_name,
    CASE WHEN state_fips ~ '^[0-9]{2}$'
        THEN state_fips ELSE NULL END AS state_fips,
    clean_county_name AS county_name,
    CASE WHEN county_fips ~ '^[0-9]{5}$'
        THEN county_fips ELSE NULL END AS county_fips,
    clean_city AS city_name,
    clean_zip AS zip4,
    CASE WHEN cd_current ~ '^[A-Z]{2}-(AL|[0-9]{1,2})$'
        THEN cd_current ELSE NULL END AS cd_current,
    CASE WHEN cd_original ~ '^[A-Z]{2}-(AL|[0-9]{1,2})$'
        THEN cd_original ELSE NULL END AS cd_original
FROM cleaned;

CREATE INDEX ON tmp_212s_raw (transaction_key);

\echo '2. Resolving canonical transactions'

CREATE TEMP TABLE tmp_212s_tx ON COMMIT DROP AS
SELECT
    r.*,
    a.award_transaction_id
FROM tmp_212s_raw r
JOIN procurement.award_transaction a
  ON a.usaspending_transaction_id = r.transaction_key;

CREATE UNIQUE INDEX ON tmp_212s_tx (raw_award_transaction_id);
ANALYZE tmp_212s_raw;
ANALYZE tmp_212s_tx;

CREATE UNIQUE INDEX ON tmp_212s_tx (award_transaction_id);

\echo '3. Building distinct canonical place candidates'

CREATE TEMP TABLE tmp_212s_places ON COMMIT DROP AS
SELECT
    country_code,
    MAX(country_name) AS country_name,
    MAX(state_code) AS state_code,
    MAX(state_name) AS state_name,
    state_fips,
    MAX(county_name) AS county_name,
    county_fips,
    city_name,
    zip4,
    MAX(cd_current) AS cd_current,
    MAX(cd_original) AS cd_original
FROM tmp_212s_tx
GROUP BY
    country_code, state_fips, county_fips,
    city_name, zip4;
ALTER TABLE tmp_212s_places
ADD COLUMN staging_place_id bigint
GENERATED ALWAYS AS IDENTITY;

CREATE UNIQUE INDEX
    ON tmp_212s_places (staging_place_id);

ANALYZE tmp_212s_places;    

\echo '4. Validating staging before insertion'

DO $$
DECLARE
    n_raw bigint;
    n_tx bigint;
    n_places bigint;
    n_existing bigint;
    n_missing bigint;
BEGIN
    SELECT COUNT(*) INTO n_raw FROM tmp_212s_raw;
    SELECT COUNT(*) INTO n_tx FROM tmp_212s_tx;
    SELECT COUNT(*) INTO n_places FROM tmp_212s_places;

    SELECT COUNT(*) INTO n_existing
    FROM tmp_212s_places c
    JOIN procurement.place p
      ON p.country_code IS NOT DISTINCT FROM c.country_code
     AND p.state_fips IS NOT DISTINCT FROM c.state_fips
     AND p.county_fips IS NOT DISTINCT FROM c.county_fips
     AND p.city_name IS NOT DISTINCT FROM c.city_name
     AND p.zip4 IS NOT DISTINCT FROM c.zip4;

    n_missing := n_places - n_existing;

    RAISE NOTICE 'Raw observations: %', n_raw;
    RAISE NOTICE 'Matched transactions: %', n_tx;
    RAISE NOTICE 'Distinct places: %', n_places;
    RAISE NOTICE 'Existing places: %', n_existing;
    RAISE NOTICE 'Missing places: %', n_missing;

    IF n_raw <> 197952
       OR n_tx <> 197952
       OR n_places <> 4949
       OR n_existing <> 3101
       OR n_missing <> 1848
    THEN
        RAISE EXCEPTION 'ETL-212S staging validation failed';
    END IF;

    IF EXISTS (
        SELECT 1 FROM tmp_212s_tx
        WHERE country_code IS DISTINCT FROM 'USA'
           OR state_code IS DISTINCT FROM 'WA'
           OR state_fips IS DISTINCT FROM '53'
           OR county_fips IS NULL
           OR zip4 IS NULL
    ) THEN
        RAISE EXCEPTION 'Unexpected geographic identity';
    END IF;
END
$$;

\echo '5. Inserting missing canonical places'

CREATE TEMP TABLE tmp_212s_inserted_places (
    place_id bigint
) ON COMMIT DROP;

WITH inserted AS (
    INSERT INTO procurement.place (
        country_code,
        country_name,
        state_code,
        state_name,
        state_fips,
        county_name,
        county_fips,
        city_name,
        zip4,
        congressional_district_current,
        congressional_district_original,
        place_identity_type
    )
    SELECT
        c.country_code,
        c.country_name,
        c.state_code,
        c.state_name,
        c.state_fips,
        c.county_name,
        c.county_fips,
        c.city_name,
        c.zip4,
        c.cd_current,
        c.cd_original,
        'GEOGRAPHIC_FINGERPRINT'
    FROM tmp_212s_places c
    WHERE NOT EXISTS (
        SELECT 1
        FROM procurement.place p
        WHERE p.country_code IS NOT DISTINCT FROM c.country_code
          AND p.state_fips IS NOT DISTINCT FROM c.state_fips
          AND p.county_fips IS NOT DISTINCT FROM c.county_fips
          AND p.city_name IS NOT DISTINCT FROM c.city_name
          AND p.zip4 IS NOT DISTINCT FROM c.zip4
    )
    RETURNING place_id
)
INSERT INTO tmp_212s_inserted_places
SELECT place_id FROM inserted;


\echo '6. Resolving distinct places and county foreign keys'

-- Resolve each distinct geographic identity exactly once.

CREATE TEMP TABLE tmp_212s_place_lookup
ON COMMIT DROP AS
SELECT
    c.staging_place_id,
    p.place_id,
    s.state_id,
    cr.county_id
FROM tmp_212s_places c
JOIN procurement.place p
  ON p.country_code IS NOT DISTINCT FROM c.country_code
 AND p.state_fips IS NOT DISTINCT FROM c.state_fips
 AND p.county_fips IS NOT DISTINCT FROM c.county_fips
 AND p.city_name IS NOT DISTINCT FROM c.city_name
 AND p.zip4 IS NOT DISTINCT FROM c.zip4
JOIN reference.state_registry s
  ON s.state_fips = c.state_fips
JOIN reference.county_registry cr
  ON cr.full_fips = c.county_fips;

CREATE UNIQUE INDEX
    ON tmp_212s_place_lookup (staging_place_id);

ANALYZE tmp_212s_place_lookup;

-- Associate each historical transaction with its staging place.
-- This join is performed against 4,949 candidates, not the
-- entire canonical place dimension.

CREATE TEMP TABLE tmp_212s_transaction_places
ON COMMIT DROP AS
SELECT
    t.raw_award_transaction_id,
    t.award_transaction_id,
    c.staging_place_id,
    t.country_code,
    t.state_code,
    t.county_fips AS county_code,
    t.city_name,
    COALESCE(t.cd_current, t.cd_original)
        AS congressional_district,
    t.zip4 AS zip_code
FROM tmp_212s_tx t
JOIN tmp_212s_places c
  ON c.country_code IS NOT DISTINCT FROM t.country_code
 AND c.state_fips IS NOT DISTINCT FROM t.state_fips
 AND c.county_fips IS NOT DISTINCT FROM t.county_fips
 AND c.city_name IS NOT DISTINCT FROM t.city_name
 AND c.zip4 IS NOT DISTINCT FROM t.zip4;

CREATE UNIQUE INDEX
    ON tmp_212s_transaction_places (award_transaction_id);

ANALYZE tmp_212s_transaction_places;

-- Final foreign-key resolution now uses one integer join.

CREATE TEMP TABLE tmp_212s_links
ON COMMIT DROP AS
SELECT
    t.raw_award_transaction_id,
    t.award_transaction_id,
    p.place_id,
    p.state_id,
    p.county_id,
    t.country_code,
    t.state_code,
    t.county_code,
    t.city_name,
    t.congressional_district,
    t.zip_code
FROM tmp_212s_transaction_places t
JOIN tmp_212s_place_lookup p
  ON p.staging_place_id = t.staging_place_id;

CREATE UNIQUE INDEX
    ON tmp_212s_links (award_transaction_id);

ANALYZE tmp_212s_links;

\echo '7. Validating resolved geography'

DO $$
DECLARE
    n bigint;
BEGIN
    SELECT COUNT(*) INTO n FROM tmp_212s_links;

    RAISE NOTICE 'Resolved transaction geography: %', n;

    IF n <> 197952 THEN
        RAISE EXCEPTION
            'Expected 197952 resolved links, found %', n;
    END IF;

    SELECT COUNT(*) INTO n FROM tmp_212s_inserted_places;

    RAISE NOTICE 'New canonical places inserted: %', n;

    IF n <> 1848 THEN
        RAISE EXCEPTION
            'Expected 1848 inserted places, found %', n;
    END IF;
END
$$;

\echo '8. Inserting missing raw observation relationships'

CREATE TEMP TABLE tmp_212s_inserted_observations (
    raw_award_transaction_id bigint
) ON COMMIT DROP;

WITH inserted AS (
    INSERT INTO procurement.award_transaction_observation (
        raw_award_transaction_id,
        award_transaction_id
    )
    SELECT
        l.raw_award_transaction_id,
        l.award_transaction_id
    FROM tmp_212s_links l
    WHERE NOT EXISTS (
        SELECT 1
        FROM procurement.award_transaction_observation o
        WHERE o.raw_award_transaction_id =
              l.raw_award_transaction_id
    )
    RETURNING raw_award_transaction_id
)
INSERT INTO tmp_212s_inserted_observations
SELECT raw_award_transaction_id FROM inserted;

\echo '9. Inserting missing place-of-performance relationships'

CREATE TEMP TABLE tmp_212s_inserted_relationships (
    award_transaction_id bigint
) ON COMMIT DROP;

WITH inserted AS (
    INSERT INTO procurement.place_of_performance (
        award_transaction_id,
        place_id,
        state_id,
        county_id,
        country_code,
        state_code,
        county_code,
        city_name,
        congressional_district,
        zip_code,
        location_scope
    )
    SELECT
        l.award_transaction_id,
        l.place_id,
        l.state_id,
        l.county_id,
        l.country_code,
        l.state_code,
        l.county_code,
        l.city_name,
        l.congressional_district,
        l.zip_code,
        'OBSERVED'
    FROM tmp_212s_links l
    WHERE NOT EXISTS (
        SELECT 1
        FROM procurement.place_of_performance pop
        WHERE pop.award_transaction_id =
              l.award_transaction_id
    )
    RETURNING award_transaction_id
)
INSERT INTO tmp_212s_inserted_relationships
SELECT award_transaction_id FROM inserted;

\echo '10. Final validation before rollback'

DO $$
DECLARE
    n_places bigint;
    n_observations bigint;
    n_relationships bigint;
    n_missing_observations bigint;
    n_missing_relationships bigint;
BEGIN
    SELECT COUNT(*) INTO n_places
    FROM tmp_212s_inserted_places;

    SELECT COUNT(*) INTO n_observations
    FROM tmp_212s_inserted_observations;

    SELECT COUNT(*) INTO n_relationships
    FROM tmp_212s_inserted_relationships;

    SELECT COUNT(*) INTO n_missing_observations
    FROM tmp_212s_links l
    LEFT JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id =
         l.raw_award_transaction_id
    WHERE o.raw_award_transaction_id IS NULL;

    SELECT COUNT(*) INTO n_missing_relationships
    FROM tmp_212s_links l
    LEFT JOIN procurement.place_of_performance pop
      ON pop.award_transaction_id =
         l.award_transaction_id
    WHERE pop.award_transaction_id IS NULL;

    RAISE NOTICE 'Inserted places: %', n_places;
    RAISE NOTICE 'Inserted observations: %', n_observations;
    RAISE NOTICE 'Inserted place relationships: %', n_relationships;
    RAISE NOTICE 'Missing observations after insert: %',
        n_missing_observations;
    RAISE NOTICE 'Missing geography after insert: %',
        n_missing_relationships;

    IF n_places <> 1848
       OR n_observations <> 197952
       OR n_relationships <> 197865
       OR n_missing_observations <> 0
       OR n_missing_relationships <> 0
    THEN
        RAISE EXCEPTION
            'ETL-212S final validation FAILED';
    END IF;

    RAISE NOTICE
        'ETL-212S validation PASS - rollback required';
END
$$;

\echo '11. ROLLING BACK ALL INSERTIONS'

ROLLBACK;

\echo '============================================================'
\echo 'ETL-212S v0.1 FINISHED - ALL TABLE INSERTIONS ROLLED BACK'
\echo '============================================================'
