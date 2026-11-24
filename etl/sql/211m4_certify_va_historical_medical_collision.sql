
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M4 - HISTORICAL VA MEDICAL CARE COLLISION CERTIFICATION'
\echo '=========================================================================='
\echo 'Fiscal years: FY2018-FY2019'
\echo 'Scope: 15 direct GDX Medical Care Assistance Listings'
\echo 'Mode: READ ONLY - NO DATABASE WRITES'
\echo 'AL 64.029: SEPARATE REVIEW - NOT IN CERTIFICATION POPULATION'
\echo '=========================================================================='

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- ==========================================================================
-- SECTION 1 - CERTIFICATION POPULATION
-- ==========================================================================
--
-- Reproduce the 15-program direct Medical Care population established
-- in ETL-174B-5N-3 and profiled in ETL-211M3.
--
-- Expected:
--   FY2018: 5,999 transactions; $1,133,039,687
--   FY2019: 5,819 transactions; $1,164,764,614
--
-- AL 64.029 is deliberately excluded.
-- ==========================================================================

\echo ''
\echo '1. CERTIFICATION POPULATION AND CONTROL TOTALS'

WITH medical_codes(program_code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
),
candidate AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.assistance_transaction_id,
        c.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger c
    JOIN medical_codes m
      ON m.program_code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20 AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21 AND c.action_date_fiscal_year = 2019)
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id) AS distinct_transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    CASE
        WHEN fiscal_year = 2018
         AND COUNT(*) = 5999
         AND COUNT(DISTINCT assistance_transaction_id) = 5999
         AND COUNT(DISTINCT program_code) = 15
         AND SUM(federal_action_obligation) = 1133039687
            THEN 'PASS'
        WHEN fiscal_year = 2019
         AND COUNT(*) = 5819
         AND COUNT(DISTINCT assistance_transaction_id) = 5819
         AND COUNT(DISTINCT program_code) = 15
         AND SUM(federal_action_obligation) = 1164764614
            THEN 'PASS'
        ELSE 'FAIL'
    END AS control_status
FROM candidate
GROUP BY fiscal_year
ORDER BY fiscal_year;



-- ==========================================================================
-- SECTION 2 - HISTORICAL POLICY DISPOSITION COVERAGE
-- ==========================================================================
--
-- Determine whether existing program policy mappings cover FY2018
-- or FY2019. The certified transaction view has no disposition column.
-- ==========================================================================

\echo ''
\echo '2. HISTORICAL POLICY DISPOSITION COVERAGE'

WITH medical_codes(program_code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
),
target_years(fiscal_year) AS (
    VALUES (2018), (2019)
)
SELECT
    y.fiscal_year,
    codes.program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    s.preferred_source,
    s.ledger_treatment,
    CASE
        WHEN m.source_program_code IS NULL
            THEN 'NO_EXISTING_YEAR_POLICY'
        WHEN m.resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
         AND s.preferred_source = 'VA_GDX'
         AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
            THEN 'EXISTING_COMPATIBLE_POLICY'
        ELSE 'REVIEW_POLICY_COLLISION'
    END AS policy_coverage_status
FROM target_years y
CROSS JOIN medical_codes codes
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = codes.program_code
 AND COALESCE(m.valid_from_fiscal_year, -9999) <= y.fiscal_year
 AND COALESCE(m.valid_through_fiscal_year, 9999) >= y.fiscal_year
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
ORDER BY y.fiscal_year, codes.program_code;

-- ==========================================================================
-- SECTION 3 - EXISTING PROGRAM POLICY MAPPINGS
-- ==========================================================================
--
-- Show all existing policy mappings for the 15 programs.
-- No assumptions about policy-year applicability are made here.
-- ==========================================================================

\echo ''
\echo '3. EXISTING PROGRAM POLICY MAPPINGS'

WITH medical_codes(program_code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
)
SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.inflow_subfamily
FROM reference.federal_inflow_program_policy_mapping m
JOIN medical_codes codes
  ON codes.program_code = m.source_program_code
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
ORDER BY
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.methodology_version;


-- ==========================================================================
-- SECTION 4 - HISTORICAL POLICY-YEAR COLLISION CHECK
-- ==========================================================================
--
-- A collision exists when an existing policy mapping for one of the
-- 15 programs already covers FY2018 or FY2019.
--
-- All applicable mappings are reported, including those with
-- the same proposed EXCLUDE_DUPLICATE disposition.
-- ==========================================================================

\echo ''
\echo '4. FY2018-FY2019 POLICY-YEAR COLLISION CHECK'

WITH medical_codes(program_code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
),
target_years(fiscal_year) AS (
    VALUES (2018), (2019)
)
SELECT
    y.fiscal_year,
    codes.program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    CASE
        WHEN m.source_program_code IS NULL
            THEN 'NO_EXISTING_YEAR_POLICY'
        WHEN m.resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
            THEN 'REVIEW_EXISTING_DUPLICATE_POLICY'
        ELSE 'REVIEW_POLICY_COLLISION'
    END AS collision_status
FROM target_years y
CROSS JOIN medical_codes codes
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = codes.program_code
 AND COALESCE(m.valid_from_fiscal_year, -9999) <= y.fiscal_year
 AND COALESCE(m.valid_through_fiscal_year, 9999) >= y.fiscal_year
ORDER BY
    y.fiscal_year,
    codes.program_code,
    m.methodology_version;


