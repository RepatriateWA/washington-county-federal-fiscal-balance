
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214M2B0 - HISTORICAL POLICY MIGRATION GATE'
\echo 'FY2018-FY2019 / SIX ADDITIVE PROGRAMS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. POLICY TABLE CONSTRAINTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'reference'
  AND c.relname IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_program_classification'
  )
ORDER BY c.relname, con.conname;

\echo ''
\echo '2. POLICY TABLE INDEXES'

SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'reference'
  AND tablename IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_program_classification'
  )
ORDER BY tablename, indexname;

\echo ''
\echo '3. REQUIRED COLUMN DEFINITIONS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_program_classification'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '4. EXISTING SIX-PROGRAM POLICY BASELINE'

SELECT
    m.source_program_code,
    m.federal_inflow_program_policy_mapping_id AS mapping_id,
    m.federal_inflow_source_policy_id AS source_policy_id,
    s.inflow_family,
    s.inflow_subfamily,
    m.resolved_accounting_disposition,
    m.valid_from_fiscal_year AS mapping_from,
    m.valid_through_fiscal_year AS mapping_through,
    s.valid_from_fiscal_year AS source_from,
    s.valid_through_fiscal_year AS source_through,
    m.methodology_version AS mapping_version,
    s.methodology_version AS source_version
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN (
      '10.555', '84.010', '84.027',
      '84.063', '93.558', '93.600'
  )
ORDER BY m.source_program_code, m.valid_from_fiscal_year;

\echo ''
\echo '5. HISTORICAL POLICY COLLISION CHECK'

WITH target AS (
    SELECT
        m.source_system,
        m.source_program_code,
        s.inflow_family,
        s.inflow_subfamily
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code IN (
          '10.555', '84.010', '84.027',
          '84.063', '93.558', '93.600'
      )
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024
)
SELECT
    t.source_program_code,
    COUNT(DISTINCT m.federal_inflow_program_policy_mapping_id)
        FILTER (
            WHERE m.valid_from_fiscal_year IS NULL
               OR m.valid_through_fiscal_year IS NULL
               OR (
                   m.valid_from_fiscal_year <= 2019
                   AND m.valid_through_fiscal_year >= 2018
               )
        ) AS historical_mapping_collisions,
    COUNT(DISTINCT s.federal_inflow_source_policy_id)
        FILTER (
            WHERE s.valid_from_fiscal_year IS NULL
               OR s.valid_through_fiscal_year IS NULL
               OR (
                   s.valid_from_fiscal_year <= 2019
                   AND s.valid_through_fiscal_year >= 2018
               )
        ) AS historical_source_collisions
FROM target t
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = t.source_system
 AND m.source_program_code = t.source_program_code
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.inflow_family = t.inflow_family
 AND s.inflow_subfamily = t.inflow_subfamily
GROUP BY t.source_program_code
ORDER BY t.source_program_code;

ROLLBACK;

\echo 'ETL-214M2B0 COMPLETE - NO DATABASE WRITES'
