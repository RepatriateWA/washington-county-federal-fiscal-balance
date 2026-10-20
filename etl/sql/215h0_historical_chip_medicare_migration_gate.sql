
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215H0 - HISTORICAL CHIP / MEDICARE MIGRATION GATE'
\echo 'FY2018-FY2019 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. POLICY TABLE COLUMN DEFINITIONS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_award_classification'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '2. POLICY TABLE CONSTRAINTS'

SELECT
    c.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'reference'
  AND c.relname IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_award_classification'
  )
ORDER BY c.relname, con.conname;

\echo ''
\echo '3. HISTORICAL SOURCE COUNTS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND BTRIM(cfda_number) IN ('93.767', '93.770')
GROUP BY 1, 2
ORDER BY 2, 1;

\echo ''
\echo '4. EXISTING MEDICARE SOURCE POLICY'

SELECT
    s.federal_inflow_source_policy_id,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.methodology_version,
    s.valid_from_fiscal_year,
    s.valid_through_fiscal_year
FROM reference.federal_inflow_source_policy s
WHERE s.inflow_family = 'MEDICARE'
  AND s.inflow_subfamily = 'PRESCRIPTION_DRUG_COVERAGE';

\echo ''
\echo '5. EXISTING CHIP SOURCE POLICIES'

SELECT
    s.federal_inflow_source_policy_id,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.methodology_version,
    s.valid_from_fiscal_year,
    s.valid_through_fiscal_year
FROM reference.federal_inflow_source_policy s
WHERE s.inflow_family = 'CHIP';

\echo ''
\echo '6. EXACT TARGET AWARD COLLISION INVENTORY'

WITH target(award_identifier) AS (
    VALUES
        ('1805WA5021'),
        ('1905WA5021'),
        ('1Y1CMS331701')
)
SELECT
    t.award_identifier,
    a.federal_inflow_award_classification_id,
    a.accounting_disposition,
    a.methodology_version,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year
FROM target t
LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = '93.767'
 AND a.source_award_identifier = t.award_identifier
ORDER BY t.award_identifier, a.valid_from_fiscal_year;

\echo ''
\echo '7. MEDICARE PROGRAM MAPPING COLLISION INVENTORY'

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
  AND m.source_program_code = '93.770'
ORDER BY m.valid_from_fiscal_year;

\echo ''
\echo '8. TARGET METHODOLOGY VERSION COLLISIONS'

SELECT
    'source_policy' AS policy_layer,
    COUNT(*) AS existing_records
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-215H-v1'

UNION ALL

SELECT
    'program_mapping',
    COUNT(*)
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-215H-v1'

UNION ALL

SELECT
    'award_classification',
    COUNT(*)
FROM reference.federal_inflow_award_classification
WHERE methodology_version = 'ANALYSIS-215H-v1';

ROLLBACK;

\echo ''
\echo 'ETL-215H0 COMPLETE - READ ONLY'
