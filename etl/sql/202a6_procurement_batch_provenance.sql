-- ETL-202A.6
-- Procurement batch provenance audit
-- READ ONLY

\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

\echo 'SECTION 1: PROCUREMENT BATCH METADATA'

SELECT
    load_batch_id,
    source_file,
    source_url,
    file_sha256,
    fiscal_year_start,
    fiscal_year_end,
    downloaded_at,
    source_record_count,
    loaded_record_count,
    rejected_record_count,
    load_status,
    notes
FROM procurement.load_batch
WHERE load_batch_id IN (2, 4, 5, 14, 15, 16, 17)
ORDER BY load_batch_id;

\echo 'SECTION 2: COMPLETE YEAR DISTRIBUTION FOR BATCHES 2 AND 4'

SELECT
    load_batch_id,
    fiscal_year,
    COUNT(*) AS canonical_transactions,
    MIN(action_date) AS earliest_action_date,
    MAX(action_date) AS latest_action_date
FROM procurement.award_transaction
WHERE load_batch_id IN (2, 4)
GROUP BY load_batch_id, fiscal_year
ORDER BY load_batch_id, fiscal_year;

\echo 'SECTION 3: FY2015-2019 PROVENANCE SUMMARY'

SELECT
    load_batch_id,
    COUNT(*) AS historical_transactions,
    MIN(fiscal_year) AS earliest_fiscal_year,
    MAX(fiscal_year) AS latest_fiscal_year
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2015 AND 2019
GROUP BY load_batch_id
ORDER BY load_batch_id;

ROLLBACK;
