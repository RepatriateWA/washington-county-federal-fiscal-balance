
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218C - NUMERICAL RECONCILIATION PREFLIGHT'
\echo 'READ ONLY / NO LEDGER PROMOTION'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. CHIP CONTROL VIEW DEFINITION'

SELECT pg_get_viewdef(
    'chip.v_cms21_control_totals'::regclass, true
) AS view_definition;

\echo ''
\echo '2. CHIP CONTROL COLUMNS'

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'chip'
  AND table_name = 'v_cms21_control_totals'
ORDER BY ordinal_position;

\echo ''
\echo '3. EXISTING REPORTING VIEW DEFINITIONS'

SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    pg_get_viewdef(c.oid, true) AS view_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'reporting'
  AND c.relname IN (
      'v_federal_expenditures_by_state_year',
      'v_federal_expenditures_by_county_year',
      'v_washington_partial_fiscal_balance'
  )
  AND c.relkind = 'v'
ORDER BY c.relname;

\echo ''
\echo '4. MEDICAID SOURCE CONTROL ROWS'

SELECT
    m.fiscal_year,
    m.state_id,
    m.federal_program_id,
    m.federal_share,
    m.control_total_label,
    m.expenditure_time_basis,
    m.source_file,
    m.source_worksheet,
    m.source_row_number
FROM cms.medicaid_state_control_total m
JOIN reference.state_registry s
  ON s.state_id = m.state_id
WHERE s.state_abbreviation = 'WA'
  AND m.fiscal_year BETWEEN 2018 AND 2024
ORDER BY m.fiscal_year,m.medicaid_state_control_total_id;

\echo ''
\echo '5. CHIP CONTROL ROWS AND FILTERS'

SELECT
    fiscal_year,
    state_abbreviation,
    worksheet_type,
    federal_share,
    is_additive_expenditure,
    is_financing_adjustment,
    source_workbook,
    source_sheet,
    source_row
FROM chip.v_cms21_control_totals
WHERE state_abbreviation = 'WA'
  AND fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year,worksheet_type,source_workbook,source_row;

ROLLBACK;

\echo ''
\echo 'ETL-218C PREFLIGHT COMPLETE - READ ONLY'
