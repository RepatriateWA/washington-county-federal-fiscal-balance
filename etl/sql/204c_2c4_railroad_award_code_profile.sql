
-- ============================================================
-- WCFFBP ETL-204C-2C.4
-- HISTORICAL RAILROAD AWARD-CODE PROFILE
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
        ) AS description,
        substring(
            assistance_award_unique_key
            FROM '^ASST_AGG_RRB_[0-9]{6}_([0-9]{4})_'
        ) AS embedded_code
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
      AND TRIM(cfda_number) = '57.001'
)
SELECT
    fiscal_year,
    COALESCE(embedded_code, '[UNPARSED]') AS embedded_code,
    description,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    SUM(obligation) AS net_obligations
FROM source
GROUP BY fiscal_year, embedded_code, description
ORDER BY fiscal_year, embedded_code, net_obligations DESC;

COMMIT;

SELECT 'ETL-204C-2C.4 COMPLETE - NO DATABASE WRITES';
