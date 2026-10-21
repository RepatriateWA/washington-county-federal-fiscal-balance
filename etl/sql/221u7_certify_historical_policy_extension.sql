\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-221U7 - HISTORICAL POLICY EXTENSION CERTIFICATION'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. COMMITTED POLICY COUNTS'

SELECT
    (SELECT COUNT(*)
     FROM reference.federal_inflow_source_policy
     WHERE methodology_version LIKE
           'ANALYSIS-221U-HIST-v1-SRC-%') AS source_policies,
    (SELECT COUNT(*)
     FROM reference.federal_inflow_program_policy_mapping
     WHERE methodology_version =
           'ANALYSIS-221U-HIST-v1') AS program_mappings;

\echo ''
\echo '2. HISTORICAL PROGRAM DISPOSITION COUNTS'

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS program_count
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-221U-HIST-v1'
GROUP BY resolved_accounting_disposition
ORDER BY resolved_accounting_disposition;

\echo ''
\echo '3. HISTORICAL OBLIGATION CONTROL BY YEAR'

SELECT
    t.action_date_fiscal_year AS fiscal_year,
    m.resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT t.cfda_number) AS distinct_programs,
    ROUND(SUM(t.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger t
JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = t.cfda_number
 AND m.methodology_version = 'ANALYSIS-221U-HIST-v1'
 AND t.action_date_fiscal_year BETWEEN
     m.valid_from_fiscal_year
     AND m.valid_through_fiscal_year
WHERE t.load_batch_id IN (20, 21)
  AND t.action_date_fiscal_year IN (2018, 2019)
GROUP BY
    t.action_date_fiscal_year,
    m.resolved_accounting_disposition
ORDER BY 1, 2;

\echo ''
\echo '4. INVALID SOURCE POLICY LINKAGES'

SELECT
    m.source_program_code,
    m.federal_inflow_source_policy_id
FROM reference.federal_inflow_program_policy_mapping m
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-221U-HIST-v1'
  AND (
      s.federal_inflow_source_policy_id IS NULL
      OR COALESCE(s.valid_from_fiscal_year, 9999) > 2018
      OR COALESCE(s.valid_through_fiscal_year, -9999) < 2019
  );

\echo ''
\echo '5. HISTORICAL MAPPING COLLISIONS'

SELECT
    a.source_program_code,
    COUNT(*) AS conflicting_mapping_rows
FROM reference.federal_inflow_program_policy_mapping a
JOIN reference.federal_inflow_program_policy_mapping b
  ON b.source_system = a.source_system
 AND b.source_program_code = a.source_program_code
 AND b.federal_inflow_program_policy_mapping_id <>
     a.federal_inflow_program_policy_mapping_id
 AND COALESCE(b.valid_from_fiscal_year, -9999) <= 2019
 AND COALESCE(b.valid_through_fiscal_year, 9999) >= 2018
WHERE a.methodology_version = 'ANALYSIS-221U-HIST-v1'
GROUP BY a.source_program_code
ORDER BY a.source_program_code;

\echo ''
\echo '6. INDEPENDENT CERTIFICATION GATE'

DO $$
DECLARE
    v_sources integer;
    v_mappings integer;
    v_invalid integer;
    v_collisions integer;
    v_add integer;
    v_exclude integer;
    v_reference integer;
    v_withheld integer;
BEGIN
    SELECT COUNT(*)
    INTO v_sources
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version LIKE
          'ANALYSIS-221U-HIST-v1-SRC-%'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-221U-HIST-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_invalid
    FROM reference.federal_inflow_program_policy_mapping m
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.methodology_version = 'ANALYSIS-221U-HIST-v1'
      AND (
          s.federal_inflow_source_policy_id IS NULL
          OR COALESCE(s.valid_from_fiscal_year, 9999) > 2018
          OR COALESCE(s.valid_through_fiscal_year, -9999) < 2019
      );

    SELECT COUNT(*)
    INTO v_collisions
    FROM reference.federal_inflow_program_policy_mapping a
    JOIN reference.federal_inflow_program_policy_mapping b
      ON b.source_system = a.source_system
     AND b.source_program_code = a.source_program_code
     AND b.federal_inflow_program_policy_mapping_id <>
         a.federal_inflow_program_policy_mapping_id
     AND COALESCE(b.valid_from_fiscal_year, -9999) <= 2019
     AND COALESCE(b.valid_through_fiscal_year, 9999) >= 2018
    WHERE a.methodology_version = 'ANALYSIS-221U-HIST-v1';

    SELECT
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'INCLUDE_ADDITIVE'),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'REFERENCE_ONLY'),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED')
    INTO v_add, v_exclude, v_reference, v_withheld
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-221U-HIST-v1';

    IF v_sources <> 17
       OR v_mappings <> 33
       OR v_invalid <> 0
       OR v_collisions <> 0
       OR v_add <> 14
       OR v_exclude <> 7
       OR v_reference <> 3
       OR v_withheld <> 9
    THEN
        RAISE EXCEPTION
            'ETL-221U7 CERTIFICATION FAILED';
    END IF;

    RAISE NOTICE
        'ETL-221U7 CERTIFICATION PASS: 17 sources, 33 mappings, zero invalid links, zero collisions';
END $$;

ROLLBACK;

\echo 'ETL-221U7 COMPLETE - NO DATABASE WRITES'