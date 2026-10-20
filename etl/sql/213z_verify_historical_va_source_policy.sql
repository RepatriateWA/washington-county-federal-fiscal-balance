
\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-213Z - FINAL VA SOURCE POLICY VERIFICATION'

BEGIN TRANSACTION READ ONLY;

SELECT
    methodology_version,
    inflow_subfamily,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND methodology_version IN (
      'ANALYSIS-213-v1',
      'ANALYSIS-149-v1',
      'ANALYSIS-209U-v1',
      'ANALYSIS-211L-v1',
      'ANALYSIS-211M-v1',
      'ANALYSIS-211N-v1'
  )
ORDER BY valid_from_fiscal_year, methodology_version;

SELECT
    COUNT(*) FILTER (
        WHERE methodology_version = 'ANALYSIS-213-v1'
          AND inflow_family = 'VETERANS_AFFAIRS'
          AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
          AND preferred_source = 'VA_GDX'
          AND allocation_source = 'VA_GDX'
          AND overlapping_sources =
              ARRAY['USASPENDING_PROCUREMENT']::text[]
          AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
          AND valid_from_fiscal_year = 2018
          AND valid_through_fiscal_year = 2019
    ) AS historical_procurement_policy,
    COUNT(*) FILTER (
        WHERE methodology_version = 'ANALYSIS-149-v1'
          AND valid_from_fiscal_year = 2024
          AND valid_through_fiscal_year = 2024
    ) AS fy2024_policy,
    COUNT(*) FILTER (
        WHERE methodology_version IN (
            'ANALYSIS-209U-v1',
            'ANALYSIS-211L-v1',
            'ANALYSIS-211M-v1',
            'ANALYSIS-211N-v1'
        )
          AND valid_from_fiscal_year = 2018
          AND valid_through_fiscal_year = 2019
    ) AS historical_assistance_policies
FROM reference.federal_inflow_source_policy;

ROLLBACK;

\echo 'ETL-213Z COMPLETE - NO DATABASE WRITES'
