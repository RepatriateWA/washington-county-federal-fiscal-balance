
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223M - PREFERRED SOURCE CONTROL INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. ALL SOURCE POLICY FAMILIES AND FISCAL COVERAGE'

SELECT
    inflow_family,
    inflow_subfamily,
    COUNT(*) AS policy_records,
    MIN(valid_from_fiscal_year) AS earliest_start,
    MAX(valid_through_fiscal_year) AS latest_finite_end,
    STRING_AGG(
        DISTINCT methodology_version,
        ', ' ORDER BY methodology_version
    ) AS methodology_versions
FROM reference.federal_inflow_source_policy
GROUP BY inflow_family, inflow_subfamily
ORDER BY inflow_family, inflow_subfamily;

\echo ''
\echo '2. EXISTING PROGRAM MAPPING DISPOSITIONS'

SELECT
    p.resolved_accounting_disposition,
    s.inflow_family,
    s.inflow_subfamily,
    COUNT(DISTINCT p.source_program_code) AS mapped_programs,
    MIN(p.valid_from_fiscal_year) AS earliest_start,
    MAX(p.valid_through_fiscal_year) AS latest_finite_end
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
GROUP BY
    p.resolved_accounting_disposition,
    s.inflow_family,
    s.inflow_subfamily
ORDER BY
    s.inflow_family,
    s.inflow_subfamily,
    p.resolved_accounting_disposition;

COMMIT;

\echo 'ETL-223M COMPLETE - NO DATABASE WRITES'
