
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211M2 - HISTORICAL VA MEDICAL POLICY CANDIDATES'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. HISTORICAL PROGRAM CLASSIFICATIONS'

SELECT
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN (
      '64.041','64.012','64.029',
      '64.040','64.045','64.048',
      '64.047','64.013','64.050',
      '64.042','64.049','64.039',
      '64.046','64.044','64.043'
  )
ORDER BY source_program_code,
         valid_from_fiscal_year,
         methodology_version;

\echo ''
\echo '2. FY2020-FY2024 ACCOUNTING POLICY PRECEDENT'

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
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN (
      '64.041','64.012','64.029',
      '64.040','64.045','64.048',
      '64.047','64.013','64.050',
      '64.042','64.049','64.039',
      '64.046','64.044','64.043'
  )
  AND COALESCE(m.valid_from_fiscal_year, -9999)
      <= 2024
  AND COALESCE(m.valid_through_fiscal_year, 9999)
      >= 2020
ORDER BY m.source_program_code,
         m.valid_from_fiscal_year,
         m.methodology_version;

\echo ''
\echo '3. FY2018-FY2019 CANDIDATE TRANSACTION CONTROLS'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    BTRIM(c.cfda_number) AS program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(c.federal_action_obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM analysis.v_certified_assistance_ledger c
WHERE (
    (c.load_batch_id = 20
     AND c.action_date_fiscal_year = 2018)
    OR
    (c.load_batch_id = 21
     AND c.action_date_fiscal_year = 2019)
)
AND BTRIM(c.cfda_number) IN (
    '64.041','64.012','64.029',
    '64.040','64.045','64.048',
    '64.047','64.013','64.050',
    '64.042','64.049','64.039',
    '64.046','64.044','64.043'
)
GROUP BY c.action_date_fiscal_year,
         BTRIM(c.cfda_number)
ORDER BY fiscal_year, net_obligations DESC;

ROLLBACK;

\echo ''
\echo 'ETL-211M2 COMPLETE - NO DATABASE WRITES'
