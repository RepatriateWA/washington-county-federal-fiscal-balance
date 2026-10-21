\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221U5 - HISTORICAL MIGRATION GATE'
\echo 'READ ONLY - NO DATABASE WRITES'

WITH historical AS (
    SELECT DISTINCT cfda_number
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
),
candidates AS (
    SELECT p.*
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN historical h
      ON h.cfda_number = p.source_program_code
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.valid_from_fiscal_year = 2020
      AND p.source_program_code <> '86.001'
      AND NOT EXISTS (
          SELECT 1
          FROM reference.federal_inflow_program_policy_mapping old
          WHERE old.source_system = p.source_system
            AND old.source_program_code = p.source_program_code
            AND COALESCE(old.valid_from_fiscal_year, -9999) <= 2019
            AND COALESCE(old.valid_through_fiscal_year, 9999) >= 2018
      )
),
controls AS (
    SELECT
        COUNT(*) AS candidate_rows,
        COUNT(DISTINCT source_program_code) AS distinct_programs,
        COUNT(DISTINCT federal_inflow_source_policy_id)
            AS distinct_source_policies,
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
        ) AS additive_rows,
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
        ) AS duplicate_rows,
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'REFERENCE_ONLY'
        ) AS reference_rows,
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED'
        ) AS withheld_rows
    FROM candidates
)
SELECT *,
       CASE
           WHEN candidate_rows = 33
            AND distinct_programs = 33
            AND additive_rows = 14
            AND duplicate_rows = 7
            AND reference_rows = 3
            AND withheld_rows = 9
           THEN 'PASS'
           ELSE 'FAIL'
       END AS migration_gate
FROM controls;

ROLLBACK;