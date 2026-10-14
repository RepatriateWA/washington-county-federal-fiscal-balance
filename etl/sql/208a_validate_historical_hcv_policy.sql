\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-208A - HISTORICAL HCV POST-MIGRATION VALIDATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo '=== 1. NEW HISTORICAL POLICY ==='

SELECT
    p.federal_inflow_source_policy_id,
    p.methodology_version,
    p.preferred_source,
    p.accounting_measure,
    p.allocation_source,
    p.ledger_treatment,
    p.overlapping_sources,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year
FROM reference.federal_inflow_source_policy p
WHERE p.methodology_version = 'ANALYSIS-208-v1';

\echo '=== 2. NEW PROGRAM CLASSIFICATION ==='

SELECT
    source_system,
    source_program_code,
    overlap_risk,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE methodology_version = 'ANALYSIS-208-v1';

\echo '=== 3. NEW PROGRAM MAPPING ==='

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.federal_inflow_source_policy_id,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
WHERE m.methodology_version = 'ANALYSIS-208-v1';

\echo '=== 4. ORIGINAL FY2020-FY2024 POLICY PRESERVATION ==='

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.federal_inflow_source_policy_id,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
WHERE m.federal_inflow_program_policy_mapping_id = 76;

\echo '=== 5. HISTORICAL HCV SOURCE RECONCILIATION ==='

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT c.assistance_award_unique_key) AS awards,
    SUM(c.federal_action_obligation) AS net_obligations,
    COUNT(*) FILTER (
        WHERE c.federal_action_obligation < 0
    ) AS negative_transactions
FROM analysis.v_certified_assistance_ledger c
WHERE TRIM(c.cfda_number) = '14.871'
  AND (
       (c.load_batch_id = 20 AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21 AND c.action_date_fiscal_year = 2019)
  )
GROUP BY c.action_date_fiscal_year
ORDER BY fiscal_year;

\echo '=== 6. HISTORICAL POLICY APPLICABILITY ==='

WITH historical AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        c.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger c
    WHERE TRIM(c.cfda_number) = '14.871'
      AND (
           (c.load_batch_id = 20 AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21 AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    h.fiscal_year,
    COUNT(*) AS transactions,
    SUM(h.federal_action_obligation) AS net_obligations,
    COUNT(m.federal_inflow_program_policy_mapping_id)
        AS matching_policy_rows,
    COUNT(*) FILTER (
        WHERE m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
    ) AS additive_transactions,
    COALESCE(SUM(h.federal_action_obligation) FILTER (
        WHERE m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
    ), 0) AS additive_obligations
FROM historical h
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = '14.871'
 AND h.fiscal_year BETWEEN
     m.valid_from_fiscal_year AND m.valid_through_fiscal_year
GROUP BY h.fiscal_year
ORDER BY h.fiscal_year;

\echo '=== 7. DOWNSTREAM LEDGER VIEW INVENTORY ==='

SELECT
    table_schema,
    table_name
FROM information_schema.views
WHERE table_schema = 'analysis'
  AND (
       table_name ILIKE '%ledger%'
    OR table_name ILIKE '%inflow%'
    OR table_name ILIKE '%disposition%'
  )
ORDER BY table_name;

COMMIT;

\echo 'ETL-208A READ-ONLY VALIDATION COMPLETE'