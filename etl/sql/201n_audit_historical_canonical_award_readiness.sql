
\set ON_ERROR_STOP on
\pset pager off

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '600s';

\echo ''
\echo '================================================================'
\echo 'ETL-201N v0.1 - HISTORICAL CANONICAL AWARD READINESS'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'STAGE A - READ ONLY - NO DATABASE WRITES'
\echo '================================================================'

\echo ''
\echo 'SECTION 1 - HISTORICAL COHORT AND SOURCE QUALITY'

WITH historical AS MATERIALIZED (
    SELECT
        r.assistance_award_unique_key AS award_key,
        r.load_batch_id,
        r.source_row_number,
        r.raw_record,
        NULLIF(BTRIM(r.raw_record ->> 'cfda_number'), '')
            AS listing_code,
        NULLIF(BTRIM(r.raw_record ->> 'assistance_type_code'), '')
            AS type_code
    FROM assistance.raw_award_transaction AS r
    WHERE r.load_batch_id IN (20, 21)
),
grouped AS MATERIALIZED (
    SELECT
        award_key,
        COUNT(DISTINCT listing_code) AS listing_count,
        COUNT(DISTINCT type_code) AS type_count
    FROM historical
    GROUP BY award_key
),
eligible AS MATERIALIZED (
    SELECT g.award_key
    FROM grouped AS g
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = g.award_key
    WHERE a.assistance_award_unique_key IS NULL
      AND g.listing_count <= 1
      AND g.type_count <= 1
),
candidate AS MATERIALIZED (
    SELECT h.*
    FROM historical AS h
    JOIN eligible AS e
      ON e.award_key = h.award_key
)
SELECT
    COUNT(*) AS candidate_source_rows,
    COUNT(DISTINCT award_key) AS candidate_awards,
    COUNT(*) FILTER (
        WHERE load_batch_id = 20
    ) AS fy2018_rows,
    COUNT(*) FILTER (
        WHERE load_batch_id = 21
    ) AS fy2019_rows,
    COUNT(*) FILTER (
        WHERE NULLIF(
            BTRIM(raw_record ->> 'award_id_fain'), ''
        ) IS NOT NULL
    ) AS rows_with_fain,
    COUNT(*) FILTER (
        WHERE NULLIF(
            BTRIM(raw_record ->> 'award_id_uri'), ''
        ) IS NOT NULL
    ) AS rows_with_uri,
    COUNT(*) FILTER (
        WHERE NULLIF(
            BTRIM(raw_record ->> 'award_id_fain'), ''
        ) IS NULL
          AND NULLIF(
            BTRIM(raw_record ->> 'award_id_uri'), ''
        ) IS NULL
    ) AS rows_without_either_identifier
FROM candidate;

\echo ''
\echo 'SECTION 2 - AWARD-LEVEL IDENTIFIER COVERAGE'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        NULLIF(BTRIM(raw_record ->> 'cfda_number'), '')
            AS listing_code,
        NULLIF(BTRIM(raw_record ->> 'assistance_type_code'), '')
            AS type_code,
        NULLIF(BTRIM(raw_record ->> 'award_id_fain'), '')
            AS fain,
        NULLIF(BTRIM(raw_record ->> 'award_id_uri'), '')
            AS uri
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
grouped AS (
    SELECT
        award_key,
        COUNT(DISTINCT listing_code) AS listing_count,
        COUNT(DISTINCT type_code) AS type_count,
        COUNT(*) FILTER (WHERE fain IS NOT NULL) AS fain_rows,
        COUNT(*) FILTER (WHERE uri IS NOT NULL) AS uri_rows,
        COUNT(DISTINCT fain) AS distinct_fains,
        COUNT(DISTINCT uri) AS distinct_uris
    FROM historical
    GROUP BY award_key
)
SELECT
    COUNT(*) AS eligible_awards,
    COUNT(*) FILTER (
        WHERE fain_rows = 0 AND uri_rows = 0
    ) AS awards_without_either_identifier,
    COUNT(*) FILTER (
        WHERE distinct_fains > 1
    ) AS awards_with_multiple_fains,
    COUNT(*) FILTER (
        WHERE distinct_uris > 1
    ) AS awards_with_multiple_uris,
    COUNT(*) FILTER (
        WHERE fain_rows > 0 AND uri_rows > 0
    ) AS awards_with_both_identifier_types
FROM grouped AS g
LEFT JOIN assistance.award AS a
  ON a.assistance_award_unique_key = g.award_key
