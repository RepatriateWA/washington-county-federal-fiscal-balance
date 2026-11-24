\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-207H - HISTORICAL HCV POLICY EXTENSION PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo '=== 1. POLICY TABLE CONSTRAINTS ==='

SELECT
    c.conrelid::regclass AS policy_table,
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
WHERE c.conrelid IN (
    'reference.federal_inflow_source_policy'::regclass,
    'reference.federal_inflow_program_classification'::regclass,
    'reference.federal_inflow_program_policy_mapping'::regclass
)
ORDER BY 1, 2;

\echo '=== 2. EXISTING HCV PROGRAM CLASSIFICATIONS ==='

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '14.871'
ORDER BY valid_from_fiscal_year;

\echo '=== 3. EXISTING HCV POLICY MAPPINGS ==='

SELECT
    federal_inflow_program_policy_mapping_id,
    federal_inflow_source_policy_id,
    source_system,
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '14.871'
ORDER BY valid_from_fiscal_year;

\echo '=== 4. SOURCE POLICY ID 29 ==='

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id = 29;

\echo '=== 5. HISTORICAL HCV ACCOUNTING CONTROL ==='

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_awards,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '14.871'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY 1
ORDER BY 1;

COMMIT;

\echo 'ETL-207H READ-ONLY PREFLIGHT COMPLETE'