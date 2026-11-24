
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212H - PROCUREMENT LINK CONSTRAINT INSPECTION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. PRIMARY, UNIQUE, AND FOREIGN KEY CONSTRAINTS'

SELECT
    con.conrelid::regclass AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
WHERE con.conrelid IN (
    'procurement.award_transaction'::regclass,
    'procurement.raw_award_transaction'::regclass,
    'procurement.award_transaction_observation'::regclass,
    'procurement.place_of_performance'::regclass
)
ORDER BY table_name, constraint_type, constraint_name;

\echo ''
\echo '2. EXISTING INDEXES'

SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'procurement'
  AND tablename IN (
      'award_transaction',
      'raw_award_transaction',
      'award_transaction_observation',
      'place_of_performance'
  )
ORDER BY tablename, indexname;

\echo ''
\echo '3. EXISTING PLACE-LINK FIELD CONVENTIONS'

SELECT
    t.fiscal_year,
    COUNT(*) AS linked_transactions,
    COUNT(p.state_id) AS state_id_present,
    COUNT(p.county_id) AS county_id_present,
    COUNT(p.place_id) AS place_id_present,
    COUNT(p.country_code) AS country_present,
    COUNT(p.state_code) AS state_code_present,
    COUNT(p.county_code) AS county_code_present,
    COUNT(p.location_scope) AS scope_present,
    COUNT(DISTINCT p.location_scope) AS distinct_scopes
FROM procurement.award_transaction t
JOIN procurement.place_of_performance p
  ON p.award_transaction_id = t.award_transaction_id
WHERE t.fiscal_year BETWEEN 2018 AND 2025
GROUP BY t.fiscal_year
ORDER BY t.fiscal_year;

\echo ''
\echo '4. PLACE LINK SAMPLE FOR FY2020'

SELECT
    t.award_transaction_id,
    p.state_id,
    p.county_id,
    p.place_id,
    p.country_code,
    p.state_code,
    p.county_code,
    p.city_name,
    p.congressional_district,
    p.zip_code,
    p.location_scope
FROM procurement.award_transaction t
JOIN procurement.place_of_performance p
  ON p.award_transaction_id = t.award_transaction_id
WHERE t.fiscal_year = 2020
ORDER BY t.award_transaction_id
LIMIT 10;

ROLLBACK;

\echo ''
\echo 'ETL-212H COMPLETE - NO DATABASE WRITES'
