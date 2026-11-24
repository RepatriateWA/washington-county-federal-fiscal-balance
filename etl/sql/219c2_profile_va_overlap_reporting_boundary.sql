
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219C2 - VA OVERLAP AND REPORTING BOUNDARY'
\echo 'FY2018-FY2024 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. REPORTING VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'reporting'
  AND viewname IN (
      'v_washington_tracked_expenditures',
      'v_washington_partial_fiscal_balance'
  )
ORDER BY viewname;

\echo ''
\echo '2. PROCUREMENT AND ASSISTANCE RELATION INVENTORY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN ('usa','va','assistance','analysis')
  AND (
      table_name ILIKE '%procurement%'
      OR table_name ILIKE '%award%'
      OR table_name ILIKE '%assistance%'
      OR table_name ILIKE '%overlap%'
  )
ORDER BY table_schema,table_name;

\echo ''
\echo '3. PROCUREMENT AND ASSISTANCE COLUMN INVENTORY'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema IN (
    'usa','va','assistance','analysis','reference'
)
AND (
    table_name ILIKE '%procurement%'
    OR table_name ILIKE '%award%'
    OR table_name IN (
        'v_certified_assistance_ledger',
        'federal_inflow_source_policy',
        'federal_inflow_program_policy_mapping',
        'federal_inflow_award_classification'
    )
)
AND (
    column_name ILIKE '%agency%'
    OR column_name ILIKE '%va%'
    OR column_name ILIKE '%fiscal%'
    OR column_name ILIKE '%obligation%'
    OR column_name ILIKE '%outlay%'
    OR column_name ILIKE '%disposition%'
    OR column_name ILIKE '%award%'
    OR column_name ILIKE '%source%'
    OR column_name ILIKE '%amount%'
)
ORDER BY table_schema,table_name,ordinal_position;

\echo ''
\echo '4. VA PROCUREMENT SOURCE POLICY BY YEAR'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.federal_inflow_source_policy_id)
        AS matching_va_gdx_policies,
    STRING_AGG(
        DISTINCT p.methodology_version,
        ', ' ORDER BY p.methodology_version
    ) AS policy_versions,
    STRING_AGG(
        DISTINCT p.ledger_treatment,
        ', ' ORDER BY p.ledger_treatment
    ) AS treatments
FROM years y
LEFT JOIN reference.federal_inflow_source_policy p
  ON p.inflow_family = 'VETERANS_AFFAIRS'
 AND p.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
 AND p.preferred_source = 'VA_GDX'
 AND p.accounting_measure = 'ANNUAL_EXPENDITURES'
 AND 'USASPENDING_PROCUREMENT' = ANY(p.overlapping_sources)
 AND y.fiscal_year BETWEEN
     p.valid_from_fiscal_year
     AND p.valid_through_fiscal_year
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;

\echo ''
\echo '5. VA ASSISTANCE POLICY DISPOSITION COVERAGE'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    m.resolved_accounting_disposition,
    COUNT(DISTINCT m.source_program_code)
        AS distinct_programs,
    COUNT(*) AS applicable_policy_mappings
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
\echo '6. VA AWARD-LEVEL CLASSIFICATION SUMMARY'

SELECT
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS classification_rows,
    COUNT(DISTINCT source_award_identifier)
        AS distinct_award_identifiers
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND inflow_family = 'VETERANS_AFFAIRS'
  AND valid_from_fiscal_year <= 2024
  AND valid_through_fiscal_year >= 2018
GROUP BY
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY
    valid_from_fiscal_year,
    accounting_disposition,
    methodology_version;

\echo ''
\echo '7. READ-ONLY REPORTING BOUNDARY GATE'

DO $gate$
DECLARE
    v_policy_failures bigint;
    v_va_reporting_rows bigint;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION
            'BLOCK: transaction is not read-only';
    END IF;

    WITH years AS (
        SELECT generate_series(2018,2024) AS fiscal_year
    ),
    coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(p.federal_inflow_source_policy_id)
                AS policy_count
        FROM years y
        LEFT JOIN reference.federal_inflow_source_policy p
          ON p.inflow_family = 'VETERANS_AFFAIRS'
         AND p.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
         AND p.preferred_source = 'VA_GDX'
         AND p.accounting_measure = 'ANNUAL_EXPENDITURES'
         AND p.ledger_treatment =
             'INCLUDE_AFTER_RECONCILIATION'
         AND 'USASPENDING_PROCUREMENT' =
             ANY(p.overlapping_sources)
         AND y.fiscal_year BETWEEN
             p.valid_from_fiscal_year
             AND p.valid_through_fiscal_year
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*) INTO v_policy_failures
    FROM coverage
    WHERE policy_count <> 1;

    SELECT COUNT(*) INTO v_va_reporting_rows
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
      AND (
          agency_code ILIKE '%VA%'
          OR program_code ILIKE '%VA%'
          OR program_name ILIKE '%veteran%'
      );

    IF v_policy_failures IS DISTINCT FROM 0
       OR v_va_reporting_rows IS DISTINCT FROM 0
    THEN
        RAISE EXCEPTION
            'BLOCK: procurement-policy coverage failures %, existing VA reporting rows %',
            v_policy_failures,
            v_va_reporting_rows;
    END IF;

    RAISE NOTICE
        'ETL-219C2 PASS: procurement overlap policy coverage and current reporting boundary verified; additive inclusion NOT authorized';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219C2 COMPLETE - READ ONLY'
