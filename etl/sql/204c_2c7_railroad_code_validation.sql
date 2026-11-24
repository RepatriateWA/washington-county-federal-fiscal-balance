
-- ============================================================
-- WCFFBP ETL-204C-2C.7
-- HISTORICAL RRB CODE VALIDATION
-- FY2018-FY2019
-- READ ONLY
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
        COALESCE(
            NULLIF(TRIM(canonical_award_description), ''),
            '[MISSING DESCRIPTION]'
        ) AS description
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
      AND TRIM(cfda_number) = '57.001'
),
parsed AS (
    SELECT
        *,
        substring(
            award_key
            FROM '^ASST_AGG_RRB_[0-9]{6}_[[:space:]"]*([0-9]{4})[[:space:]"]*_'
        ) AS code
    FROM source
)
SELECT
    fiscal_year,
    COALESCE(code, '[UNPARSED]') AS code,
    description,
    COUNT(*) AS transactions,
    SUM(obligation) AS net_obligations
FROM parsed
GROUP BY fiscal_year, code, description
ORDER BY fiscal_year, code, net_obligations DESC;

-- Inspect remaining failures, if any.
WITH source AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        assistance_award_unique_key AS award_key,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
      AND TRIM(cfda_number) = '57.001'
)
SELECT fiscal_year, award_key, obligation
FROM source
WHERE substring(
    award_key
    FROM '^ASST_AGG_RRB_[0-9]{6}_[[:space:]"]*([0-9]{4})[[:space:]"]*_'
) IS NULL
ORDER BY fiscal_year, award_key
LIMIT 40;

COMMIT;

SELECT 'ETL-204C-2C.7 COMPLETE - NO DATABASE WRITES';
