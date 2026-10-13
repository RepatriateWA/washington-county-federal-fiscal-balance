
\set ON_ERROR_STOP on
\pset pager off

\echo '=============================================================='
\echo 'ETL-201Q STAGE D.2 - TRANSACTION CONSTRAINT PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '300s';

\echo ''
\echo 'SECTION 1 - CANONICAL TRANSACTION COLUMN DEFINITIONS'

SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default,
    numeric_precision,
    numeric_scale
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'award_transaction'
ORDER BY ordinal_position;

\echo ''
\echo 'SECTION 2 - CANONICAL TRANSACTION CONSTRAINTS'

SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
WHERE c.conrelid = 'assistance.award_transaction'::regclass
ORDER BY c.contype, c.conname;

\echo ''
\echo 'SECTION 3 - OBSERVATION LINK CONSTRAINTS'

SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
WHERE c.conrelid =
    'assistance.award_transaction_observation'::regclass
ORDER BY c.contype, c.conname;

\echo ''
\echo 'SECTION 4 - CANONICAL TRANSACTION INDEXES'

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'assistance'
  AND tablename = 'award_transaction'
ORDER BY indexname;

\echo ''
\echo 'SECTION 5 - TRANSACTION FIELD POLICY'

SELECT
    field_class,
    policy_version,
    COUNT(*) AS field_count
FROM assistance.transaction_field_policy
GROUP BY field_class, policy_version
ORDER BY field_class, policy_version;

\echo ''
\echo 'SECTION 6 - HISTORICAL TRANSACTION TARGET BASELINE'

SELECT
    COUNT(*) AS canonical_transaction_rows,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(*) FILTER (
        WHERE assistance_award_id IS NULL
    ) AS null_award_references
FROM assistance.award_transaction;

SELECT
    COUNT(*) AS observation_link_rows
FROM assistance.award_transaction_observation;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE D.2 COMPLETE - READ ONLY'
