\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221U4 - HISTORICAL AUTHORIZATION PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'

\echo ''
\echo '1. SOURCE POLICY TABLE COLUMNS'

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_source_policy'
ORDER BY ordinal_position;

\echo ''
\echo '2. SOURCE POLICY CONSTRAINTS'

SELECT
    conname,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid =
    'reference.federal_inflow_source_policy'::regclass
ORDER BY conname;

\echo ''
\echo '3. EXISTING HISTORICAL SOURCE POLICIES'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    ledger_treatment,
    preferred_source,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE valid_from_fiscal_year <= 2019
  AND (
      valid_through_fiscal_year IS NULL
      OR valid_through_fiscal_year >= 2018
  )
ORDER BY inflow_family, inflow_subfamily;

ROLLBACK;