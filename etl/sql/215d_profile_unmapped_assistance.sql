
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215D - UNMAPPED ASSISTANCE PROVENANCE AUDIT'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- Identify the same unmapped population as ETL-215C.
-- EXISTS avoids multiplying source rows through policy joins.

\echo ''
\echo '1. TOP 40 UNMAPPED PROGRAMS - SEVEN-YEAR TOTAL'

WITH source_rows AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        cfda_title AS program_title,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(award_id_fain), ''),
            NULLIF(TRIM(award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (load_batch_id = 20
         AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21
         AND action_date_fiscal_year = 2019)
        OR
        (reference_state_abbreviation = 'WA'
         AND action_date_fiscal_year BETWEEN 2020 AND 2024)
),
unmapped AS MATERIALIZED (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (a.valid_from_fiscal_year IS NULL
               OR a.valid_from_fiscal_year <= s.fiscal_year)
          AND (a.valid_through_fiscal_year IS NULL
               OR a.valid_through_fiscal_year >= s.fiscal_year)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (p.valid_from_fiscal_year IS NULL
               OR p.valid_from_fiscal_year <= s.fiscal_year)
          AND (p.valid_through_fiscal_year IS NULL
               OR p.valid_through_fiscal_year >= s.fiscal_year)
    )
),
program_totals AS (
    SELECT
        program_code,
        MAX(program_title) AS program_title,
        COUNT(*) AS transactions,
        COUNT(DISTINCT fiscal_year) AS years_present,
        SUM(obligation) AS net_obligations,
        SUM(ABS(obligation)) AS absolute_activity,
        COUNT(*) FILTER (WHERE obligation < 0)
            AS negative_transactions
    FROM unmapped
    GROUP BY program_code
)
SELECT
    program_code,
    program_title,
    transactions,
    years_present,
    negative_transactions,
    ROUND(net_obligations, 2) AS net_obligations,
    ROUND(absolute_activity, 2) AS absolute_activity
FROM program_totals
ORDER BY absolute_activity DESC, program_code
LIMIT 40;

\echo ''
\echo '2. UNMAPPED ANNUAL SOURCE CONTROL'

WITH source_rows AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(award_id_fain), ''),
            NULLIF(TRIM(award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (load_batch_id = 20
         AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21
         AND action_date_fiscal_year = 2019)
        OR
        (reference_state_abbreviation = 'WA'
         AND action_date_fiscal_year BETWEEN 2020 AND 2024)
),
unmapped AS (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (a.valid_from_fiscal_year IS NULL
               OR a.valid_from_fiscal_year <= s.fiscal_year)
          AND (a.valid_through_fiscal_year IS NULL
               OR a.valid_through_fiscal_year >= s.fiscal_year)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (p.valid_from_fiscal_year IS NULL
               OR p.valid_from_fiscal_year <= s.fiscal_year)
          AND (p.valid_through_fiscal_year IS NULL
               OR p.valid_through_fiscal_year >= s.fiscal_year)
    )
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS absolute_activity
FROM unmapped
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. EXISTING PROGRAM CLASSIFICATIONS WITHOUT MAPPINGS'
\echo 'These are prior-work evidence, NOT additive authorizations.'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    c.source_program_code,
    c.source_program_title,
    c.inflow_family,
    c.inflow_subfamily,
    c.overlap_risk,
    c.methodology_version,
    c.classification_basis
FROM years y
JOIN reference.federal_inflow_program_classification c
  ON c.source_system = 'USASPENDING_ASSISTANCE'
 AND (c.valid_from_fiscal_year IS NULL
      OR c.valid_from_fiscal_year <= y.fiscal_year)
 AND (c.valid_through_fiscal_year IS NULL
      OR c.valid_through_fiscal_year >= y.fiscal_year)
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_program_policy_mapping p
    WHERE p.source_system = c.source_system
      AND p.source_program_code = c.source_program_code
      AND (p.valid_from_fiscal_year IS NULL
           OR p.valid_from_fiscal_year <= y.fiscal_year)
      AND (p.valid_through_fiscal_year IS NULL
           OR p.valid_through_fiscal_year >= y.fiscal_year)
)
ORDER BY y.fiscal_year, c.source_program_code
LIMIT 150;

\echo ''
\echo '4. SOURCE POLICY INVENTORY - PREVIOUS WORK'

SELECT
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
WHERE
    valid_from_fiscal_year IS NULL
    OR valid_from_fiscal_year <= 2024
ORDER BY
    inflow_family,
    inflow_subfamily,
    methodology_version
LIMIT 150;

ROLLBACK;

\echo ''
\echo 'ETL-215D COMPLETE - READ ONLY'