-- ==========================================================================
-- SECTION 5 - GDX MEDICAL CARE ACCOUNTING CONTROLS
-- ==========================================================================
--
-- Revalidate the historical county-level Medical Care component.
-- This is an expenditure control, not a dollar-for-dollar
-- reconciliation to USAspending obligations.
-- ==========================================================================

\echo ''
\echo '5. GDX MEDICAL CARE ACCOUNTING CONTROLS'

SELECT
    e.fiscal_year,
    k.category_code,
    k.aggregation_role,
    COUNT(*) AS expenditure_rows,
    COUNT(DISTINCT e.county_id) AS counties,
    ROUND(SUM(e.expenditure_amount)::numeric, 2)
        AS expenditure_dollars,
    CASE
        WHEN e.fiscal_year = 2018
         AND COUNT(*) = 39
         AND COUNT(DISTINCT e.county_id) = 39
         AND ROUND(SUM(e.expenditure_amount)::numeric, 2)
             = 1526068781.09
            THEN 'PASS'
        WHEN e.fiscal_year = 2019
         AND COUNT(*) = 39
         AND COUNT(DISTINCT e.county_id) = 39
         AND ROUND(SUM(e.expenditure_amount)::numeric, 2)
             = 1665541164.21
            THEN 'PASS'
        ELSE 'FAIL'
    END AS control_status
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category k
  ON k.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
  AND k.category_code = 'MEDICAL_CARE'
  AND k.aggregation_role = 'COMPONENT'
GROUP BY
    e.fiscal_year,
    k.category_code,
    k.aggregation_role
ORDER BY e.fiscal_year;



-- ==========================================================================
-- SECTION 6 - SEPARATE REVIEW POPULATION: AL 64.029
-- ==========================================================================
--
-- Preserve AL 64.029 as a separate evidentiary case.
-- Not included in the 15-program certification population.
-- ==========================================================================

\echo ''
\echo '6. AL 64.029 - SEPARATE REVIEW CONTROL'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    BTRIM(c.cfda_number) AS program_code,
    MAX(c.cfda_title) AS program_title,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    CASE
        WHEN c.action_date_fiscal_year = 2018
         AND COUNT(*) = 468
         AND SUM(c.federal_action_obligation) = 152247509
            THEN 'PASS_SEPARATE'
        WHEN c.action_date_fiscal_year = 2019
         AND COUNT(*) = 468
         AND SUM(c.federal_action_obligation) = 164889075
            THEN 'PASS_SEPARATE'
        ELSE 'FAIL'
    END AS separation_status
FROM analysis.v_certified_assistance_ledger c
WHERE BTRIM(c.cfda_number) = '64.029'
  AND (
      (c.load_batch_id = 20 AND c.action_date_fiscal_year = 2018)
      OR
      (c.load_batch_id = 21 AND c.action_date_fiscal_year = 2019)
  )
GROUP BY
    c.action_date_fiscal_year,
    BTRIM(c.cfda_number)
ORDER BY fiscal_year;




-- ==========================================================================
-- SECTION 7 - PRE-MIGRATION CERTIFICATION SUMMARY
-- ==========================================================================

\echo ''
\echo '7. PRE-MIGRATION CERTIFICATION SUMMARY'

WITH medical_codes(program_code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
),
candidate AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.assistance_transaction_id,
        c.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger c
    JOIN medical_codes codes
      ON codes.program_code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20 AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21 AND c.action_date_fiscal_year = 2019)
),
population AS (
    SELECT
        COUNT(*) AS transactions,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_transactions,
        COUNT(DISTINCT (fiscal_year, program_code))
            AS program_years,
        SUM(federal_action_obligation) AS net_obligations
    FROM candidate
),
policy_review AS (
    SELECT
        COUNT(*) AS applicable_policy_rows,
        COUNT(*) FILTER (
            WHERE m.resolved_accounting_disposition <> 'EXCLUDE_DUPLICATE'
               OR s.preferred_source IS DISTINCT FROM 'VA_GDX'
               OR s.ledger_treatment IS DISTINCT FROM 'EXCLUDE_DUPLICATE'
        ) AS conflicting_policy_rows
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN medical_codes codes
      ON codes.program_code = m.source_program_code
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND (
          (
              COALESCE(m.valid_from_fiscal_year, -9999) <= 2018
              AND COALESCE(m.valid_through_fiscal_year, 9999) >= 2018
          )
          OR
          (
              COALESCE(m.valid_from_fiscal_year, -9999) <= 2019
              AND COALESCE(m.valid_through_fiscal_year, 9999) >= 2019
          )
      )
)
SELECT
    p.transactions,
    p.distinct_transactions,
    p.program_years,
    ROUND(p.net_obligations::numeric, 2) AS net_obligations,
    r.applicable_policy_rows,
    r.conflicting_policy_rows,
    CASE
        WHEN p.transactions <> 11818
          OR p.distinct_transactions <> 11818
          OR p.program_years <> 30
          OR p.net_obligations <> 2297804301
            THEN 'FAIL_POPULATION_CONTROL'
        WHEN r.conflicting_policy_rows > 0
            THEN 'REVIEW_POLICY_COLLISION'
        WHEN r.applicable_policy_rows > 0
            THEN 'REVIEW_EXISTING_COMPATIBLE_POLICY'
        ELSE 'PASS_POLICY_MAPPING_COLLISION_SCREEN'
    END AS certification_status
FROM population p
CROSS JOIN policy_review r;

ROLLBACK;

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M4 COMPLETE - READ ONLY - NO DATABASE WRITES'
\echo '=========================================================================='
