
-- ============================================================
-- WCFFBP ETL-204C-2C.8
-- RRB AWARD-CODE CROSS-PERIOD VALIDATION
-- FY2018-FY2024
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

WITH source AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        assistance_transaction_id,
        assistance_award_unique_key AS award_key,
        federal_action_obligation AS obligation,
        UPPER(COALESCE(
            canonical_award_description, ''
        )) AS description
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
      AND TRIM(cfda_number) = '57.001'
),
parsed AS (
    SELECT
        *,
        substring(
            award_key
            FROM '^ASST_AGG_RRB_[0-9]{6}_[[:space:]"]*([0-9]{4})[[:space:]"]*_'
        ) AS embedded_code
    FROM source
),
classified AS (
    SELECT
        *,
        CASE
            WHEN description LIKE '%RAILROAD UNEMPLOYMENT%'
              OR description LIKE '%CARES ACT%'
              OR description LIKE '%ENHANCED BENEFIT%'
              OR description LIKE '%EXTENDED BENEFIT%'
              OR description LIKE '%WAITING PERIOD%'
                THEN 'RUIA_CANDIDATE'
            WHEN description LIKE '%PENSION%'
              OR description LIKE '%VESTED DUAL BENEFIT%'
                THEN 'RETIREMENT_CANDIDATE'
            WHEN TRIM(description) = ''
                THEN 'MISSING_DESCRIPTION'
            ELSE 'OTHER_DESCRIPTION'
        END AS diagnostic_family
    FROM parsed
)
SELECT
    fiscal_year,
    COALESCE(embedded_code, '[UNPARSED]') AS embedded_code,
    diagnostic_family,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM classified
GROUP BY fiscal_year, embedded_code, diagnostic_family
ORDER BY fiscal_year, embedded_code, diagnostic_family;

-- Annual completeness controls.
WITH source AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        assistance_transaction_id,
        assistance_award_unique_key,
        federal_action_obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
      AND TRIM(cfda_number) = '57.001'
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(*) FILTER (
        WHERE substring(
            assistance_award_unique_key
            FROM '^ASST_AGG_RRB_[0-9]{6}_[[:space:]"]*([0-9]{4})[[:space:]"]*_'
        ) IS NULL
    ) AS unparsed_identifiers,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM source
GROUP BY fiscal_year
ORDER BY fiscal_year;

COMMIT;

SELECT 'ETL-204C-2C.8 COMPLETE - NO DATABASE WRITES';
