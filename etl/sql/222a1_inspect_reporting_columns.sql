\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-222A1 - REPORTING INTERFACE INSPECTION'
\echo 'READ ONLY'

BEGIN TRANSACTION READ ONLY;

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (table_schema = 'reporting'
     AND table_name IN (
         'v_washington_revenue_summary',
         'v_washington_tracked_expenditures',
         'v_washington_partial_fiscal_balance'
     ))
    OR
    (table_schema = 'va'
     AND table_name = 'v_washington_county_gdx_control_total')
    OR
    (table_schema = 'analysis'
     AND table_name = 'v_wa_federal_wage_allocation')
ORDER BY
    table_schema,
    table_name,
    ordinal_position;

ROLLBACK;

\echo 'ETL-222A1 COMPLETE'