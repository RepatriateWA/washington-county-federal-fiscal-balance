\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '===================================================='
\echo 'ETL-221U2 - HISTORICAL POLICY COMPATIBILITY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '===================================================='

\echo ''
\echo '1. CANDIDATE POLICIES AND EXISTING HISTORICAL MAPPINGS'

WITH historical_programs AS (
    SELECT DISTINCT
        t.cfda_number
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.load_batch_id IN (20, 21)
),
candidates AS (
    SELECT
        p.federal_inflow_program_policy_mapping_id,
        p.source_program_code,
        p.resolved_accounting_disposition,
        p.valid_from_fiscal_year,
        p.valid_through_fiscal_year,
        p.federal_inflow_source_policy_id,
        p.methodology_version
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN historical_programs h
      ON h.cfda_number = p.source_program_code
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.valid_from_fiscal_year = 2020
      AND (
          p.valid_through_fiscal_year IS NULL
          OR p.valid_through_fiscal_year >= 2020
      )
)
SELECT
    c.resolved_accounting_disposition,
    COUNT(*) AS candidate_policy_rows,
    COUNT(*) FILTER (
        WHERE EXISTS (
            SELECT 1
            FROM reference.federal_inflow_program_policy_mapping h
            WHERE h.source_system = 'USASPENDING_ASSISTANCE'
              AND h.source_program_code = c.source_program_code
              AND h.valid_from_fiscal_year <= 2019
              AND (
                  h.valid_through_fiscal_year IS NULL
                  OR h.valid_through_fiscal_year >= 2018
              )
        )
    ) AS existing_historical_mapping_rows
FROM candidates c
GROUP BY c.resolved_accounting_disposition
ORDER BY c.resolved_accounting_disposition;

\echo ''
\echo '2. SOURCE POLICY RECORDS ASSOCIATED WITH CANDIDATES'

WITH historical_programs AS (
    SELECT DISTINCT cfda_number
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
),
candidates AS (
    SELECT DISTINCT
        p.federal_inflow_source_policy_id
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN historical_programs h
      ON h.cfda_number = p.source_program_code
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.valid_from_fiscal_year = 2020
)
SELECT
    s.federal_inflow_source_policy_id,
    to_jsonb(s) AS source_policy_record
FROM reference.federal_inflow_source_policy s
JOIN candidates c
  ON c.federal_inflow_source_policy_id =
     s.federal_inflow_source_policy_id
ORDER BY s.federal_inflow_source_policy_id;

\echo ''
\echo '3. HISTORICAL POLICY ROWS FOR CANDIDATE PROGRAMS'

WITH candidate_codes AS (
    SELECT DISTINCT p.source_program_code
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN (
        SELECT DISTINCT cfda_number
        FROM analysis.v_certified_assistance_ledger
        WHERE load_batch_id IN (20, 21)
    ) h
      ON h.cfda_number = p.source_program_code
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.valid_from_fiscal_year = 2020
)
SELECT
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version
FROM reference.federal_inflow_program_policy_mapping p
JOIN candidate_codes c
  ON c.source_program_code = p.source_program_code
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.valid_from_fiscal_year <= 2019
  AND (
      p.valid_through_fiscal_year IS NULL
      OR p.valid_through_fiscal_year >= 2018
  )
ORDER BY p.source_program_code, p.valid_from_fiscal_year;

ROLLBACK;