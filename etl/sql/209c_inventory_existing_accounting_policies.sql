
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209C - EXISTING ACCOUNTING POLICY INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN READ ONLY;

\echo ''
\echo '1. ACCOUNTING CONTROL TABLES AND ROW COUNTS'

SELECT
    'PROGRAM_CLASSIFICATION' AS policy_layer,
    COUNT(*) AS rows
FROM reference.federal_inflow_program_classification

UNION ALL

SELECT
    'SOURCE_POLICY',
    COUNT(*)
FROM reference.federal_inflow_source_policy

UNION ALL

SELECT
    'PROGRAM_POLICY_MAPPING',
    COUNT(*)
FROM reference.federal_inflow_program_policy_mapping

UNION ALL

SELECT
    'AWARD_CLASSIFICATION',
    COUNT(*)
FROM reference.federal_inflow_award_classification

ORDER BY policy_layer;

\echo ''
\echo '2. SOURCE POLICY COVERAGE'

SELECT
    preferred_source,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS policy_count
FROM reference.federal_inflow_source_policy
GROUP BY 1, 2, 3, 4
ORDER BY 3 NULLS FIRST, 4 NULLS LAST, 1, 2;

\echo ''
\echo '3. PROGRAM POLICY COVERAGE BY YEAR AND DISPOSITION'

WITH years AS (
    SELECT generate_series(2015, 2025) AS fiscal_year
)
SELECT
    y.fiscal_year,
    m.resolved_accounting_disposition,
    COUNT(*) AS matching_policy_rows,
    COUNT(DISTINCT (
        m.source_system,
        m.source_program_code
    )) AS distinct_programs
FROM years y
JOIN reference.federal_inflow_program_policy_mapping m
  ON (
      m.valid_from_fiscal_year IS NULL
      OR y.fiscal_year >= m.valid_from_fiscal_year
  )
 AND (
      m.valid_through_fiscal_year IS NULL
      OR y.fiscal_year <= m.valid_through_fiscal_year
  )
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '4. AWARD CLASSIFICATION COVERAGE BY YEAR AND DISPOSITION'

WITH years AS (
    SELECT generate_series(2015, 2025) AS fiscal_year
)
SELECT
    y.fiscal_year,
    a.accounting_disposition,
    COUNT(*) AS matching_classification_rows,
    COUNT(DISTINCT (
        a.source_system,
        a.source_program_code,
        a.source_award_identifier
    )) AS distinct_awards
FROM years y
JOIN reference.federal_inflow_award_classification a
  ON (
      a.valid_from_fiscal_year IS NULL
      OR y.fiscal_year >= a.valid_from_fiscal_year
  )
 AND (
      a.valid_through_fiscal_year IS NULL
      OR y.fiscal_year <= a.valid_through_fiscal_year
  )
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '5. ACCOUNTING METHODOLOGY VERSIONS'

SELECT
    'PROGRAM_POLICY_MAPPING' AS policy_layer,
    methodology_version,
    COUNT(*) AS policy_rows
FROM reference.federal_inflow_program_policy_mapping
GROUP BY methodology_version

UNION ALL

SELECT
    'AWARD_CLASSIFICATION',
    methodology_version,
    COUNT(*)
FROM reference.federal_inflow_award_classification
GROUP BY methodology_version

UNION ALL

SELECT
    'SOURCE_POLICY',
    methodology_version,
    COUNT(*)
FROM reference.federal_inflow_source_policy
GROUP BY methodology_version

ORDER BY policy_layer, methodology_version;

\echo ''
\echo '6. HISTORICAL HCV POLICY ROWS'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.federal_inflow_source_policy_id,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '14.871'
ORDER BY
    m.valid_from_fiscal_year,
    m.methodology_version;

\echo ''
\echo '7. POSSIBLE OVERLAPPING PROGRAM POLICY WINDOWS'

SELECT
    a.source_program_code,
    a.methodology_version AS methodology_a,
    b.methodology_version AS methodology_b,
    a.federal_inflow_program_policy_mapping_id AS mapping_a,
    b.federal_inflow_program_policy_mapping_id AS mapping_b,
    a.resolved_accounting_disposition AS disposition_a,
    b.resolved_accounting_disposition AS disposition_b
FROM reference.federal_inflow_program_policy_mapping a
JOIN reference.federal_inflow_program_policy_mapping b
  ON a.federal_inflow_program_policy_mapping_id
     < b.federal_inflow_program_policy_mapping_id
 AND a.source_system = b.source_system
 AND a.source_program_code = b.source_program_code
 AND COALESCE(a.valid_from_fiscal_year, -9999)
     <= COALESCE(b.valid_through_fiscal_year, 9999)
 AND COALESCE(b.valid_from_fiscal_year, -9999)
     <= COALESCE(a.valid_through_fiscal_year, 9999)
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
ORDER BY a.source_program_code, mapping_a, mapping_b;

ROLLBACK;

\echo 'ETL-209C COMPLETE - NO DATABASE WRITES'
