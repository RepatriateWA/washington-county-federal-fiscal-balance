
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219C1 - VA REPORTING OVERLAP PREFLIGHT'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. VA GDX ANNUAL REPORTING CONTROLS'

SELECT
    fiscal_year,
    COUNT(*) AS counties,
    SUM(va_gdx_expenditure_amount) AS va_expenditure_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. ALL VA-RELATED SOURCE POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family ILIKE '%VA%'
   OR inflow_subfamily ILIKE '%VA%'
   OR preferred_source ILIKE '%VA%'
   OR EXISTS (
       SELECT 1
       FROM unnest(overlapping_sources) AS s(source_name)
       WHERE s.source_name ILIKE '%VA%'
   )
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year,
    methodology_version;

\echo ''
\echo '3. VA-RELATED USAspending PROGRAM MAPPINGS'

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE p.inflow_family ILIKE '%VA%'
   OR p.inflow_subfamily ILIKE '%VA%'
   OR p.preferred_source ILIKE '%VA%'
ORDER BY
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.methodology_version;

\echo ''
\echo '4. EXISTING VA REPORTING COMPONENTS'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    expenditure_dollars,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE agency_code ILIKE '%VA%'
   OR program_code ILIKE '%VA%'
   OR program_name ILIKE '%veteran%'
ORDER BY report_year,program_code;

\echo ''
\echo '5. SOURCE POLICY COVERAGE GATE'

DO $gate$
DECLARE
    v_bad_years bigint;
    v_existing_va bigint;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION
            'BLOCK: transaction not read-only';
    END IF;

    WITH years AS (
        SELECT generate_series(2018,2024) AS fiscal_year
    ),
    coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(p.federal_inflow_source_policy_id)
                AS applicable_policies
        FROM years y
        LEFT JOIN reference.federal_inflow_source_policy p
          ON p.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
         AND p.preferred_source = 'VA_GDX'
         AND p.accounting_measure = 'ANNUAL_EXPENDITURES'
         AND y.fiscal_year BETWEEN
             p.valid_from_fiscal_year
             AND p.valid_through_fiscal_year
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*) INTO v_bad_years
    FROM coverage
    WHERE applicable_policies <> 1;

    SELECT COUNT(*) INTO v_existing_va
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
      AND (
          agency_code ILIKE '%VA%'
          OR program_code ILIKE '%VA%'
          OR program_name ILIKE '%veteran%'
      );

    IF v_bad_years IS DISTINCT FROM 0
       OR v_existing_va IS DISTINCT FROM 0
    THEN
        RAISE EXCEPTION
            'BLOCK: policy coverage failures %, existing VA reporting rows %',
            v_bad_years,v_existing_va;
    END IF;

    RAISE NOTICE
        'ETL-219C1 PASS: one VA GDX source policy per year; no existing VA reporting component';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219C1 COMPLETE - READ ONLY'
