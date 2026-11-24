\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221H - ASSISTANCE ACCOUNTING BRIDGE INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'

\echo ''
\echo '1. ACCOUNTING-RELATED VIEWS'

SELECT
    schemaname,
    viewname
FROM pg_views
WHERE schemaname IN ('analysis', 'assistance', 'reporting')
  AND (
       viewname ILIKE '%account%'
    OR viewname ILIKE '%bridge%'
    OR viewname ILIKE '%assist%'
    OR viewname ILIKE '%classif%'
  )
ORDER BY schemaname, viewname;

\echo ''
\echo '2. EXISTING PROGRAM MAPPING COVERAGE BY YEAR'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    m.resolved_accounting_disposition,
    COUNT(*) AS applicable_mappings,
    COUNT(DISTINCT m.source_program_code) AS distinct_programs
FROM years y
JOIN reference.federal_inflow_program_policy_mapping m
  ON y.fiscal_year BETWEEN
     m.valid_from_fiscal_year
     AND m.valid_through_fiscal_year
GROUP BY
    y.fiscal_year,
    m.resolved_accounting_disposition
ORDER BY
    y.fiscal_year,
    m.resolved_accounting_disposition;

\echo ''
\echo '3. AWARD-LEVEL CLASSIFICATION COVERAGE'

SELECT
    accounting_disposition,
    COUNT(*) AS classification_rows,
    COUNT(DISTINCT source_award_identifier) AS distinct_awards,
    MIN(valid_from_fiscal_year) AS first_year,
    MAX(valid_through_fiscal_year) AS last_year
FROM reference.federal_inflow_award_classification
WHERE valid_from_fiscal_year <= 2024
  AND valid_through_fiscal_year >= 2018
GROUP BY accounting_disposition
ORDER BY accounting_disposition;

\echo ''
\echo '4. ASSISTANCE VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname IN ('analysis', 'assistance', 'reporting')
  AND (
       viewname ILIKE '%account%bridge%'
    OR viewname ILIKE '%assist%ledger%'
    OR viewname ILIKE '%assist%account%'
  )
ORDER BY schemaname, viewname;

ROLLBACK;