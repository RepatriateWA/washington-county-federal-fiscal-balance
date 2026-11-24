
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219A1 - STATEWIDE EXPENDITURE SOURCE INVENTORY'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER CHANGES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. DATABASE AND SESSION CONTROLS'

SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('transaction_read_only')
        AS transaction_read_only,
    current_setting('server_version') AS postgres_version;

\echo ''
\echo '2. REPORTING VIEW INVENTORY'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
    END AS relation_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'reporting'
  AND c.relkind IN ('v','m')
ORDER BY c.relname;

\echo ''
\echo '3. SOURCE-FAMILY RELATION INVENTORY'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
    END AS relation_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp_%'
  AND c.relkind IN ('r','p','v','m')
  AND (
      n.nspname IN (
          'ssa','cms','medicare','medicaid',
          'chip','va','usa','assistance',
          'irs','bea','rrb','treasury',
          'reporting','analysis'
      )
      OR c.relname ~* (
          'federal|expenditure|spend|payment|' ||
          'benefit|compensation|outlay|obligation'
      )
  )
ORDER BY n.nspname, c.relname;

\echo ''
\echo '4. COLUMNS OF RELEVANT REPORTING VIEWS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reporting'
  AND (
      table_name ~* (
          'expenditure|fiscal_balance|revenue|' ||
          'medicaid|chip|medicare|ssa|va'
      )
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '5. ACCOUNTING POLICY STRUCTURE'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_award_classification'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '6. CURRENT REPORTING EXPENDITURE COMPONENTS'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    COUNT(*) AS observation_count,
    SUM(expenditure_dollars::numeric)
        AS reported_expenditure_dollars,
    MIN(measure_note) AS example_measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY
    report_year,
    agency_code,
    program_code,
    program_name
ORDER BY
    report_year,
    agency_code,
    program_code;

\echo ''
\echo '7. CURRENT ANNUAL PARTIAL-BALANCE TOTALS'

SELECT
    report_year,
    gross_collections_dollars,
    tracked_expenditures_dollars,
    partial_fiscal_balance_dollars
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year;

\echo ''
\echo '8. SOURCE POLICY FAMILIES AND TREATMENTS'

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
WHERE valid_from_fiscal_year <= 2024
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
\echo '9. USAspending POLICY CLASSIFICATION SUMMARY'

SELECT
    source_system,
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS award_classification_rows
FROM reference.federal_inflow_award_classification
WHERE valid_from_fiscal_year <= 2024
  AND (
      valid_through_fiscal_year IS NULL
      OR valid_through_fiscal_year >= 2018
  )
GROUP BY
    source_system,
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY
    source_system,
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year;

\echo ''
\echo '10. FAIL-CLOSED BASELINE CONTROL'

DO $gate$
DECLARE
    v_years integer;
    v_components integer;
    v_revenue numeric;
    v_expenditures numeric;
    v_balance numeric;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION
            'ETL-219A1 BLOCK: transaction is not read-only';
    END IF;

    SELECT
        COUNT(*),
        SUM(gross_collections_dollars::numeric),
        SUM(tracked_expenditures_dollars::numeric),
        SUM(partial_fiscal_balance_dollars::numeric)
    INTO
        v_years,
        v_revenue,
        v_expenditures,
        v_balance
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024;

    SELECT COUNT(*)
    INTO v_components
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024;

    IF v_years <> 7
       OR v_components <> 42
       OR v_revenue IS DISTINCT FROM 877156759000
       OR v_expenditures IS DISTINCT FROM 323024861111
       OR v_balance IS DISTINCT FROM 554131897889
    THEN
        RAISE EXCEPTION
            'ETL-219A1 BLOCK: reporting baseline changed; years %, components %, revenue %, expenditures %, balance %',
            v_years,
            v_components,
            v_revenue,
            v_expenditures,
            v_balance;
    END IF;

    RAISE NOTICE
        'ETL-219A1 PASS: baseline unchanged; 7 years, 42 reporting components';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219A1 COMPLETE - READ ONLY'
