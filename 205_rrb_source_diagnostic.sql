\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '=== 1. FY2018/FY2019 BY BATCH ==='

SELECT
    load_batch_id,
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year IN (2018, 2019)
GROUP BY 1, 2
ORDER BY 1, 2;

\echo '=== 2. RRB ASSISTANCE LISTING ==='

SELECT
    action_date_fiscal_year AS fiscal_year,
    load_batch_id,
    cfda_number,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year IN (2018, 2019)
  AND TRIM(cfda_number) = '57.001'
GROUP BY 1, 2, 3
ORDER BY 1, 2;

\echo '=== 3. BATCH 20/21 SOURCE POPULATION ==='

SELECT
    load_batch_id,
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

COMMIT;
