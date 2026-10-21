
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223N3 - POST-MIGRATION CERTIFICATION'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. CERTIFIED SOURCE POLICIES AND MAPPINGS'

SELECT
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year AS mapping_start,
    p.valid_through_fiscal_year AS mapping_end,
    s.inflow_family,
    s.inflow_subfamily,
    s.ledger_treatment,
    s.preferred_source,
    s.valid_from_fiscal_year AS policy_start,
    s.valid_through_fiscal_year AS policy_end,
    p.methodology_version AS mapping_version,
    s.methodology_version AS source_version
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.methodology_version = 'ANALYSIS-223N-v1'
ORDER BY p.source_program_code;

\echo ''
\echo '2. FY2018-FY2019 TRANSACTION ACCOUNTING CONTROLS'

WITH target AS (
    SELECT
        BTRIM(v.cfda_number) AS program_code,
        v.action_date_fiscal_year AS fiscal_year,
        v.federal_action_obligation AS amount
    FROM analysis.v_certified_assistance_ledger v
    WHERE (
        (v.load_batch_id = 20
         AND v.action_date_fiscal_year = 2018)
        OR
        (v.load_batch_id = 21
         AND v.action_date_fiscal_year = 2019)
    )
      AND BTRIM(v.cfda_number) IN (
          '10.557','10.561','10.924','93.527','93.563'
      )
)
SELECT
    t.program_code,
    t.fiscal_year,
    p.resolved_accounting_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(COALESCE(t.amount, 0)), 2)
        AS net_obligations,
    ROUND(SUM(ABS(COALESCE(t.amount, 0))), 2)
        AS absolute_activity
FROM target t
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = t.program_code
 AND p.methodology_version = 'ANALYSIS-223N-v1'
 AND t.fiscal_year >= p.valid_from_fiscal_year
 AND t.fiscal_year <= p.valid_through_fiscal_year
GROUP BY
    t.program_code,
    t.fiscal_year,
    p.resolved_accounting_disposition
ORDER BY t.program_code, t.fiscal_year;

\echo ''
\echo '3. TOTAL COVERAGE AND POLICY VALIDITY'

WITH target AS (
    SELECT
        BTRIM(v.cfda_number) AS program_code,
        v.action_date_fiscal_year AS fiscal_year,
        v.federal_action_obligation AS amount
    FROM analysis.v_certified_assistance_ledger v
    WHERE (
        (v.load_batch_id = 20
         AND v.action_date_fiscal_year = 2018)
        OR
        (v.load_batch_id = 21
         AND v.action_date_fiscal_year = 2019)
    )
      AND BTRIM(v.cfda_number) IN (
          '10.557','10.561','10.924','93.527','93.563'
      )
)
SELECT
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE p.federal_inflow_program_policy_mapping_id IS NOT NULL
    ) AS mapped_transactions,
    COUNT(*) FILTER (
        WHERE p.federal_inflow_program_policy_mapping_id IS NULL
    ) AS unmapped_transactions,
    ROUND(SUM(t.amount), 2) AS net_obligations,
    ROUND(SUM(t.amount) FILTER (
        WHERE p.resolved_accounting_disposition =
              'INCLUDE_ADDITIVE'
    ), 2) AS mapped_net_obligations
FROM target t
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = t.program_code
 AND p.methodology_version = 'ANALYSIS-223N-v1'
 AND t.fiscal_year BETWEEN
     p.valid_from_fiscal_year AND p.valid_through_fiscal_year;

\echo ''
\echo '4. DISCOVER AWARD-SPECIFIC ACCOUNTING STRUCTURES'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema IN (
    'reference','analysis','assistance'
)
  AND (
      column_name ILIKE '%accounting_disposition%'
      OR column_name ILIKE '%accounting_classification%'
      OR column_name ILIKE '%source_policy%'
      OR column_name ILIKE '%overlap%'
  )
ORDER BY table_schema, table_name, ordinal_position;

COMMIT;

\echo 'ETL-223N3 COMPLETE - NO DATABASE WRITES'
