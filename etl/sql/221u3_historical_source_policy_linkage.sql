\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221U3 - HISTORICAL SOURCE POLICY LINKAGE'
\echo 'READ ONLY - NO DATABASE WRITES'

WITH historical_codes AS (
    SELECT DISTINCT cfda_number
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
),
candidates AS (
    SELECT p.*
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN historical_codes h
      ON h.cfda_number = p.source_program_code
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.valid_from_fiscal_year = 2020
      AND NOT EXISTS (
          SELECT 1
          FROM reference.federal_inflow_program_policy_mapping old
          WHERE old.source_system = p.source_system
            AND old.source_program_code = p.source_program_code
            AND old.valid_from_fiscal_year <= 2019
            AND (
                old.valid_through_fiscal_year IS NULL
                OR old.valid_through_fiscal_year >= 2018
            )
      )
)
SELECT
    c.source_program_code,
    c.resolved_accounting_disposition,
    c.methodology_version AS later_methodology,
    s.inflow_family,
    s.inflow_subfamily,
    s.valid_from_fiscal_year AS source_policy_start,
    s.valid_through_fiscal_year AS source_policy_end,
    s.methodology_version AS source_methodology,
    CASE
        WHEN s.valid_from_fiscal_year <= 2018
         AND (
             s.valid_through_fiscal_year IS NULL
             OR s.valid_through_fiscal_year >= 2019
         )
        THEN 'HISTORICALLY_VALID_SOURCE'
        ELSE 'HISTORICAL_SOURCE_POLICY_REQUIRED'
    END AS linkage_status
FROM candidates c
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     c.federal_inflow_source_policy_id
ORDER BY
    linkage_status,
    c.resolved_accounting_disposition,
    c.source_program_code;

ROLLBACK;