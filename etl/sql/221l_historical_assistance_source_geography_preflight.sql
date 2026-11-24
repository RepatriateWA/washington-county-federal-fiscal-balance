\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '===================================================='
\echo 'ETL-221L - HISTORICAL ASSISTANCE SOURCE GEOGRAPHY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '===================================================='

\echo ''
\echo '1. RAW TRANSACTION GEOGRAPHY AND SOURCE COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'raw_award_transaction'
  AND (
       column_name ILIKE '%place%'
    OR column_name ILIKE '%state%'
    OR column_name ILIKE '%county%'
    OR column_name ILIKE '%zip%'
    OR column_name ILIKE '%location%'
    OR column_name ILIKE '%recipient%'
    OR column_name ILIKE '%batch%'
    OR column_name ILIKE '%row%'
  )
ORDER BY ordinal_position;

\echo ''
\echo '2. CANONICAL TRANSACTION LINKAGE FIELDS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'award_transaction'
  AND (
       column_name ILIKE '%place%'
    OR column_name ILIKE '%recipient%'
    OR column_name ILIKE '%batch%'
    OR column_name ILIKE '%row%'
  )
ORDER BY ordinal_position;

\echo ''
\echo '3. HISTORICAL CANONICAL LINKAGE COUNTS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    load_batch_id,
    COUNT(*) AS transaction_rows,
    COUNT(*) FILTER (
        WHERE place_of_performance_id IS NULL
    ) AS missing_performance_place,
    COUNT(*) FILTER (
        WHERE recipient_id IS NULL
    ) AS missing_recipient_link,
    COUNT(*) FILTER (
        WHERE assistance_listing_id IS NULL
    ) AS missing_program_link,
    SUM(federal_action_obligation) AS obligations_dollars
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year IN (2018, 2019)
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '4. AVAILABLE SOURCE BATCH TABLES'

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND (
       table_name ILIKE '%load_batch%'
    OR table_name ILIKE '%source_file%'
    OR table_name ILIKE '%import_batch%'
  )
ORDER BY table_schema, table_name;

\echo ''
\echo '5. AVAILABLE PLACE LINKAGE TABLES'

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND (
       table_name ILIKE '%place%'
    OR table_name ILIKE '%geograph%'
  )
  AND table_schema IN (
      'assistance',
      'procurement',
      'reference'
  )
ORDER BY table_schema, table_name;

ROLLBACK;