-- ETL-202A.4
-- Historical coverage and source-policy audit
-- READ ONLY

\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

\echo 'SECTION 1: HISTORICAL PROCUREMENT'
SELECT
    fiscal_year,
    COUNT(*) AS transaction_rows,
    COUNT(DISTINCT load_batch_id) AS distinct_batches
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2015 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo 'SECTION 2: HISTORICAL ASSISTANCE'
SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS canonical_transactions,
    COUNT(DISTINCT load_batch_id) AS distinct_batches
FROM assistance.award_transaction
WHERE action_date_fiscal_year BETWEEN 2015 AND 2024
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

\echo 'SECTION 3: VA GDX CATEGORY COUNTS'
SELECT
    fiscal_year,
    COUNT(*) AS observations,
    COUNT(DISTINCT county_id) AS distinct_counties
FROM va.gdx_county_expenditure
WHERE fiscal_year BETWEEN 2015 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo 'SECTION 4: SOURCE ACCOUNTING POLICIES'
SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
ORDER BY inflow_family, inflow_subfamily,
         valid_from_fiscal_year;

\echo 'SECTION 5: PROGRAM MAPPING SUMMARY'
SELECT
    source_system,
    resolved_accounting_disposition,
    COUNT(*) AS mapping_count,
    MIN(valid_from_fiscal_year) AS earliest_valid_year,
    MAX(valid_through_fiscal_year) AS latest_valid_year
FROM reference.federal_inflow_program_policy_mapping
GROUP BY source_system, resolved_accounting_disposition
ORDER BY source_system, resolved_accounting_disposition;

ROLLBACK;
