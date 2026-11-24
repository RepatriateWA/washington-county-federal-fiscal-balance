-- ETL-202A.2
-- READ ONLY: fiscal source and policy discovery

\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- 1. Exact source table populations.
SELECT
    source_name,
    row_count
FROM (
    SELECT 'irs.county_income_tax' AS source_name,
           COUNT(*) AS row_count
    FROM irs.county_income_tax
    UNION ALL
    SELECT 'irs.state_collections', COUNT(*)
    FROM irs.state_collections
    UNION ALL
    SELECT 'ssa.benefit_payments', COUNT(*)
    FROM ssa.benefit_payments
    UNION ALL
    SELECT 'va.gdx_county_expenditure', COUNT(*)
    FROM va.gdx_county_expenditure
    UNION ALL
    SELECT 'cms.medicare_core_county_year', COUNT(*)
    FROM cms.medicare_core_county_year
    UNION ALL
    SELECT 'cms.medicare_geographic_payments', COUNT(*)
    FROM cms.medicare_geographic_payments
    UNION ALL
    SELECT 'cms_raw.medicaid_mbes', COUNT(*)
    FROM cms_raw.medicaid_mbes
    UNION ALL
    SELECT 'chip.cms21_expenditure', COUNT(*)
    FROM chip.cms21_expenditure
    UNION ALL
    SELECT 'bea.compensation_observation', COUNT(*)
    FROM bea.compensation_observation
    UNION ALL
    SELECT 'omb.object_class_observation', COUNT(*)
    FROM omb.object_class_observation
    UNION ALL
    SELECT 'procurement.award_transaction', COUNT(*)
    FROM procurement.award_transaction
    UNION ALL
    SELECT 'assistance.award_transaction', COUNT(*)
    FROM assistance.award_transaction
    UNION ALL
    SELECT 'reference.federal_inflow_source_policy', COUNT(*)
    FROM reference.federal_inflow_source_policy
    UNION ALL
    SELECT 'reference.federal_inflow_program_policy_mapping', COUNT(*)
    FROM reference.federal_inflow_program_policy_mapping
) AS inventory
ORDER BY source_name;

-- 2. Discover year-column names before grouping by year.
SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
    ('irs','county_income_tax'),
    ('irs','state_collections'),
    ('ssa','benefit_payments'),
    ('va','gdx_county_expenditure'),
    ('cms','medicare_core_county_year'),
    ('cms','medicare_geographic_payments'),
    ('cms_raw','medicaid_mbes'),
    ('chip','cms21_expenditure'),
    ('bea','compensation_observation'),
    ('omb','object_class_observation'),
    ('procurement','award_transaction'),
    ('assistance','award_transaction')
)
AND column_name ~* 'year|date|period|batch'
ORDER BY table_schema, table_name, ordinal_position;

-- 3. Inspect existing ledger-policy column definitions.
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
    ('reference','federal_inflow_source_policy'),
    ('reference','federal_inflow_program_policy_mapping'),
    ('reporting','v_washington_partial_fiscal_balance'),
    ('reporting','v_washington_tracked_expenditures'),
    ('reporting','v_federal_receipts_by_state_year'),
    ('reporting','v_federal_expenditures_by_state_year')
)
ORDER BY table_schema, table_name, ordinal_position;

-- 4. Inspect existing reporting-view SQL definitions.
SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'reporting'
  AND viewname IN (
      'v_washington_partial_fiscal_balance',
      'v_washington_tracked_expenditures',
      'v_federal_receipts_by_state_year',
      'v_federal_expenditures_by_state_year'
  )
ORDER BY viewname;

ROLLBACK;
