-- ETL-202A.5
-- Historical procurement provenance profile
-- READ ONLY

\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

\echo 'SECTION 1: PROCUREMENT BY FISCAL YEAR AND LOAD BATCH'

SELECT
    fiscal_year,
    load_batch_id,
    COUNT(*) AS canonical_transaction_rows,
    MIN(action_date) AS earliest_action_date,
    MAX(action_date) AS latest_action_date
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2015 AND 2024
GROUP BY fiscal_year, load_batch_id
ORDER BY fiscal_year, load_batch_id;

\echo 'SECTION 2: PROCUREMENT LOAD BATCH METADATA COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'load_batch'
ORDER BY ordinal_position;

\echo 'SECTION 3: ASSISTANCE HISTORICAL POLICY BOUNDARIES'

SELECT
    source_system,
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS mapping_count
FROM reference.federal_inflow_program_policy_mapping
GROUP BY
    source_system,
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY
    source_system,
    resolved_accounting_disposition,
    valid_from_fiscal_year;

ROLLBACK;
