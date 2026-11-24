
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo ''
\echo '======================================================================'
\echo 'ETL-211M6A - VA MEDICAL CARE PRE-MIGRATION AUTHORIZATION'
\echo '======================================================================'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo 'AL 64.029 IS EXCLUDED FROM THIS AUTHORIZATION'
\echo '======================================================================'

BEGIN TRANSACTION READ ONLY;

-- SECTION 1: CERTIFIED CANDIDATE POPULATION

\echo ''
\echo '1. CERTIFIED CANDIDATE POPULATION'

WITH medical_codes(code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
),
candidate AS (
    SELECT c.*
    FROM analysis.v_certified_assistance_ledger c
    JOIN medical_codes m
      ON BTRIM(c.cfda_number) = m.code
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
)
SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT BTRIM(cfda_number))
        AS programs,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    CASE
        WHEN action_date_fiscal_year = 2018
         AND COUNT(*) = 5999
         AND COUNT(DISTINCT assistance_transaction_id) = 5999
         AND COUNT(DISTINCT BTRIM(cfda_number)) = 15
         AND SUM(federal_action_obligation) = 1133039687
            THEN 'PASS'
        WHEN action_date_fiscal_year = 2019
         AND COUNT(*) = 5819
         AND COUNT(DISTINCT assistance_transaction_id) = 5819
         AND COUNT(DISTINCT BTRIM(cfda_number)) = 15
         AND SUM(federal_action_obligation) = 1164764614
            THEN 'PASS'
        ELSE 'FAIL'
    END AS control_status
FROM candidate
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;


-- SECTION 2: HISTORICAL POLICY COLLISIONS

\echo ''
\echo '2. HISTORICAL POLICY COLLISIONS'

WITH medical_codes(code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
),
years(fiscal_year) AS (
    VALUES (2018), (2019)
)
SELECT
    y.fiscal_year,
    COUNT(m.federal_inflow_program_policy_mapping_id)
        AS applicable_policy_rows,
    CASE
        WHEN COUNT(m.federal_inflow_program_policy_mapping_id) = 0
            THEN 'PASS_NO_COLLISION'
        ELSE 'REVIEW_COLLISION'
    END AS control_status
FROM years y
CROSS JOIN medical_codes codes
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(m.source_program_code) = codes.code
 AND (
     m.valid_from_fiscal_year IS NULL
     OR m.valid_from_fiscal_year <= y.fiscal_year
 )
 AND (
     m.valid_through_fiscal_year IS NULL
     OR m.valid_through_fiscal_year >= y.fiscal_year
 )
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;


-- SECTION 3: AWARD CLASSIFICATION COLLISIONS

\echo ''
\echo '3. AWARD CLASSIFICATION COLLISIONS'

WITH medical_codes(code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
)
SELECT
    COUNT(*) AS classification_rows,
    COUNT(*) FILTER (
        WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
    ) AS additive_rows,
    COUNT(*) FILTER (
        WHERE accounting_disposition = 'EXCLUDE_DUPLICATE'
    ) AS duplicate_exclusion_rows,
    CASE
        WHEN COUNT(*) = 0
            THEN 'PASS_NO_AWARD_COLLISION'
        ELSE 'REVIEW_AWARD_CLASSIFICATIONS'
    END AS control_status
FROM reference.federal_inflow_award_classification a
JOIN medical_codes codes
  ON BTRIM(a.source_program_code) = codes.code
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND (
      (
          COALESCE(a.valid_from_fiscal_year, -9999) <= 2018
          AND COALESCE(a.valid_through_fiscal_year, 9999) >= 2018
      )
      OR
      (
          COALESCE(a.valid_from_fiscal_year, -9999) <= 2019
          AND COALESCE(a.valid_through_fiscal_year, 9999) >= 2019
      )
  );


-- SECTION 4: EXISTING POLICY PRECEDENT

\echo ''
\echo '4. FY2020-FY2024 POLICY PRECEDENT'

SELECT
    m.source_program_code,
    m.methodology_version,
    m.resolved_accounting_disposition,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    s.federal_inflow_source_policy_id,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.inflow_subfamily
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(m.source_program_code) IN (
      '64.011', '64.012', '64.013',
      '64.039', '64.040', '64.041',
      '64.042', '64.043', '64.044',
      '64.045', '64.046', '64.047',
      '64.048', '64.049', '64.050'
  )
ORDER BY
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.methodology_version;


-- SECTION 5: SOURCE POLICY IDENTITY

\echo ''
\echo '5. SOURCE POLICY IDENTITY'

SELECT
    federal_inflow_source_policy_id,
    preferred_source,
    allocation_source,
    ledger_treatment,
    inflow_subfamily,
    methodology_version
FROM reference.federal_inflow_source_policy
WHERE preferred_source = 'VA_GDX'
  AND ledger_treatment = 'EXCLUDE_DUPLICATE'
ORDER BY
    federal_inflow_source_policy_id;


-- SECTION 6: AL 64.029 SEPARATION

\echo ''
\echo '6. AL 64.029 SEPARATION CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '64.029'
  AND (
      (load_batch_id = 20 AND action_date_fiscal_year = 2018)
      OR
      (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

ROLLBACK;

\echo ''
\echo '======================================================================'
\echo 'ETL-211M6A COMPLETE - READ ONLY'
\echo '======================================================================'
