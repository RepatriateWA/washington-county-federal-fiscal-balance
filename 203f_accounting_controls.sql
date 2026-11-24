BEGIN TRANSACTION READ ONLY;

\echo '=== 1. VA CONTROL TOTAL VIEW ==='
SELECT
    pg_get_viewdef('va.v_washington_county_gdx_control_total'::regclass, true)
    AS definition;

\echo '=== 2. OBLIGATION RECONCILIATION VIEW ==='
SELECT
    pg_get_viewdef('analysis.v_wa_obligation_reconciliation'::regclass, true)
    AS definition;

\echo '=== 3. VA CONTROL TOTAL COLUMNS ==='
SELECT
    ordinal_position, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'va'
  AND table_name = 'v_washington_county_gdx_control_total'
ORDER BY ordinal_position;

\echo '=== 4. SOURCE ACCOUNTING POLICIES ==='
SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_source_policy
ORDER BY inflow_family, inflow_subfamily,
         valid_from_fiscal_year;

COMMIT;