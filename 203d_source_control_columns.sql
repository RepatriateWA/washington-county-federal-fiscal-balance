BEGIN TRANSACTION READ ONLY;

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (table_schema = 'reference'
     AND table_name IN (
         'federal_inflow_source_policy',
         'federal_inflow_program_policy_mapping'
     ))
    OR
    (table_schema = 'cms'
     AND table_name IN (
         'medicare_geographic_payments',
         'medicaid_state_control_total'
     ))
    OR
    (table_schema = 'va'
     AND table_name = 'gdx_county_expenditure')
    OR
    (table_schema = 'irs'
     AND table_name = 'state_collections')
    OR
    (table_schema = 'analysis'
     AND table_name IN (
         'v_certified_assistance_ledger',
         'v_statewide_assistance_by_year',
         'v_wa_federal_wage_allocation',
         'v_wa_obligation_reconciliation'
     ))
    OR
    (table_schema = 'omb'
     AND table_name = 'v_federal_wage_obligation_control')
    OR
    (table_schema = 'opm'
     AND table_name = 'v_omb_civilian_wage_allocation')
    OR
    (table_schema = 'bea'
     AND table_name = 'v_omb_military_wage_allocation')
ORDER BY
    table_schema,
    table_name,
    ordinal_position;

COMMIT;