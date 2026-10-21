
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223N4 - AWARD CLASSIFICATION PRECEDENCE PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. AWARD CLASSIFICATION TABLE STRUCTURE'

SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_award_classification'
ORDER BY ordinal_position;

\echo ''
\echo '2. EXISTING AWARD CLASSIFICATION DISTRIBUTION'

SELECT
    accounting_disposition,
    COUNT(*) AS classification_records
FROM reference.federal_inflow_award_classification
GROUP BY accounting_disposition
ORDER BY accounting_disposition;

\echo ''
\echo '3. CERTIFIED ASSISTANCE LEDGER LINKING COLUMNS'

SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name = 'v_certified_assistance_ledger'
  AND (
      column_name ILIKE '%award%'
      OR column_name ILIKE '%batch%'
      OR column_name ILIKE '%row%'
      OR column_name ILIKE '%transaction%'
      OR column_name ILIKE '%cfda%'
  )
ORDER BY ordinal_position;

COMMIT;

\echo 'ETL-223N4 COMPLETE - NO DATABASE WRITES'
