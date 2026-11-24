
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211M7 - VA HISTORICAL MEDICAL POLICY CERTIFICATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- 1. Verify committed policy record counts.

\echo ''
\echo '1. COMMITTED RECORD COUNTS'

WITH counts AS (
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_classification
         WHERE methodology_version = 'ANALYSIS-211M-v1')
            AS classifications,
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-211M-v1')
            AS source_policies,
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-211M-v1')
            AS mappings
)
SELECT *,
       CASE WHEN classifications = 15
                 AND source_policies = 1
                 AND mappings = 15
            THEN 'PASS' ELSE 'FAIL' END AS status
FROM counts;

-- 2. Independently resolve every historical transaction.

\echo ''
\echo '2. HISTORICAL TRANSACTION RESOLUTION'

WITH targets(code) AS (
    VALUES
    ('64.011'), ('64.012'), ('64.013'),
    ('64.039'), ('64.040'), ('64.041'),
    ('64.042'), ('64.043'), ('64.044'),
    ('64.045'), ('64.046'), ('64.047'),
    ('64.048'), ('64.049'), ('64.050')
),
historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger c
    JOIN targets t
      ON t.code = BTRIM(c.cfda_number)
    WHERE (c.load_batch_id = 20
           AND c.action_date_fiscal_year = 2018)
       OR (c.load_batch_id = 21
           AND c.action_date_fiscal_year = 2019)
),
resolved AS (
    SELECT
        h.assistance_transaction_id,
        h.fiscal_year,
        h.program_code,
        h.federal_action_obligation,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS mapping_count,
        COUNT(*) FILTER (
            WHERE m.methodology_version = 'ANALYSIS-211M-v1'
              AND m.resolved_accounting_disposition =
                  'EXCLUDE_DUPLICATE'
              AND s.preferred_source = 'VA_GDX'
              AND s.allocation_source = 'VA_GDX'
              AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
        ) AS correct_count
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, -9999)
         AND COALESCE(m.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    GROUP BY
        h.assistance_transaction_id,
        h.fiscal_year,
        h.program_code,
        h.federal_action_obligation
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE mapping_count <> 1 OR correct_count <> 1
    ) AS bad_resolutions,
    CASE
        WHEN fiscal_year = 2018
         AND COUNT(*) = 5999
         AND COUNT(DISTINCT assistance_transaction_id) = 5999
         AND COUNT(DISTINCT program_code) = 15
         AND ROUND(SUM(federal_action_obligation)::numeric, 2)
             = 1133039687.00
         AND COUNT(*) FILTER (
             WHERE mapping_count <> 1 OR correct_count <> 1
         ) = 0
            THEN 'PASS'
        WHEN fiscal_year = 2019
         AND COUNT(*) = 5819
         AND COUNT(DISTINCT assistance_transaction_id) = 5819
         AND COUNT(DISTINCT program_code) = 15
         AND ROUND(SUM(federal_action_obligation)::numeric, 2)
             = 1164764614.00
         AND COUNT(*) FILTER (
             WHERE mapping_count <> 1 OR correct_count <> 1
         ) = 0
            THEN 'PASS'
        ELSE 'FAIL'
    END AS status
FROM resolved
GROUP BY fiscal_year
ORDER BY fiscal_year;

-- 3. Verify no historical policy was applied to AL 64.029.

\echo ''
\echo '3. AL 64.029 EXCLUSION BOUNDARY'

SELECT
    COUNT(*) AS unexpected_mappings,
    CASE WHEN COUNT(*) = 0
         THEN 'PASS' ELSE 'FAIL' END AS status
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-211M-v1'
  AND source_program_code = '64.029';

-- 4. Verify later-year mappings remain unique.

\echo ''
\echo '4. FY2020-FY2024 POLICY CONTINUITY'

WITH targets(code) AS (
    VALUES
    ('64.011'), ('64.012'), ('64.013'),
    ('64.039'), ('64.040'), ('64.041'),
    ('64.042'), ('64.043'), ('64.044'),
    ('64.045'), ('64.046'), ('64.047'),
    ('64.048'), ('64.049'), ('64.050')
),
years AS (
    SELECT t.code, y.fiscal_year
    FROM targets t
    CROSS JOIN generate_series(2020, 2024)
        AS y(fiscal_year)
),
coverage AS (
    SELECT
        y.code,
        y.fiscal_year,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS matching_mappings,
        COUNT(*) FILTER (
            WHERE m.methodology_version = 'ANALYSIS-174B-5N-v1'
              AND m.resolved_accounting_disposition =
                  'EXCLUDE_DUPLICATE'
        ) AS expected_mappings
    FROM years y
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = y.code
     AND y.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, -9999)
         AND COALESCE(m.valid_through_fiscal_year, 9999)
    GROUP BY y.code, y.fiscal_year
)
SELECT
    COUNT(*) AS program_years,
    COUNT(*) FILTER (
        WHERE matching_mappings = 1
          AND expected_mappings = 1
    ) AS correct_program_years,
    CASE
        WHEN COUNT(*) = 75
         AND COUNT(*) FILTER (
             WHERE matching_mappings = 1
               AND expected_mappings = 1
         ) = 75
        THEN 'PASS' ELSE 'FAIL'
    END AS status
FROM coverage;

ROLLBACK;

\echo ''
\echo 'ETL-211M7 COMPLETE - NO DATABASE WRITES'
