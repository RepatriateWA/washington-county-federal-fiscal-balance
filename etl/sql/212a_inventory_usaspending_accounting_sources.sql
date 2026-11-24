
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212A - USASPENDING ACCOUNTING SOURCE INVENTORY'
\echo 'FY2018-FY2025'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. USASPENDING AND ACCOUNTING SCHEMA OBJECTS'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'assistance',
    'procurement',
    'analysis',
    'reporting'
)
  AND (
      table_schema IN ('assistance', 'procurement')
      OR table_name ILIKE '%assistance%'
      OR table_name ILIKE '%procurement%'
      OR table_name ILIKE '%ledger%'
      OR table_name ILIKE '%fiscal_balance%'
  )
ORDER BY table_schema, table_name;

\echo ''
\echo '2. ACQUISITION, TRANSACTION AND POLICY COLUMNS'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE (
    table_schema IN ('assistance', 'procurement')
    OR (
        table_schema = 'analysis'
        AND table_name IN (
            'v_certified_assistance_ledger',
            'v_assistance_transaction_observation_ledger'
        )
    )
    OR (
        table_schema = 'reference'
        AND table_name IN (
            'federal_inflow_program_classification',
            'federal_inflow_source_policy',
            'federal_inflow_program_policy_mapping'
        )
    )
)
AND (
    column_name ILIKE '%fiscal%'
    OR column_name ILIKE '%batch%'
    OR column_name ILIKE '%status%'
    OR column_name ILIKE '%obligation%'
    OR column_name ILIKE '%outlay%'
    OR column_name ILIKE '%amount%'
    OR column_name ILIKE '%disposition%'
    OR column_name ILIKE '%methodology%'
    OR column_name ILIKE '%program%'
    OR column_name ILIKE '%cfda%'
    OR column_name ILIKE '%geograph%'
    OR column_name ILIKE '%state%'
    OR column_name ILIKE '%county%'
    OR column_name ILIKE '%award%'
    OR column_name ILIKE '%transaction%'
)
ORDER BY table_schema, table_name, ordinal_position;

\echo ''
\echo '3. CERTIFIED ASSISTANCE ACQUISITION BY FISCAL YEAR'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_rows,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT load_batch_id)
        AS load_batches,
    COUNT(DISTINCT BTRIM(cfda_number))
        AS distinct_programs,
    ROUND(
        SUM(federal_action_obligation)::numeric, 2
    ) AS net_obligations,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_obligation_rows,
    COUNT(*) FILTER (
        WHERE is_covid IS TRUE
    ) AS covid_rows,
    ROUND(
        COALESCE(
            SUM(federal_action_obligation) FILTER (
                WHERE is_covid IS TRUE
            ), 0
        )::numeric, 2
    ) AS covid_net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2025
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '4. CERTIFIED ASSISTANCE BY LOAD BATCH'

SELECT
    action_date_fiscal_year AS fiscal_year,
    load_batch_id,
    COUNT(*) AS transaction_rows,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(
        SUM(federal_action_obligation)::numeric, 2
    ) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2025
GROUP BY action_date_fiscal_year, load_batch_id
ORDER BY fiscal_year, load_batch_id;

\echo ''
\echo '5. PROGRAM POLICY COVERAGE BY FISCAL YEAR'

SELECT
    y.fiscal_year,
    COUNT(*) FILTER (
        WHERE m.resolved_accounting_disposition =
              'INCLUDE_ADDITIVE'
    ) AS additive_mapping_rows,
    COUNT(*) FILTER (
        WHERE m.resolved_accounting_disposition =
              'EXCLUDE_DUPLICATE'
    ) AS duplicate_mapping_rows,
    COUNT(*) FILTER (
        WHERE m.resolved_accounting_disposition =
              'WITHHOLD_UNRESOLVED'
    ) AS withheld_mapping_rows,
    COUNT(*) FILTER (
        WHERE m.resolved_accounting_disposition =
              'REFERENCE_ONLY'
    ) AS reference_mapping_rows,
    COUNT(*) AS total_applicable_mapping_rows
FROM generate_series(2018, 2025) AS y(fiscal_year)
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND y.fiscal_year >=
     COALESCE(m.valid_from_fiscal_year, 2018)
 AND y.fiscal_year <=
     COALESCE(m.valid_through_fiscal_year, 2025)
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;

\echo ''
\echo '6. ACCOUNTING VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname IN ('analysis', 'reporting')
  AND (
      viewname ILIKE '%assistance%'
      OR viewname ILIKE '%ledger%'
      OR viewname ILIKE '%fiscal_balance%'
  )
ORDER BY schemaname, viewname;

ROLLBACK;

\echo ''
\echo 'ETL-212A COMPLETE - NO DATABASE WRITES'
