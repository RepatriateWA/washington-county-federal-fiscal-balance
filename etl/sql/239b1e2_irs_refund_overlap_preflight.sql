\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION READ ONLY;

\echo 'ETL-239B1E2 | IRS REFUND OVERLAP PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'

\echo 'SECTION 1 | Relevant source columns'
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE
    (table_schema = 'reference'
     AND table_name IN (
         'federal_inflow_program_policy_mapping',
         'federal_inflow_award_classification'
     ))
    OR
    (table_schema = 'analysis'
     AND table_name = 'v_certified_assistance_ledger')
ORDER BY table_schema, table_name, ordinal_position;

\echo 'SECTION 2 | IRS and pandemic program-policy candidates'
SELECT
    source_program_code,
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    to_jsonb(p)::text AS full_policy_record
FROM reference.federal_inflow_program_policy_mapping p
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND (
      to_jsonb(p)::text ~* 
      'economic impact|stimulus|recovery rebate|child tax|refundable|tax credit|internal revenue|treasury|pandemic'
  )
ORDER BY source_program_code, valid_from_fiscal_year
LIMIT 150;

\echo 'SECTION 3 | IRS and pandemic award-policy candidates'
SELECT
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    to_jsonb(a)::text AS full_award_record
FROM reference.federal_inflow_award_classification a
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND (
      to_jsonb(a)::text ~*
      'economic impact|stimulus|recovery rebate|child tax|refundable|tax credit|internal revenue|treasury|pandemic'
  )
ORDER BY source_program_code, valid_from_fiscal_year
LIMIT 150;

\echo 'SECTION 4 | Source coverage by fiscal year'
SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS washington_transactions,
    COUNT(*) FILTER (
        WHERE cfda_number IS NULL
    ) AS missing_program_code,
    COUNT(DISTINCT cfda_number) AS distinct_program_codes
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2018 AND 2024
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

ROLLBACK;
\echo 'ETL-239B1E2 PREFLIGHT COMPLETE'