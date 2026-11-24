
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M5A - ASSISTANCE LEDGER RESOLUTION DISCOVERY'
\echo '=========================================================================='
\echo 'Scope: FY2018-FY2019 VA Medical Care'
\echo 'Mode: READ ONLY - NO DATABASE WRITES'
\echo '=========================================================================='

BEGIN TRANSACTION READ ONLY;

-- ==========================================================================
-- SECTION 1 - CANDIDATE ACCOUNTING OBJECTS
-- ==========================================================================
-- Find relations whose names suggest ledger classification, accounting
-- disposition, reconciliation, policy resolution, or transaction overrides.
-- ==========================================================================

\echo ''
\echo '1. CANDIDATE ACCOUNTING OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED_TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED_VIEW'
        WHEN 'f' THEN 'FOREIGN_TABLE'
        ELSE c.relkind::text
    END AS object_type
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND n.nspname NOT IN (
      'pg_catalog',
      'information_schema'
  )
  AND n.nspname NOT LIKE 'pg_toast%'
  AND (
      c.relname ILIKE '%ledger%'
      OR c.relname ILIKE '%disposition%'
      OR c.relname ILIKE '%policy%'
      OR c.relname ILIKE '%overlap%'
      OR c.relname ILIKE '%reconcil%'
      OR c.relname ILIKE '%override%'
      OR c.relname ILIKE '%classif%'
  )
ORDER BY n.nspname, c.relname;


-- ==========================================================================
-- SECTION 2 - ACCOUNTING-RELATED COLUMNS
-- ==========================================================================
-- Find actual column names rather than assuming a disposition field
-- exists on the certified transaction view.
-- ==========================================================================

\echo ''
\echo '2. ACCOUNTING-RELATED COLUMNS'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
      column_name ILIKE '%disposition%'
      OR column_name ILIKE '%ledger%'
      OR column_name ILIKE '%policy%'
      OR column_name ILIKE '%overlap%'
      OR column_name ILIKE '%override%'
      OR column_name ILIKE '%classification%'
      OR column_name ILIKE '%methodology%'
  )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- ==========================================================================
-- SECTION 3 - ASSISTANCE LEDGER VIEW DEFINITIONS
-- ==========================================================================
-- Retrieve definitions for assistance-related accounting views.
-- These definitions help establish policy precedence and resolution.
-- ==========================================================================

\echo ''
\echo '3. ASSISTANCE LEDGER VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_catalog.pg_views
WHERE schemaname NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
      viewname ILIKE '%assistance%ledger%'
      OR viewname ILIKE '%assistance%disposition%'
      OR viewname ILIKE '%assistance%policy%'
      OR viewname ILIKE '%inflow%ledger%'
      OR viewname ILIKE '%inflow%resolution%'
  )
ORDER BY schemaname, viewname;


-- ==========================================================================
-- SECTION 4 - DIRECT DEPENDENCIES OF CERTIFIED ASSISTANCE VIEW
-- ==========================================================================
-- List relations referenced directly by the certified assistance view.
-- This does not recursively expand every downstream dependency.
-- ==========================================================================

\echo ''
\echo '4. DIRECT DEPENDENCIES OF CERTIFIED ASSISTANCE VIEW'

SELECT DISTINCT
    source_ns.nspname AS source_schema,
    source_rel.relname AS source_object,
    source_rel.relkind AS source_kind
FROM pg_catalog.pg_class target_rel
JOIN pg_catalog.pg_namespace target_ns
  ON target_ns.oid = target_rel.relnamespace
JOIN pg_catalog.pg_rewrite rw
  ON rw.ev_class = target_rel.oid
JOIN pg_catalog.pg_depend dep
  ON dep.objid = rw.oid
 AND dep.classid = 'pg_catalog.pg_rewrite'::regclass
 AND dep.refclassid = 'pg_catalog.pg_class'::regclass
JOIN pg_catalog.pg_class source_rel
  ON source_rel.oid = dep.refobjid
JOIN pg_catalog.pg_namespace source_ns
  ON source_ns.oid = source_rel.relnamespace
WHERE target_ns.nspname = 'analysis'
  AND target_rel.relname = 'v_certified_assistance_ledger'
  AND source_rel.oid <> target_rel.oid
ORDER BY source_schema, source_object;


-- ==========================================================================
-- SECTION 5 - EXISTING POLICY PRECEDENCE AND UNIQUENESS CONSTRAINTS
-- ==========================================================================
-- Identify constraints and indexes that may affect overlapping
-- program-policy mappings.
-- ==========================================================================

\echo ''
\echo '5. POLICY MAPPING CONSTRAINTS'

SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS constraint_definition
FROM pg_catalog.pg_constraint con
WHERE con.conrelid =
    'reference.federal_inflow_program_policy_mapping'::regclass
ORDER BY con.conname;

\echo ''
\echo '6. POLICY MAPPING INDEXES'

SELECT
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'reference'
  AND tablename = 'federal_inflow_program_policy_mapping'
ORDER BY indexname;


-- ==========================================================================
-- SECTION 7 - COMPLETION
-- ==========================================================================

ROLLBACK;

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M5A COMPLETE - NO DATABASE WRITES'
\echo '=========================================================================='
