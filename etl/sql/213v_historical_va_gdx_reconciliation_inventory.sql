
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '=========================================================='
\echo 'ETL-213V v0.1 - HISTORICAL VA GDX RECONCILIATION INVENTORY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Existing VA-related relations'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'f' THEN 'FOREIGN TABLE'
        ELSE c.relkind::text
    END AS relation_type
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE n.nspname NOT IN (
    'pg_catalog',
    'information_schema'
)
AND (
    n.nspname ILIKE '%va%'
    OR c.relname ILIKE '%gdx%'
    OR c.relname ILIKE '%veteran%'
    OR c.relname ILIKE '%federal_inflow%'
)
AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
ORDER BY n.nspname, c.relname;

\echo ''
\echo '2. VA and source-policy column inventory'

SELECT
    c.table_schema,
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type
FROM information_schema.columns c
WHERE (
    c.table_schema = 'va'
    OR c.table_name ILIKE '%gdx%'
    OR c.table_name IN (
        'federal_inflow_source_policy',
        'federal_inflow_program_classification',
        'federal_inflow_program_policy_mapping',
        'federal_inflow_award_classification'
    )
)
ORDER BY
    c.table_schema,
    c.table_name,
    c.ordinal_position;

\echo ''
\echo '3. VA GDX source-related database objects'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    d.description AS object_description
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
LEFT JOIN pg_description d
  ON d.objoid = c.oid
 AND d.objsubid = 0
WHERE n.nspname NOT IN (
    'pg_catalog',
    'information_schema'
)
AND (
    n.nspname = 'va'
    OR c.relname ILIKE '%gdx%'
)
AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
ORDER BY n.nspname, c.relname;

\echo ''
\echo '4. Existing policy-table row counts'

SELECT
    'federal_inflow_source_policy' AS relation_name,
    COUNT(*) AS rows
FROM reference.federal_inflow_source_policy

UNION ALL

SELECT
    'federal_inflow_program_classification',
    COUNT(*)
FROM reference.federal_inflow_program_classification

UNION ALL

SELECT
    'federal_inflow_program_policy_mapping',
    COUNT(*)
FROM reference.federal_inflow_program_policy_mapping

UNION ALL

SELECT
    'federal_inflow_award_classification',
    COUNT(*)
FROM reference.federal_inflow_award_classification;

\echo ''
\echo '5. FY2018-FY2019 VA procurement control'

SELECT
    t.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT t.award_id) AS awards,
    COUNT(*) FILTER (
        WHERE t.federal_action_obligation > 0
    ) AS positive_transactions,
    COUNT(*) FILTER (
        WHERE t.federal_action_obligation < 0
    ) AS negative_transactions,
    ROUND(
        SUM(t.federal_action_obligation), 2
    ) AS net_obligations,
    ROUND(
        SUM(ABS(t.federal_action_obligation)), 2
    ) AS gross_absolute_obligations
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id =
     r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id =
     o.award_transaction_id
WHERE r.load_batch_id IN (22, 23)
  AND BTRIM(
      r.raw_record->>'funding_agency_code'
  ) = '036'
  AND t.fiscal_year IN (2018, 2019)
GROUP BY t.fiscal_year
ORDER BY t.fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-213V v0.1 COMPLETE - NO DATABASE WRITES'
