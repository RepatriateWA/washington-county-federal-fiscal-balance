
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223L - ACCOUNTING POLICY INVENTORY'
\echo 'FY2018-FY2019 / READ ONLY'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. ALL EXISTING PROGRAM POLICY MAPPINGS'

SELECT
    p.source_program_code,
    p.source_system,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version,
    p.mapping_basis,
    s.inflow_family,
    s.inflow_subfamily,
    s.methodology_version AS source_policy_version
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE BTRIM(p.source_program_code) IN (
    '10.557','10.561','10.924','93.527','93.563'
)
ORDER BY
    p.source_program_code,
    p.valid_from_fiscal_year,
    p.methodology_version;

\echo ''
\echo '2. EXISTING SOURCE POLICY FAMILIES'

SELECT
    inflow_family,
    inflow_subfamily,
    COUNT(*) AS policy_count,
    MIN(valid_from_fiscal_year) AS earliest_start,
    MAX(valid_through_fiscal_year) AS latest_finite_end
FROM reference.federal_inflow_source_policy
WHERE
    inflow_family ILIKE '%NUTRITION%'
    OR inflow_family ILIKE '%AGRICULT%'
    OR inflow_family ILIKE '%HEALTH%'
    OR inflow_family ILIKE '%CHILD%'
    OR inflow_family ILIKE '%CONSERV%'
    OR inflow_subfamily ILIKE '%NUTRITION%'
    OR inflow_subfamily ILIKE '%SNAP%'
    OR inflow_subfamily ILIKE '%WIC%'
    OR inflow_subfamily ILIKE '%HEALTH%'
    OR inflow_subfamily ILIKE '%CHILD%'
    OR inflow_subfamily ILIKE '%CONSERV%'
GROUP BY inflow_family, inflow_subfamily
ORDER BY inflow_family, inflow_subfamily;

\echo ''
\echo '3. TARGET PROGRAM TRANSACTION CONTROLS'

SELECT
    BTRIM(cfda_number) AS program_code,
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation), 2)
        AS net_obligations,
    ROUND(SUM(ABS(federal_action_obligation)), 2)
        AS absolute_activity
FROM analysis.v_certified_assistance_ledger
WHERE (
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND BTRIM(cfda_number) IN (
    '10.557','10.561','10.924','93.527','93.563'
)
GROUP BY BTRIM(cfda_number), action_date_fiscal_year
ORDER BY program_code, fiscal_year;

COMMIT;

\echo 'ETL-223L COMPLETE - NO DATABASE WRITES'
