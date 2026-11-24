\pset pager off
\set ON_ERROR_STOP on

\echo 'ETL-209 - HISTORICAL HCV RESOLUTION SCHEMA PREFLIGHT'
\echo 'READ ONLY'

BEGIN READ ONLY;

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (table_schema = 'analysis'
     AND table_name = 'v_certified_assistance_ledger'
     AND column_name IN (
         'assistance_transaction_id',
         'load_batch_id',
         'source_row_number',
         'action_date_fiscal_year',
         'cfda_number',
         'award_id_fain',
         'award_id_uri',
         'federal_action_obligation'
     ))
    OR
    (table_schema = 'reference'
     AND table_name IN (
         'federal_inflow_award_classification',
         'federal_inflow_program_policy_mapping'
     ))
ORDER BY
    table_schema,
    table_name,
    ordinal_position;

ROLLBACK;