WHERE a.assistance_award_unique_key IS NULL
  AND g.listing_count <= 1
  AND g.type_count <= 1;

\echo ''
\echo 'SECTION 3 - SOURCE FIELD FORMATS'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        raw_record,
        NULLIF(BTRIM(raw_record ->> 'cfda_number'), '')
            AS listing_code,
        NULLIF(BTRIM(raw_record ->> 'assistance_type_code'), '')
            AS type_code
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
eligible AS (
    SELECT h.award_key
    FROM historical AS h
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = h.award_key
    WHERE a.assistance_award_unique_key IS NULL
    GROUP BY h.award_key
    HAVING COUNT(DISTINCT h.listing_code) <= 1
       AND COUNT(DISTINCT h.type_code) <= 1
),
candidate AS (
    SELECT h.raw_record
    FROM historical AS h
    JOIN eligible AS e ON e.award_key = h.award_key
),
fields AS (
    SELECT
        c.raw_record,
        v.field_name,
        NULLIF(BTRIM(c.raw_record ->> v.field_name), '')
            AS field_value
    FROM candidate AS c
    CROSS JOIN (
        VALUES
          ('action_date'),
          ('period_of_performance_start_date'),
          ('period_of_performance_current_end_date'),
          ('total_obligated_amount'),
          ('total_outlayed_amount_for_overall_award'),
          ('total_non_federal_funding_amount'),
          ('total_face_value_of_loan'),
          ('total_loan_subsidy_cost')
    ) AS v(field_name)
)
SELECT
    field_name,
    COUNT(*) AS examined_rows,
    COUNT(*) FILTER (
        WHERE field_value IS NULL
    ) AS blank_rows,
    COUNT(*) FILTER (
        WHERE field_value IS NOT NULL
    ) AS populated_rows,
    COUNT(*) FILTER (
        WHERE field_value IS NOT NULL
          AND (
              CASE
                WHEN field_name IN (
                    'action_date',
                    'period_of_performance_start_date',
                    'period_of_performance_current_end_date'
                )
                THEN LEFT(field_value, 10)
                     !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                ELSE
                    REPLACE(
                        REPLACE(field_value, ',', ''),
                        '$', ''
                    ) !~ '^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$'
              END
          )
    ) AS nonconforming_format_rows
FROM fields
GROUP BY field_name
ORDER BY field_name;

\echo ''
\echo 'SECTION 4 - DIMENSION RESOLUTION'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        NULLIF(BTRIM(raw_record ->> 'cfda_number'), '')
            AS listing_code,
        NULLIF(BTRIM(raw_record ->> 'assistance_type_code'), '')
            AS type_code,
        NULLIF(BTRIM(raw_record ->> 'funding_opportunity_number'), '')
            AS opportunity_code
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
eligible AS (
    SELECT h.award_key
    FROM historical AS h
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = h.award_key
    WHERE a.assistance_award_unique_key IS NULL
    GROUP BY h.award_key
    HAVING COUNT(DISTINCT h.listing_code) <= 1
       AND COUNT(DISTINCT h.type_code) <= 1
)
SELECT
    COUNT(*) AS candidate_rows,
    COUNT(*) FILTER (
        WHERE h.listing_code IS NOT NULL
          AND l.assistance_listing_id IS NULL
    ) AS unresolved_listing_rows,
    COUNT(*) FILTER (
        WHERE h.type_code IS NOT NULL
          AND t.assistance_type_id IS NULL
    ) AS unresolved_type_rows,
    COUNT(*) FILTER (
        WHERE h.opportunity_code IS NOT NULL
          AND f.funding_opportunity_id IS NULL
    ) AS unresolved_opportunity_rows
FROM historical AS h
JOIN eligible AS e ON e.award_key = h.award_key
LEFT JOIN assistance.assistance_listing AS l
  ON l.cfda_number = h.listing_code
LEFT JOIN assistance.assistance_type AS t
  ON t.assistance_type_code = h.type_code
LEFT JOIN assistance.funding_opportunity AS f
  ON f.funding_opportunity_number = h.opportunity_code;

\echo ''
\echo 'SECTION 5 - CANONICAL TARGET CONSTRAINTS'

SELECT
    conname AS constraint_name,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'assistance.award'::regclass
  AND contype IN ('c', 'u', 'p', 'f')
ORDER BY conname;

ROLLBACK;

\echo ''
\echo 'ETL-201N STAGE A COMPLETE - READ ONLY'
