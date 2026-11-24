
-- ============================================================
-- WCFFBP ETL-204C-2B.6
-- HISTORICAL RAILROAD COUNTY FIPS VALIDATION
-- FY2018-FY2019
-- READ ONLY - NO DATABASE MODIFICATIONS
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT '1. COUNTY IDENTIFIER VALIDATION' AS section;

WITH railroad AS (
    SELECT
        v.assistance_transaction_id,
        v.action_date_fiscal_year AS fiscal_year,
        v.assistance_award_unique_key AS award_key,
        v.federal_action_obligation AS obligation,
        substring(
            upper(v.assistance_award_unique_key)
            FROM 'WA\*\*([0-9]{3})'
        ) AS candidate_county_fips
    FROM analysis.v_certified_assistance_ledger v
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
),
classified AS (
    SELECT
        r.*,
        c.county_name,
        CASE
            WHEN r.candidate_county_fips IS NULL
                THEN 'NO_COUNTY_PATTERN'
            WHEN c.county_id IS NULL
                THEN 'UNMATCHED_COUNTY_FIPS'
            ELSE 'MATCHED_WA_COUNTY'
        END AS match_status
    FROM railroad r
    LEFT JOIN reference.county_registry c
      ON c.full_fips =
         ('53' || r.candidate_county_fips)
)
SELECT
    fiscal_year,
    match_status,
    COUNT(*) AS transactions,
    SUM(obligation) AS net_obligations
FROM classified
GROUP BY fiscal_year, match_status
ORDER BY fiscal_year, match_status;


SELECT '2. COUNTY DISTRIBUTION' AS section;

WITH railroad AS (
    SELECT
        v.action_date_fiscal_year AS fiscal_year,
        v.federal_action_obligation AS obligation,
        substring(
            upper(v.assistance_award_unique_key)
            FROM 'WA\*\*([0-9]{3})'
        ) AS county_fips
    FROM analysis.v_certified_assistance_ledger v
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
)
SELECT
    r.fiscal_year,
    c.full_fips,
    c.county_name,
    COUNT(*) AS transactions,
    SUM(r.obligation) AS net_obligations
FROM railroad r
JOIN reference.county_registry c
  ON c.full_fips = ('53' || r.county_fips)
GROUP BY
    r.fiscal_year,
    c.full_fips,
    c.county_name
ORDER BY
    r.fiscal_year,
    c.full_fips;


SELECT '3. RAW JSON GEOGRAPHY FIELD DISCOVERY'
    AS section;

WITH railroad AS (
    SELECT
        v.assistance_transaction_id
    FROM analysis.v_certified_assistance_ledger v
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
),
raw_records AS (
    SELECT DISTINCT
        raw.raw_assistance_transaction_id,
        raw.raw_record
    FROM railroad r
    JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id =
         r.assistance_transaction_id
    JOIN assistance.raw_award_transaction raw
      ON raw.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id
)
SELECT
    key AS raw_field_name,
    COUNT(*) AS records_with_field,
    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(value), '') IS NOT NULL
    ) AS nonempty_values
FROM raw_records,
LATERAL jsonb_each_text(raw_record)
WHERE key ILIKE '%state%'
   OR key ILIKE '%county%'
   OR key ILIKE '%place%'
   OR key ILIKE '%location%'
GROUP BY key
ORDER BY key;

COMMIT;

SELECT 'ETL-204C-2B.6 COMPLETE - NO DATABASE WRITES';
