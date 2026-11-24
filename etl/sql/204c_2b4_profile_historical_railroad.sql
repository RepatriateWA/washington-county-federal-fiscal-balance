
-- ============================================================
-- WCFFBP ETL-204C-2B.4
-- HISTORICAL RAILROAD RETIREMENT PROFILE
-- FY2018-FY2019
-- READ ONLY - NO LEDGER MODIFICATIONS
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT '1. RAILROAD RETIREMENT BY FISCAL YEAR'
    AS section;

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations,
    SUM(total_outlayed_amount_for_overall_award)
        AS reported_overall_award_outlays,
    COUNT(*) FILTER (
        WHERE total_outlayed_amount_for_overall_award
              IS NOT NULL
    ) AS rows_with_outlay_data
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
  AND TRIM(cfda_number) = '57.001'
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


SELECT '2. ASSISTANCE TYPE CLASSIFICATION'
    AS section;

SELECT
    action_date_fiscal_year AS fiscal_year,
    assistance_type_code,
    assistance_type_description,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
  AND TRIM(cfda_number) = '57.001'
GROUP BY
    action_date_fiscal_year,
    assistance_type_code,
    assistance_type_description
ORDER BY
    action_date_fiscal_year,
    assistance_type_code;


SELECT '3. GEOGRAPHIC ATTRIBUTION'
    AS section;

SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(
        TRIM(performance_state_code),
        '[NULL]'
    ) AS performance_state,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
  AND TRIM(cfda_number) = '57.001'
GROUP BY
    action_date_fiscal_year,
    performance_state_code
ORDER BY
    action_date_fiscal_year,
    transactions DESC;


SELECT '4. EXTRAORDINARY FUNDING PROFILE'
    AS section;

SELECT
    action_date_fiscal_year AS fiscal_year,
    is_covid,
    is_iija,
    is_extraordinary,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
  AND TRIM(cfda_number) = '57.001'
GROUP BY
    action_date_fiscal_year,
    is_covid,
    is_iija,
    is_extraordinary
ORDER BY action_date_fiscal_year;


SELECT '5. HISTORICAL RAILROAD CONTROL TOTALS'
    AS section;

SELECT
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    SUM(federal_action_obligation)
        AS net_obligations,
    MIN(action_date) AS earliest_action,
    MAX(action_date) AS latest_action
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
  AND TRIM(cfda_number) = '57.001';

COMMIT;

SELECT 'ETL-204C-2B.4 COMPLETE - NO DATABASE WRITES';
