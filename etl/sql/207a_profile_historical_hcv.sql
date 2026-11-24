\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '======================================================================'
\echo 'ETL-207A - FY2018/FY2019 HISTORICAL HOUSING CHOICE VOUCHER PROFILE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '======================================================================'

-- ------------------------------------------------------------
-- 1. HISTORICAL SOURCE POPULATION
-- ------------------------------------------------------------

\echo ''
\echo '=== 1. HISTORICAL HCV SOURCE POPULATION ==='

SELECT
    load_batch_id,
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation > 0
    ) AS positive_transactions,
    ROUND(SUM(federal_action_obligation::numeric), 2)
        AS net_obligations,
    ROUND(
        SUM(
            CASE
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation::numeric
                ELSE 0
            END
        ), 2
    ) AS positive_obligations,
    ROUND(
        SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation::numeric
                ELSE 0
            END
        ), 2
    ) AS negative_obligations
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '14.871'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY
    load_batch_id,
    action_date_fiscal_year
ORDER BY fiscal_year;


-- ------------------------------------------------------------
-- 2. SOURCE-VIEW COLUMN INVENTORY
-- Avoid assumptions about award and recipient field names.
-- ------------------------------------------------------------

\echo ''
\echo '=== 2. CERTIFIED LEDGER VIEW COLUMN INVENTORY ==='

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name = 'v_certified_assistance_ledger'
ORDER BY ordinal_position;


-- ------------------------------------------------------------
-- 3. HISTORICAL HUD ASSISTANCE PROGRAM COMPARISON
-- ------------------------------------------------------------

\echo ''
\echo '=== 3. RELATED HISTORICAL HUD PROGRAMS ==='

SELECT
    action_date_fiscal_year AS fiscal_year,
    TRIM(cfda_number) AS program_code,
    COUNT(*) AS transactions,
    ROUND(
        SUM(federal_action_obligation::numeric), 2
    ) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
  AND TRIM(cfda_number) IN (
      '14.871',  -- Housing Choice Vouchers
      '14.195',  -- Project-Based Rental Assistance
      '14.850',  -- Public Housing Operating Fund
      '14.872',  -- Public Housing Capital Fund
      '14.879',  -- Mainstream Vouchers
      '14.267'   -- Continuum of Care
  )
GROUP BY
    action_date_fiscal_year,
    TRIM(cfda_number)
ORDER BY
    fiscal_year,
    program_code;


-- ------------------------------------------------------------
-- 4. EXISTING HCV ACCOUNTING POLICY
-- ------------------------------------------------------------

\echo ''
\echo '=== 4. CURRENT HCV POLICY MAPPING ==='

SELECT
    m.source_system,
    m.source_program_code,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.resolved_accounting_disposition,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '14.871'
ORDER BY m.valid_from_fiscal_year;


-- ------------------------------------------------------------
-- 5. EXISTING HCV CLASSIFICATION AND VALIDITY
-- ------------------------------------------------------------

\echo ''
\echo '=== 5. CURRENT HCV PROGRAM CLASSIFICATION ==='

SELECT
    source_system,
    source_program_code,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '14.871'
ORDER BY valid_from_fiscal_year;


-- ------------------------------------------------------------
-- 6. INDEPENDENT TOTAL CONTROL
-- ------------------------------------------------------------

\echo ''
\echo '=== 6. COMBINED HISTORICAL HCV CONTROL ==='

WITH historical AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        federal_action_obligation::numeric AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE TRIM(cfda_number) = '14.871'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      )
)
SELECT
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE fiscal_year = 2018)
        AS fy2018_transactions,
    COUNT(*) FILTER (WHERE fiscal_year = 2019)
        AS fy2019_transactions,
    ROUND(SUM(obligation), 2) AS combined_net_obligations,
    ROUND(
        SUM(obligation) FILTER (WHERE fiscal_year = 2018), 2
    ) AS fy2018_net_obligations,
    ROUND(
        SUM(obligation) FILTER (WHERE fiscal_year = 2019), 2
    ) AS fy2019_net_obligations
FROM historical;

COMMIT;

\echo 'ETL-207A READ-ONLY PROFILE COMPLETE'