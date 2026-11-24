
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219A2 - EXPENDITURE COVERAGE AND BASIS GAP PROFILE'
\echo 'FY2018-FY2024 / READ ONLY / NO ACCOUNTING DECISIONS'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. REPORTED COMPONENT COVERAGE BY YEAR'

WITH components AS (
    SELECT
        report_year,
        CASE
            WHEN agency_code = 'SSA'
                THEN 'SSA_OASDI'
            WHEN agency_code = 'CMS'
                 AND program_code = 'MEDICARE'
                THEN 'MEDICARE_ORIGINAL'
            WHEN agency_code = 'CMS'
                 AND program_code = 'MEDICAID'
                THEN 'CMS_MEDICAID'
            WHEN agency_code = 'CMS'
                 AND program_code = 'CHIP'
                THEN 'CMS_CHIP'
            ELSE 'OTHER_REPORTED'
        END AS source_family,
        expenditure_dollars::numeric AS dollars
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
)
SELECT
    report_year,
    source_family,
    COUNT(*) AS component_rows,
    SUM(dollars) AS reported_dollars
FROM components
GROUP BY report_year, source_family
ORDER BY report_year, source_family;

\echo ''
\echo '2. CURRENT ANNUAL COVERAGE MATRIX'

SELECT
    report_year,
    SUM(expenditure_dollars::numeric)
        FILTER (WHERE agency_code = 'SSA')
        AS ssa_oasdi_annualized,
    SUM(expenditure_dollars::numeric)
        FILTER (
            WHERE agency_code = 'CMS'
              AND program_code = 'MEDICARE'
        ) AS original_medicare_calendar_year,
    SUM(expenditure_dollars::numeric)
        FILTER (
            WHERE agency_code = 'CMS'
              AND program_code = 'MEDICAID'
        ) AS medicaid_federal_fiscal_year,
    SUM(expenditure_dollars::numeric)
        FILTER (
            WHERE agency_code = 'CMS'
              AND program_code = 'CHIP'
        ) AS chip_federal_fiscal_year,
    SUM(expenditure_dollars::numeric)
        AS current_reported_total
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY report_year
ORDER BY report_year;

\echo ''
\echo '3. REPORTING COMPONENT MEASURE NOTES'

SELECT DISTINCT
    agency_code,
    program_code,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY agency_code, program_code, measure_note;

\echo ''
\echo '4. SOURCE POLICY COVERAGE BY FISCAL YEAR'

WITH years AS (
    SELECT generate_series(2018,2024)::integer
        AS fiscal_year
)
SELECT
    y.fiscal_year,
    p.inflow_family,
    p.accounting_measure,
    p.ledger_treatment,
    COUNT(*) AS applicable_policy_rows,
    COUNT(DISTINCT p.inflow_subfamily)
        AS distinct_subfamilies
FROM years y
JOIN reference.federal_inflow_source_policy p
    ON p.valid_from_fiscal_year <= y.fiscal_year
   AND (
       p.valid_through_fiscal_year IS NULL
       OR p.valid_through_fiscal_year >= y.fiscal_year
   )
GROUP BY
    y.fiscal_year,
    p.inflow_family,
    p.accounting_measure,
    p.ledger_treatment
ORDER BY
    y.fiscal_year,
    p.inflow_family,
    p.ledger_treatment;

\echo ''
\echo '5. SOURCE POLICIES REQUIRING RECONCILIATION OR REVIEW'

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
  AND (
      ledger_treatment IN (
          'INCLUDE_AFTER_RECONCILIATION',
          'REVIEW_REQUIRED',
          'SEPARATE_CONTINGENT_MEASURE'
      )
      OR accounting_measure IN (
          'NET_FEDERAL_ACTION_OBLIGATION',
          'FEDERAL_WAGE_OBLIGATIONS'
      )
  )
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year;

\echo ''
\echo '6. SOURCE RELATIONS REQUIRING DETAILED FOLLOW-UP'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind AS relation_kind,
    STRING_AGG(
        a.attname || ' (' ||
        format_type(a.atttypid,a.atttypmod) || ')',
        ', ' ORDER BY a.attnum
    ) AS columns
FROM pg_class c
JOIN pg_namespace n
    ON n.oid = c.relnamespace
JOIN pg_attribute a
    ON a.attrelid = c.oid
WHERE c.relkind IN ('r','p','v','m')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND (
      (n.nspname = 'va'
       AND c.relname IN (
           'v_washington_county_gdx_control_total',
           'gdx_county_expenditure'
       ))
      OR (n.nspname = 'bea'
          AND c.relname IN (
              'v_omb_military_wage_allocation',
              'compensation_observation'
          ))
      OR (n.nspname = 'omb'
          AND c.relname =
              'v_federal_wage_obligation_control')
      OR (n.nspname = 'cms'
          AND c.relname IN (
              'medicare_core_state_year',
              'medicare_geographic_payments'
          ))
      OR (n.nspname = 'analysis'
          AND c.relname IN (
              'v_statewide_assistance_by_year',
              'v_wa_federal_wage_allocation'
          ))
  )
GROUP BY n.nspname,c.relname,c.relkind
ORDER BY n.nspname,c.relname;

\echo ''
\echo '7. INDEPENDENT BASELINE AND STRUCTURAL GATE'

DO $gate$
DECLARE
    v_years integer;
    v_components integer;
    v_bad_years integer;
    v_bad_components integer;
    v_revenue numeric;
    v_spending numeric;
    v_balance numeric;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION
            'ETL-219A2 BLOCK: transaction not read-only';
    END IF;

    SELECT
        COUNT(*),
        SUM(gross_collections_dollars::numeric),
        SUM(tracked_expenditures_dollars::numeric),
        SUM(partial_fiscal_balance_dollars::numeric)
    INTO
        v_years,
        v_revenue,
        v_spending,
        v_balance
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024;

    SELECT COUNT(*)
    INTO v_components
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024;

    WITH annual AS (
        SELECT
            report_year,
            COUNT(*) AS n,
            COUNT(*) FILTER (
                WHERE agency_code = 'SSA'
            ) AS ssa_n,
            COUNT(*) FILTER (
                WHERE agency_code = 'CMS'
                  AND program_code IN (
                      'MEDICARE','MEDICAID','CHIP'
                  )
            ) AS cms_n
        FROM reporting.v_washington_tracked_expenditures
        WHERE report_year BETWEEN 2018 AND 2024
        GROUP BY report_year
    )
    SELECT COUNT(*)
    INTO v_bad_years
    FROM annual
    WHERE n <> 6
       OR ssa_n <> 3
       OR cms_n <> 3;

    WITH keys AS (
        SELECT
            report_year,
            agency_code,
            program_code,
            COUNT(*) AS n
        FROM reporting.v_washington_tracked_expenditures
        WHERE report_year BETWEEN 2018 AND 2024
        GROUP BY report_year,agency_code,program_code
    )
    SELECT COUNT(*)
    INTO v_bad_components
    FROM keys
    WHERE n <> 1;

    IF v_years <> 7
       OR v_components <> 42
       OR v_bad_years <> 0
       OR v_bad_components <> 0
       OR v_revenue IS DISTINCT FROM 877156759000
       OR v_spending IS DISTINCT FROM 323024861111
       OR v_balance IS DISTINCT FROM 554131897889
    THEN
        RAISE EXCEPTION
            'ETL-219A2 BLOCK: baseline or structure mismatch';
    END IF;

    RAISE NOTICE
        'ETL-219A2 PASS: coverage profiled; baseline and component uniqueness preserved';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219A2 COMPLETE - READ ONLY'
