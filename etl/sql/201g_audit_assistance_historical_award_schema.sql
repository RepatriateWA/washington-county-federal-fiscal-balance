
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '============================================================'
\echo 'WCFFBP - ETL-201G v0.1'
\echo 'HISTORICAL CANONICAL AWARD SCHEMA AUDIT'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo 'SECTION 1 - CANONICAL AWARD COLUMN DEFINITIONS'
\echo ''

SELECT
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    character_maximum_length,
    is_identity,
    identity_generation,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'award'
ORDER BY ordinal_position;

\echo ''
\echo 'SECTION 2 - CANONICAL AWARD CONSTRAINTS'
\echo ''

SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid, true)
        AS constraint_definition,
    c.convalidated AS is_validated
FROM pg_constraint AS c
WHERE c.conrelid = 'assistance.award'::regclass
ORDER BY c.contype, c.conname;

\echo ''
\echo 'SECTION 3 - CANONICAL AWARD INDEXES'
\echo ''

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'assistance'
  AND tablename = 'award'
ORDER BY indexname;

\echo ''
\echo 'SECTION 4 - FOREIGN KEY REFERENCES'
\echo ''

SELECT
    c.conname AS foreign_key_name,
    pg_get_constraintdef(c.oid, true)
        AS foreign_key_definition,
    c.confrelid::regclass
        AS referenced_table
FROM pg_constraint AS c
WHERE c.conrelid = 'assistance.award'::regclass
  AND c.contype = 'f'
ORDER BY c.conname;

\echo ''
\echo 'SECTION 5 - AWARD TABLE TRIGGERS'
\echo ''

SELECT
    t.tgname AS trigger_name,
    pg_get_triggerdef(t.oid, true)
        AS trigger_definition,
    t.tgenabled AS trigger_enabled
FROM pg_trigger AS t
WHERE t.tgrelid = 'assistance.award'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;

\echo ''
\echo 'SECTION 6 - HISTORICAL SOURCE AND CANONICAL COUNTS'
\echo ''

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT
        assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    COUNT(*) AS historical_distinct_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NOT NULL
    ) AS existing_canonical_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NULL
    ) AS missing_canonical_awards
FROM historical_keys AS h
LEFT JOIN assistance.award AS a
  ON a.assistance_award_unique_key = h.award_key;

\echo ''
\echo 'SECTION 7 - EXISTING CANONICAL AWARD EXAMPLES'
\echo ''

SELECT *
FROM assistance.award
LIMIT 5;

ROLLBACK;
