\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-220D - VA FINAL-LEDGER AUTHORIZATION PREFLIGHT'
\echo 'FY2018-FY2024 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. SOURCE INTEGRITY - COUNTY AND FINANCIAL CONTROLS'

WITH county AS (
    SELECT
        e.fiscal_year,
        e.county_id,
        COUNT(*) AS source_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
              AND e.expenditure_amount IS NULL
        ) AS null_controls,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_dollars,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_dollars
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year BETWEEN 2018 AND 2024
    GROUP BY e.fiscal_year, e.county_id
),
checked AS (
    SELECT
        c.*,
        v.va_gdx_expenditure_amount AS reporting_dollars
    FROM county c
    LEFT JOIN va.v_washington_county_gdx_control_total v
      ON v.fiscal_year = c.fiscal_year
     AND v.county_id = c.county_id
)
SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    COUNT(*) FILTER (
        WHERE component_dollars IS DISTINCT FROM control_dollars
           OR control_dollars IS DISTINCT FROM reporting_dollars
           OR null_controls <> 0
    ) AS financial_exceptions,
    SUM(reporting_dollars) AS va_gdx_dollars
FROM checked
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. TOTAL VA SOURCE POLICY - EXACTLY ONE PER YEAR'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.federal_inflow_source_policy_id) AS policy_count,
    STRING_AGG(
        p.methodology_version, ', '
        ORDER BY p.methodology_version
    ) AS methodology_versions,
    STRING_AGG(
        p.ledger_treatment, ', '
        ORDER BY p.methodology_version
    ) AS ledger_treatments
FROM years y
LEFT JOIN reference.federal_inflow_source_policy p
  ON p.inflow_family = 'VETERANS_AFFAIRS'
 AND p.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
 AND p.preferred_source = 'VA_GDX'
 AND p.accounting_measure = 'ANNUAL_EXPENDITURES'
 AND y.fiscal_year BETWEEN
     p.valid_from_fiscal_year
     AND p.valid_through_fiscal_year
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;

\echo ''
\echo '3. ASSISTANCE OVERLAP - POLICY DISPOSITIONS'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    m.resolved_accounting_disposition,
    COUNT(DISTINCT m.source_program_code) AS distinct_programs
FROM years y
JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND y.fiscal_year BETWEEN
     m.valid_from_fiscal_year
     AND m.valid_through_fiscal_year
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE p.inflow_family = 'VETERANS_AFFAIRS'
GROUP BY
    y.fiscal_year,
    m.resolved_accounting_disposition
ORDER BY
    y.fiscal_year,
    m.resolved_accounting_disposition;

\echo ''
\echo '4. CURRENT VA REPORTING BOUNDARY'

SELECT
    COUNT(*) AS existing_va_reporting_rows
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
  AND (
      agency_code ILIKE '%VA%'
      OR program_code ILIKE '%VA%'
      OR program_name ILIKE '%veteran%'
  );

\echo ''
\echo '5. INDEPENDENT FAIL-CLOSED STRUCTURAL GATE'

DO $gate$
DECLARE
    v_county_years bigint;
    v_financial_exceptions bigint;
    v_bad_policy_years bigint;
    v_existing_va_rows bigint;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'BLOCK: transaction is not read-only';
    END IF;

    WITH county AS (
        SELECT
            e.fiscal_year,
            e.county_id,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
                  AND e.expenditure_amount IS NULL
            ) AS null_controls,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS components,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS controls
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2018 AND 2024
        GROUP BY e.fiscal_year, e.county_id
    )
    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE c.components IS DISTINCT FROM c.controls
               OR c.controls IS DISTINCT FROM
                  v.va_gdx_expenditure_amount
               OR c.null_controls <> 0
        )
    INTO v_county_years, v_financial_exceptions
    FROM county c
    LEFT JOIN va.v_washington_county_gdx_control_total v
      ON v.fiscal_year = c.fiscal_year
     AND v.county_id = c.county_id;

    WITH years AS (
        SELECT generate_series(2018, 2024) AS fiscal_year
    ),
    coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(p.federal_inflow_source_policy_id) AS policies
        FROM years y
        LEFT JOIN reference.federal_inflow_source_policy p
          ON p.inflow_family = 'VETERANS_AFFAIRS'
         AND p.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
         AND p.preferred_source = 'VA_GDX'
         AND p.accounting_measure = 'ANNUAL_EXPENDITURES'
         AND p.ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
         AND 'USASPENDING_PROCUREMENT' =
             ANY(p.overlapping_sources)
         AND y.fiscal_year BETWEEN
             p.valid_from_fiscal_year
             AND p.valid_through_fiscal_year
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*)
    INTO v_bad_policy_years
    FROM coverage
    WHERE policies <> 1;

    SELECT COUNT(*)
    INTO v_existing_va_rows
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
      AND (
          agency_code ILIKE '%VA%'
          OR program_code ILIKE '%VA%'
          OR program_name ILIKE '%veteran%'
      );

    IF v_county_years <> 273
       OR v_financial_exceptions <> 0
       OR v_bad_policy_years <> 0
       OR v_existing_va_rows <> 0
    THEN
        RAISE EXCEPTION
          'BLOCK: county-years %, financial exceptions %, policy failures %, existing VA rows %',
          v_county_years,
          v_financial_exceptions,
          v_bad_policy_years,
          v_existing_va_rows;
    END IF;

    RAISE NOTICE
      'ETL-220D STRUCTURAL PASS: source, policy and reporting boundary verified; final additive authorization NOT granted';
END
$gate$;

\echo ''
\echo '6. AUTHORIZATION DECISION REGISTER'
\echo 'SOURCE_INTEGRITY: PASS only if structural gate succeeds'
\echo 'SOURCE_POLICY_COVERAGE: PASS only if structural gate succeeds'
\echo 'PROCUREMENT_OVERLAP: POLICY VERIFIED; NO INDEPENDENT ADDITION'
\echo 'ASSISTANCE_OVERLAP: REVIEW UNRESOLVED POPULATION'
\echo 'CROSS_FAMILY_OVERLAP: NOT YET CERTIFIED'
\echo 'FINAL_LEDGER_AUTHORIZATION: WITHHELD'

ROLLBACK;

\echo ''
\echo 'ETL-220D COMPLETE - READ ONLY'