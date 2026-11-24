
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo ''
\echo 'ETL-211M5C - AWARD IDENTIFIER SEMANTICS'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. AWARD CLASSIFICATION SOURCE SYSTEMS'

SELECT
    source_system,
    COUNT(*) AS classification_rows,
    COUNT(DISTINCT source_program_code) AS programs,
    COUNT(DISTINCT source_award_identifier) AS identifiers
FROM reference.federal_inflow_award_classification
GROUP BY source_system
ORDER BY classification_rows DESC, source_system;

\echo ''
\echo '2. VA MEDICAL CARE AWARD CLASSIFICATION RECORDS'

SELECT
    source_system,
    source_program_code,
    source_award_identifier,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE source_program_code IN (
    '64.011','64.012','64.013',
    '64.039','64.040','64.041',
    '64.042','64.043','64.044',
    '64.045','64.046','64.047',
    '64.048','64.049','64.050'
)
ORDER BY
    source_program_code,
    source_award_identifier,
    methodology_version;

\echo ''
\echo '3. REPRESENTATIVE CLASSIFICATION IDENTIFIERS'

SELECT
    source_system,
    source_program_code,
    source_award_identifier,
    accounting_disposition,
    methodology_version
FROM reference.federal_inflow_award_classification
ORDER BY
    source_system,
    source_program_code,
    source_award_identifier
LIMIT 25;

\echo ''
\echo '4. REPRESENTATIVE HISTORICAL VA AWARD IDENTIFIERS'

SELECT
    action_date_fiscal_year,
    cfda_number,
    assistance_award_unique_key,
    award_id_fain,
    award_id_uri,
    assistance_transaction_unique_key
FROM analysis.v_certified_assistance_ledger
WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
  AND BTRIM(cfda_number) IN (
    '64.011','64.012','64.013',
    '64.039','64.040','64.041',
    '64.042','64.043','64.044',
    '64.045','64.046','64.047',
    '64.048','64.049','64.050'
  )
ORDER BY
    action_date_fiscal_year,
    cfda_number,
    assistance_award_unique_key
LIMIT 25;

ROLLBACK;

\echo ''
\echo 'ETL-211M5C COMPLETE - NO DATABASE WRITES'
