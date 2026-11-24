
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219B1 - VA GDX REPORTING READINESS'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. ANNUAL VA GDX COUNTY CONTROL TOTALS'

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT county_id) AS distinct_counties,
    SUM(va_gdx_expenditure_amount)
        AS statewide_va_gdx_dollars,
    MIN(va_gdx_expenditure_amount)
        AS minimum_county_dollars,
    MAX(va_gdx_expenditure_amount)
        AS maximum_county_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. DUPLICATE COUNTY-YEAR KEYS'

SELECT
    fiscal_year,
    county_id,
    COUNT(*) AS duplicate_rows
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year, county_id
HAVING COUNT(*) <> 1
ORDER BY fiscal_year, county_id;

\echo ''
\echo '3. SOURCE EXPENDITURE CLASSES BY YEAR'

SELECT
    fiscal_year,
    schema_regime,
    expenditure_class,
    COUNT(*) AS source_rows,
    COUNT(DISTINCT county_id) AS counties,
    SUM(expenditure_amount)
        AS expenditure_dollars
FROM va.gdx_county_expenditure
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY
    fiscal_year,
    schema_regime,
    expenditure_class
ORDER BY
    fiscal_year,
    schema_regime,
    expenditure_class;

\echo ''
\echo '4. VA SOURCE POLICIES'

SELECT
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
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
  AND valid_from_fiscal_year <= 2024
  AND (
      valid_through_fiscal_year IS NULL
      OR valid_through_fiscal_year >= 2018
  )
ORDER BY valid_from_fiscal_year;

\echo ''
\echo '5. EXISTING VA REPORTING COMPONENTS'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    SUM(expenditure_dollars)
        AS reporting_dollars
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
  AND (
      agency_code ILIKE '%VA%'
      OR program_code ILIKE '%VA%'
  )
GROUP BY
    report_year,
    agency_code,
    program_code,
    program_name
ORDER BY report_year, program_code;

\echo ''
\echo '6. VA COUNTY COVERAGE AND POLICY GATE'

DO $gate$
DECLARE
    v_bad_years integer;
    v_bad_counties integer;
    v_bad_policy_years integer;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION
            'ETL-219B1 BLOCK: transaction not read-only';
    END IF;

    WITH years AS (
        SELECT generate_series(2018,2024)::integer
            AS fiscal_year
    ),
    coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(v.county_id) AS rows_found,
            COUNT(DISTINCT v.county_id)
                AS counties_found
        FROM years y
        LEFT JOIN va.v_washington_county_gdx_control_total v
            ON v.fiscal_year = y.fiscal_year
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*)
    INTO v_bad_years
    FROM coverage
    WHERE rows_found <> 39
       OR counties_found <> 39;

    SELECT COUNT(*)
    INTO v_bad_counties
    FROM (
        SELECT fiscal_year, county_id
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year, county_id
        HAVING COUNT(*) <> 1
    ) d;

    WITH years AS (
        SELECT generate_series(2018,2024)::integer
            AS fiscal_year
    ),
    policy_coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(p.federal_inflow_source_policy_id)
                AS applicable_policies
        FROM years y
        LEFT JOIN reference.federal_inflow_source_policy p
            ON p.inflow_family = 'VETERANS_AFFAIRS'
           AND p.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
           AND p.valid_from_fiscal_year <= y.fiscal_year
           AND (
               p.valid_through_fiscal_year IS NULL
               OR p.valid_through_fiscal_year >= y.fiscal_year
           )
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*)
    INTO v_bad_policy_years
    FROM policy_coverage
    WHERE applicable_policies <> 1;

    IF v_bad_years <> 0
       OR v_bad_counties <> 0
       OR v_bad_policy_years <> 0
    THEN
        RAISE EXCEPTION
            'ETL-219B1 BLOCK: county coverage %, duplicate keys %, policy years %',
            v_bad_years,
            v_bad_counties,
            v_bad_policy_years;
    END IF;

    RAISE NOTICE
        'ETL-219B1 PASS: 39 county controls and one source policy per year';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219B1 COMPLETE - READ ONLY'
