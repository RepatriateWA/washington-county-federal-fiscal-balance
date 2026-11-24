
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-213Y2 v0.1 - HISTORICAL VA PROCUREMENT POLICY PREFLIGHT'
\echo 'ANALYSIS-213-v1 | FY2018-FY2019 | READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. All existing VA source policies'

SELECT
    federal_inflow_source_policy_id,
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
WHERE inflow_family = 'VETERANS_AFFAIRS'
ORDER BY
    inflow_subfamily,
    valid_from_fiscal_year,
    federal_inflow_source_policy_id;

\echo ''
\echo '2. Existing total-VA-expenditures policy and overlaps'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    source_selection_basis
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND (
      inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      OR (
          valid_from_fiscal_year <= 2019
          AND valid_through_fiscal_year >= 2018
          AND overlapping_sources @>
              ARRAY['USASPENDING_PROCUREMENT']::text[]
      )
  )
ORDER BY valid_from_fiscal_year,
         federal_inflow_source_policy_id;

\echo ''
\echo '3. Proposed-policy exact identity and year-overlap counts'

SELECT
    COUNT(*) FILTER (
        WHERE inflow_family = 'VETERANS_AFFAIRS'
          AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
          AND methodology_version = 'ANALYSIS-213-v1'
    ) AS existing_exact_version_rows,

    COUNT(*) FILTER (
        WHERE inflow_family = 'VETERANS_AFFAIRS'
          AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
          AND valid_from_fiscal_year <= 2019
          AND valid_through_fiscal_year >= 2018
    ) AS overlapping_historical_rows,

    COUNT(*) FILTER (
        WHERE inflow_family = 'VETERANS_AFFAIRS'
          AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
          AND valid_from_fiscal_year <= 2024
          AND valid_through_fiscal_year >= 2024
    ) AS fy2024_policy_rows
FROM reference.federal_inflow_source_policy;

\echo ''
\echo '4. Table constraints'

SELECT
    con.conname AS constraint_name,
    CASE con.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'f' THEN 'FOREIGN KEY'
        WHEN 'c' THEN 'CHECK'
        WHEN 'x' THEN 'EXCLUSION'
        ELSE con.contype::text
    END AS constraint_type,
    pg_get_constraintdef(con.oid)
        AS constraint_definition
FROM pg_constraint con
WHERE con.conrelid =
    'reference.federal_inflow_source_policy'::regclass
ORDER BY con.conname;

\echo ''
\echo '5. Index definitions'

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'reference'
  AND tablename = 'federal_inflow_source_policy'
ORDER BY indexname;

\echo ''
\echo '6. Column defaults, nullability, and types'

SELECT
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_source_policy'
ORDER BY ordinal_position;

\echo ''
\echo '7. Proposed policy compatibility'

WITH proposed AS (
    SELECT
        'VETERANS_AFFAIRS'::text AS inflow_family,
        'TOTAL_VA_EXPENDITURES'::text AS inflow_subfamily,
        'ANNUAL_EXPENDITURES'::text AS accounting_measure,
        'VA_GDX'::text AS preferred_source,
        'VA_GDX'::text AS allocation_source,
        ARRAY['USASPENDING_PROCUREMENT']::text[]
            AS overlapping_sources,
        'INCLUDE_AFTER_RECONCILIATION'::text
            AS ledger_treatment,
        'ANALYSIS-213-v1'::text AS methodology_version,
        2018::integer AS valid_from_fiscal_year,
        2019::integer AS valid_through_fiscal_year
)
SELECT
    p.*,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM reference.federal_inflow_source_policy s
            WHERE s.inflow_family = p.inflow_family
              AND s.inflow_subfamily = p.inflow_subfamily
              AND s.valid_from_fiscal_year
                  <= p.valid_through_fiscal_year
              AND s.valid_through_fiscal_year
                  >= p.valid_from_fiscal_year
        )
        THEN 'BLOCK: EXISTING POLICY OVERLAP'
        ELSE 'PASS: NO EXISTING POLICY OVERLAP'
    END AS historical_year_check,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM reference.federal_inflow_source_policy s
            WHERE s.methodology_version = p.methodology_version
        )
        THEN 'REVIEW: METHODOLOGY VERSION EXISTS'
        ELSE 'PASS: METHODOLOGY VERSION NOT PRESENT'
    END AS version_check
FROM proposed p;

ROLLBACK;

\echo ''
\echo 'ETL-213Y2 v0.1 COMPLETE - NO DATABASE WRITES'
