
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '============================================================'
\echo 'ETL-201K v0.1'
\echo 'FUNDING OPPORTUNITY REFERENCE POLICY AUDIT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo 'SECTION 1 - REFERENCE TABLE COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default,
    is_identity
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'funding_opportunity'
ORDER BY ordinal_position;

\echo ''
\echo 'SECTION 2 - REFERENCE TABLE CONSTRAINTS'

SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.conrelid =
    'assistance.funding_opportunity'::regclass
ORDER BY con.conname;

\echo ''
\echo 'SECTION 3 - REFERENCE TABLE INDEXES'

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'assistance'
  AND tablename = 'funding_opportunity'
ORDER BY indexname;

\echo ''
\echo 'SECTION 4 - EXISTING REFERENCE EXAMPLES'

SELECT *
FROM assistance.funding_opportunity
ORDER BY funding_opportunity_id
LIMIT 15;

\echo ''
\echo 'SECTION 5 - REFERENCE POPULATION'

SELECT
    COUNT(*) AS reference_rows,
    COUNT(DISTINCT funding_opportunity_number)
        AS distinct_opportunity_numbers,
    COUNT(*) FILTER (
        WHERE funding_opportunity_number IS NULL
    ) AS null_opportunity_numbers
FROM assistance.funding_opportunity;

ROLLBACK;

\echo ''
\echo 'ETL-201K COMPLETE - NO DATABASE WRITES'
