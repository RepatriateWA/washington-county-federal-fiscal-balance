
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209B - REPORTING ACCOUNTING DEPENDENCY AUDIT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN READ ONLY;

\echo ''
\echo '1. REPORTING AND ANALYSIS VIEW INVENTORY'

SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    CASE c.relkind
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
    END AS object_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('reporting', 'analysis')
  AND c.relkind IN ('v', 'm')
ORDER BY n.nspname, c.relname;

\echo ''
\echo '2. VIEWS REFERENCING ACCOUNTING POLICY OR DISPOSITION'

WITH definitions AS (
    SELECT
        n.nspname AS schema_name,
        c.relname AS view_name,
        pg_get_viewdef(c.oid, true) AS definition
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('reporting', 'analysis')
      AND c.relkind IN ('v', 'm')
)
SELECT
    schema_name,
    view_name,
    definition ILIKE '%federal_inflow_award_classification%'
        AS references_award_classification,
    definition ILIKE '%federal_inflow_program_policy_mapping%'
        AS references_program_policy,
    definition ILIKE '%resolved_accounting_disposition%'
        AS references_resolved_disposition,
    definition ILIKE '%INCLUDE_ADDITIVE%'
        AS references_additive_disposition
FROM definitions
WHERE definition ILIKE ANY (ARRAY[
    '%federal_inflow_award_classification%',
    '%federal_inflow_program_policy_mapping%',
    '%resolved_accounting_disposition%',
    '%INCLUDE_ADDITIVE%',
    '%ledger_treatment%'
])
ORDER BY schema_name, view_name;

\echo ''
\echo '3. DIRECT DEPENDENCIES OF REPORTING AND ANALYSIS VIEWS'

SELECT DISTINCT
    source_ns.nspname AS dependent_schema,
    source.relname AS dependent_view,
    target_ns.nspname AS referenced_schema,
    target.relname AS referenced_object
FROM pg_class source
JOIN pg_namespace source_ns
  ON source_ns.oid = source.relnamespace
JOIN pg_rewrite rule
  ON rule.ev_class = source.oid
JOIN pg_depend dep
  ON dep.objid = rule.oid
JOIN pg_class target
  ON target.oid = dep.refobjid
JOIN pg_namespace target_ns
  ON target_ns.oid = target.relnamespace
WHERE source_ns.nspname IN ('reporting', 'analysis')
  AND source.relkind IN ('v', 'm')
  AND target.oid <> source.oid
  AND target_ns.nspname NOT IN (
      'pg_catalog', 'information_schema'
  )
ORDER BY
    dependent_schema,
    dependent_view,
    referenced_schema,
    referenced_object;

\echo ''
\echo '4. HISTORICAL ASSISTANCE REPORTING OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('reporting', 'analysis')
  AND (
       c.relname ILIKE '%assistance%'
    OR c.relname ILIKE '%inflow%'
    OR c.relname ILIKE '%fiscal_balance%'
    OR c.relname ILIKE '%expenditure%'
  )
ORDER BY schema_name, object_name;

ROLLBACK;

\echo 'ETL-209B COMPLETE - NO DATABASE WRITES'
