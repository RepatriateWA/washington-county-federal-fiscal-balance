
\set ON_ERROR_STOP on
\pset pager off

\echo '========================================================='
\echo 'ETL-214M2A-2 - RAW HISTORICAL PROVENANCE'
\echo 'FY2018-FY2019 / SIX ASSISTANCE PROGRAMS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '========================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. RAW JSON KEYS FOR AGENCY AND RECIPIENT FIELDS'

WITH target AS MATERIALIZED (
    SELECT
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        o.raw_assistance_transaction_id
    FROM analysis.v_certified_assistance_ledger l
    JOIN analysis.v_assistance_transaction_observation_ledger o
      ON o.assistance_transaction_id = l.assistance_transaction_id
    WHERE (
        (l.load_batch_id = 20 AND l.action_date_fiscal_year = 2018)
        OR
        (l.load_batch_id = 21 AND l.action_date_fiscal_year = 2019)
    )
    AND TRIM(l.cfda_number) IN (
        '10.555', '84.010', '84.027',
        '84.063', '93.558', '93.600'
    )
),
sample AS (
    SELECT DISTINCT ON (t.fiscal_year, t.program_code)
        t.fiscal_year,
        t.program_code,
        r.raw_record
    FROM target t
    JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         t.raw_assistance_transaction_id
    ORDER BY
        t.fiscal_year,
        t.program_code,
        t.raw_assistance_transaction_id
)
SELECT
    s.fiscal_year,
    s.program_code,
    k.key AS raw_json_key,
    LEFT(s.raw_record ->> k.key, 160) AS example_value
FROM sample s
CROSS JOIN LATERAL
    JSONB_OBJECT_KEYS(s.raw_record) AS k(key)
WHERE k.key ILIKE '%recipient%'
   OR k.key ILIKE '%agency%'
   OR k.key ILIKE '%subagency%'
   OR k.key ILIKE '%uei%'
   OR k.key ILIKE '%duns%'
ORDER BY
    s.program_code,
    s.fiscal_year,
    k.key;

\echo ''
\echo '2. RAW JSON FIELD COVERAGE BY PROGRAM AND YEAR'

WITH target AS MATERIALIZED (
    SELECT
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        o.raw_assistance_transaction_id
    FROM analysis.v_certified_assistance_ledger l
    JOIN analysis.v_assistance_transaction_observation_ledger o
      ON o.assistance_transaction_id = l.assistance_transaction_id
    WHERE (
        (l.load_batch_id = 20 AND l.action_date_fiscal_year = 2018)
        OR
        (l.load_batch_id = 21 AND l.action_date_fiscal_year = 2019)
    )
    AND TRIM(l.cfda_number) IN (
        '10.555', '84.010', '84.027',
        '84.063', '93.558', '93.600'
    )
),
raw_fields AS (
    SELECT
        t.fiscal_year,
        t.program_code,
        t.raw_assistance_transaction_id,
        k.key,
        NULLIF(BTRIM(r.raw_record ->> k.key), '') AS field_value
    FROM target t
    JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         t.raw_assistance_transaction_id
    CROSS JOIN LATERAL
        JSONB_OBJECT_KEYS(r.raw_record) AS k(key)
    WHERE k.key ILIKE '%recipient%'
       OR k.key ILIKE '%agency%'
       OR k.key ILIKE '%uei%'
       OR k.key ILIKE '%duns%'
)
SELECT
    program_code,
    fiscal_year,
    key AS raw_json_key,
    COUNT(*) AS records_with_key,
    COUNT(*) FILTER (
        WHERE field_value IS NOT NULL
          AND LOWER(field_value) NOT IN (
              'null', 'none', 'nan', 'n/a'
          )
    ) AS records_with_usable_value,
    COUNT(DISTINCT field_value) AS distinct_values
FROM raw_fields
GROUP BY program_code, fiscal_year, key
ORDER BY program_code, fiscal_year, key;

ROLLBACK;

\echo 'ETL-214M2A-2 COMPLETE - NO DATABASE WRITES'
