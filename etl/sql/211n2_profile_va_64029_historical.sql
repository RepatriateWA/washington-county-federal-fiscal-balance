
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211N2 - AL 64.029 HISTORICAL POLICY TRIAGE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. CERTIFIED HISTORICAL TRANSACTION PROFILE'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    BTRIM(c.cfda_number) AS program_code,
    MIN(c.cfda_title) AS example_program_title,
    COUNT(*) AS transactions,
    COUNT(DISTINCT c.assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE c.federal_action_obligation < 0
    ) AS negative_transactions,
    COUNT(*) FILTER (
        WHERE c.is_covid
    ) AS covid_transactions
FROM analysis.v_certified_assistance_ledger c
WHERE BTRIM(c.cfda_number) = '64.029'
  AND (
      (c.load_batch_id = 20
       AND c.action_date_fiscal_year = 2018)
      OR
      (c.load_batch_id = 21
       AND c.action_date_fiscal_year = 2019)
  )
GROUP BY c.action_date_fiscal_year, BTRIM(c.cfda_number)
ORDER BY fiscal_year;

\echo ''
\echo '2. ALL EXISTING AL 64.029 PROGRAM POLICIES'

SELECT
    m.source_system,
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.resolved_accounting_disposition,
    m.methodology_version,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.source_selection_basis
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '64.029'
ORDER BY m.valid_from_fiscal_year;

\echo ''
\echo '3. HISTORICAL CLASSIFICATION COLLISION CHECK'

SELECT
    'PROGRAM_POLICY' AS record_type,
    COUNT(*) AS overlapping_records
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '64.029'
  AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
  AND COALESCE(valid_through_fiscal_year, 9999) >= 2018

UNION ALL

SELECT
    'PROGRAM_CLASSIFICATION',
    COUNT(*)
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '64.029'
  AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
  AND COALESCE(valid_through_fiscal_year, 9999) >= 2018

UNION ALL

SELECT
    'AWARD_CLASSIFICATION',
    COUNT(*)
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '64.029'
  AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
  AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

\echo ''
\echo '4. HISTORICAL VA GDX EXPENDITURE COMPONENTS'

SELECT
    e.fiscal_year,
    k.category_code,
    k.category_name,
    k.aggregation_role,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT e.county_id) AS distinct_counties,
    ROUND(SUM(e.expenditure_amount)::numeric, 2)
        AS expenditure_dollars
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category k
  ON k.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
GROUP BY
    e.fiscal_year,
    k.category_code,
    k.category_name,
    k.aggregation_role
ORDER BY e.fiscal_year, k.category_code;

ROLLBACK;

\echo ''
\echo 'ETL-211N2 COMPLETE - NO DATABASE WRITES'
