
-- ============================================================
-- WCFFBP ETL-204C-2C.6
-- NORMALIZED HISTORICAL RAILROAD AWARD CODES
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
        NULLIF(TRIM(canonical_award_description), '')
            AS description,
        substring(
            assistance_award_unique_key
            FROM '^ASST_AGG_RRB_[0-9]{6}_(.*?)_WA'
        ) AS raw_code
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
      AND TRIM(cfda_number) = '57.001'
),
normalized AS (
    SELECT
        *,
        NULLIF(
            REGEXP_REPLACE(raw_code, '[^0-9]', '', 'g'),
            ''
        ) AS normalized_code
    FROM source
)
SELECT
    fiscal_year,
    COALESCE(normalized_code, '[UNPARSED]')
        AS normalized_code,
    COALESCE(
        description,
        '[MISSING DESCRIPTION]'
    ) AS description,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    SUM(obligation) AS net_obligations
FROM normalized
GROUP BY fiscal_year, normalized_code, description
ORDER BY fiscal_year, normalized_code, net_obligations DESC;

COMMIT;

SELECT 'ETL-204C-2C.6 COMPLETE - NO DATABASE WRITES';
