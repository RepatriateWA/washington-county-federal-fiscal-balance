
-- ============================================================
-- WCFFBP ETL-204C-2C.3
-- HISTORICAL RAILROAD DESCRIPTION INVENTORY
-- FY2018-FY2019
-- STRICTLY READ ONLY
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

-- 1. Description distribution, retaining missing values.
WITH source AS (
    SELECT
        v.action_date_fiscal_year AS fiscal_year,
        v.assistance_transaction_id,
        v.federal_action_obligation AS obligation,
        NULLIF(TRIM(v.canonical_award_description), '')
            AS canonical_description,
        NULLIF(TRIM(r.raw_record ->> 'transaction_description'), '')
            AS raw_description,
        NULLIF(TRIM(r.raw_record ->>
            'prime_award_base_transaction_description'), '')
            AS base_description
    FROM analysis.v_certified_assistance_ledger v
    JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id = v.assistance_transaction_id
    JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
)
SELECT
    fiscal_year,
    COALESCE(
        canonical_description,
        raw_description,
        base_description,
        '[MISSING DESCRIPTION]'
    ) AS effective_description,
    COUNT(*) AS transactions,
    SUM(obligation) AS net_obligations
FROM source
GROUP BY fiscal_year, effective_description
ORDER BY fiscal_year, net_obligations DESC;


-- 2. Award identifier examples for each fiscal year.
SELECT
    v.action_date_fiscal_year AS fiscal_year,
    v.assistance_award_unique_key,
    v.canonical_award_description,
    v.federal_action_obligation,
    r.raw_record ->> 'award_id_uri' AS raw_award_uri,
    r.raw_record ->> 'transaction_description'
        AS raw_transaction_description
FROM analysis.v_certified_assistance_ledger v
JOIN assistance.award_transaction_observation o
  ON o.assistance_transaction_id = v.assistance_transaction_id
JOIN assistance.raw_award_transaction r
  ON r.raw_assistance_transaction_id =
     o.raw_assistance_transaction_id
WHERE v.load_batch_id IN (20, 21)
  AND TRIM(v.cfda_number) = '57.001'
ORDER BY
    v.action_date_fiscal_year,
    v.federal_action_obligation DESC
LIMIT 30;

COMMIT;

SELECT 'ETL-204C-2C.3 COMPLETE - NO DATABASE WRITES';
