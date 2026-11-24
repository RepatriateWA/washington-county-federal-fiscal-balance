
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215A - STATEWIDE ACCOUNTING READINESS'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. REPORTING RELATION INVENTORY'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind AS relation_kind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (
    (n.nspname = 'reporting'
     AND c.relname IN (
         'v_washington_partial_fiscal_balance',
         'v_washington_tracked_expenditures',
         'v_washington_revenue_summary',
         'v_washington_ssa_summary',
         'v_medicare_expenditures_by_state_year',
         'v_washington_medicaid_expenditures',
         'v_washington_chip_expenditures'
     ))
    OR (n.nspname = 'cms'
        AND c.relname = 'medicare_core_state_year')
    OR (n.nspname = 'analysis'
        AND c.relname = 'v_wa_federal_wage_allocation')
    OR (n.nspname = 'va'
        AND c.relname =
            'v_washington_county_gdx_control_total')
)
ORDER BY 1,2;

\echo ''
\echo '2. CURRENT PARTIAL BALANCE'
\echo 'DIAGNOSTIC ONLY - NOT FINAL LEDGER'

SELECT *
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year;

\echo ''
\echo '3. EXISTING TRACKED EXPENDITURE COMPONENTS'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    expenditure_dollars,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year, agency_code, program_code;

\echo ''
\echo '4. IRS RECEIPTS - STATEWIDE CONTROL'

SELECT
    fiscal_year,
    gross_collections_dollars
FROM reporting.v_washington_revenue_summary
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '5. SSA OASDI - ANNUALIZED DECEMBER SNAPSHOTS'

SELECT
    report_year,
    program_code,
    program_name,
    annualized_benefits_dollars
FROM reporting.v_washington_ssa_summary
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year, program_code;

\echo ''
\echo '6. MEDICAID - FEDERAL SHARE / FFY'

SELECT
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '7. CHIP - FEDERAL SHARE / FFY'

SELECT
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance,
    measure_note
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '8. FEDERAL WAGES - ALLOCATED FFY CONTROLS'

SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars,
    civilian_allocation_confidence,
    military_allocation_confidence,
    combined_allocation_confidence,
    civilian_value_status,
    military_value_status,
    certification_methodology_version
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '9. VA GDX - STATEWIDE CONTROL FROM COUNTY RECORDS'

SELECT
    fiscal_year,
    COUNT(DISTINCT county_id) AS county_count,
    SUM(va_gdx_expenditure_amount) AS statewide_expenditure
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '10. MEDICARE CORE - COLUMN INVENTORY'
\echo 'No assumptions about stored component columns'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'cms'
  AND table_name = 'medicare_core_state_year'
ORDER BY ordinal_position;

\echo ''
\echo '11. USAspending ASSISTANCE - ANNUAL GROSS CONTROLS'
\echo 'OBLIGATIONS ONLY - NOT ADDITIVE AS A WHOLE'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT TRIM(cfda_number))
        AS distinct_programs,
    SUM(federal_action_obligation)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
  AND reference_state_abbreviation = 'WA'
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '12. PROCUREMENT - ANNUAL GROSS CONTROLS'
\echo 'OBLIGATIONS ONLY - NOT ADDITIVE AS A WHOLE'

SELECT
    fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT award_id) AS award_count,
    SUM(federal_action_obligation) AS net_obligations
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '13. HISTORICAL FY2018-2019 POLICY EXTENSION'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.methodology_version
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-214M2B-v1'
ORDER BY m.source_program_code;

\echo ''
\echo '14. SOURCE POLICY TREATMENT INVENTORY'

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
WHERE (
    valid_from_fiscal_year IS NULL
    OR valid_from_fiscal_year <= 2024
)
AND (
    valid_through_fiscal_year IS NULL
    OR valid_through_fiscal_year >= 2018
)
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year,
    methodology_version;

\echo ''
\echo '15. CURRENT REPORTING VIEW DEFINITION'
\echo 'Inspect actual database definition, not only Git history'

SELECT pg_get_viewdef(
    'reporting.v_washington_partial_fiscal_balance'::regclass,
    true
) AS current_view_definition;

ROLLBACK;

\echo ''
\echo 'ETL-215A COMPLETE - READ ONLY'
