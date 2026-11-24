
-- ============================================================
-- WCFFBP ETL-204C-2C.5
-- HISTORICAL RAILROAD UNPARSED IDENTIFIERS
-- FY2018-FY2019
-- READ ONLY
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

WITH source AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        assistance_award_unique_key AS award_key,
        canonical_award_description AS description,
        federal_action_obligation AS obligation,
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
    award_key,
    description,
    obligation
FROM source
WHERE embedded_code IS NULL
ORDER BY fiscal_year, award_key
LIMIT 80;

COMMIT;

SELECT 'ETL-204C-2C.5 COMPLETE - NO DATABASE WRITES';
