-- ============================================================
-- WCFFBP ETL-204C-2C.1
-- RAILROAD RETIREMENT ACCOUNTING PROFILE
-- FY2018-FY2024
-- READ ONLY
-- ============================================================
\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION READ ONLY;
SELECT '1. RAILROAD RETIREMENT ANNUAL CONTROL' AS section;
SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    SUM(federal_action_obligation)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '57.001'
  AND action_date_fiscal_year BETWEEN 2018 AND 2024
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;
SELECT '2. HISTORICAL RAW BENEFIT CLASSIFICATION FIELDS'
    AS section;
WITH historical AS (
    SELECT DISTINCT
        r.raw_assistance_transaction_id,
        r.raw_record
    FROM analysis.v_certified_assistance_ledger v
    JOIN assistance.award_transaction_observation o
      ON o.assistance_transaction_id =
         v.assistance_transaction_id
    JOIN assistance.raw_award_transaction r
      ON r.raw_assistance_transaction_id =
         o.raw_assistance_transaction_id
    WHERE v.load_batch_id IN (20, 21)
      AND TRIM(v.cfda_number) = '57.001'
)
SELECT
    key AS source_field,
    COUNT(*) AS source_records,
    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(value), '') IS NOT NULL
    ) AS populated_records
FROM historical,
LATERAL jsonb_each_text(raw_record)
WHERE key ILIKE '%benefit%'
   OR key ILIKE '%program%'
   OR key ILIKE '%award%'
   OR key ILIKE '%description%'
   OR key ILIKE '%outlay%'
GROUP BY key
ORDER BY key;
SELECT '3. HISTORICAL AWARD IDENTIFIER PATTERNS' AS section;
SELECT
action_date_fiscal_year AS fiscal_year,
substring(
assistance_award_unique_key
FROM '^ASST_AGG_RRB_[^]+([^_]+)'
) AS raw_category_segment,
COUNT(*) AS transactions,
SUM(federal_action_obligation)
AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
AND TRIM(cfda_number) = '57.001'
GROUP BY
action_date_fiscal_year,
raw_category_segment
ORDER BY
fiscal_year,
raw_category_segment;
COMMIT;
SELECT 'ETL-204C-2C.1 COMPLETE - NO DATABASE WRITES';