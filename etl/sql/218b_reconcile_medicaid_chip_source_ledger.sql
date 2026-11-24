
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218B - MEDICAID/CHIP SOURCE-TO-LEDGER RECONCILIATION'
\echo 'FY2018-FY2024 / READ ONLY / DISCOVERY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. SOURCE TABLE AND VIEW DEFINITIONS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'BASE TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE c.relkind::text
    END AS object_type,
    pg_get_viewdef(c.oid, true) AS view_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (
    n.nspname = 'cms'
    AND c.relname IN (
        'medicaid_service_expenditures',
        'medicaid_state_control_total'
    )
)
OR (
    n.nspname = 'reporting'
    AND c.relname IN (
        'v_washington_medicaid_expenditures',
        'v_washington_chip_expenditures'
    )
)
OR (
    n.nspname = 'analysis'
    AND c.relname IN (
        'v_certified_assistance_ledger',
        'v_assistance_transaction_observation_ledger'
    )
)
ORDER BY n.nspname,c.relname;

\echo ''
\echo '2. SOURCE AND LEDGER COLUMN INVENTORY'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE (
    table_schema = 'cms'
    AND table_name IN (
        'medicaid_service_expenditures',
        'medicaid_state_control_total'
    )
)
OR (
    table_schema = 'reporting'
    AND table_name IN (
        'v_washington_medicaid_expenditures',
        'v_washington_chip_expenditures'
    )
)
OR (
    table_schema = 'analysis'
    AND table_name IN (
        'v_certified_assistance_ledger',
        'v_assistance_transaction_observation_ledger'
    )
)
ORDER BY table_schema,table_name,ordinal_position;

\echo ''
\echo '3. SOURCE ROW COUNTS'

SELECT
    'cms.medicaid_service_expenditures' AS source_object,
    COUNT(*) AS source_rows
FROM cms.medicaid_service_expenditures

UNION ALL

SELECT
    'cms.medicaid_state_control_total',
    COUNT(*)
FROM cms.medicaid_state_control_total;

\echo ''
\echo '4. CERTIFIED CMS REPORTING CONTROLS'

WITH controls AS (
    SELECT
        'MEDICAID'::text AS program,
        fiscal_year,
        federal_expenditure_amount::numeric AS dollars,
        amount_method,
        is_additive_to_fiscal_balance
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL

    SELECT
        'CHIP',
        fiscal_year,
        federal_expenditure_amount::numeric,
        amount_method,
        is_additive_to_fiscal_balance
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
)
SELECT *
FROM controls
ORDER BY fiscal_year,program;

\echo ''
\echo '5. CORE MEDICAID AND CHIP SOURCE POLICIES'

SELECT
    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.source_selection_basis,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year
FROM reference.federal_inflow_source_policy p
WHERE (
    p.inflow_family = 'MEDICAID'
    AND p.inflow_subfamily = 'MEDICAID_STATE_EXPENDITURES'
)
OR (
    UPPER(COALESCE(p.inflow_family,'')) LIKE '%CHIP%'
    OR UPPER(COALESCE(p.inflow_subfamily,'')) LIKE '%CHIP%'
)
ORDER BY p.inflow_family,p.inflow_subfamily,
         p.valid_from_fiscal_year;

\echo ''
\echo '6. OVERLAP MAPPINGS FOR CORE PROGRAMS'

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_program_code IN ('93.778','93.767')
ORDER BY m.source_program_code,
         m.valid_from_fiscal_year;

\echo ''
\echo '7. AWARD-LEVEL CORE CHIP CLASSIFICATIONS'

SELECT
    source_program_code,
    inflow_subfamily,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS award_classifications
FROM reference.federal_inflow_award_classification
WHERE source_program_code = '93.767'
GROUP BY
    source_program_code,
    inflow_subfamily,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY valid_from_fiscal_year,methodology_version,
         inflow_subfamily;

\echo ''
\echo '8. EXISTING FISCAL BALANCE / LEDGER OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN (
    'pg_catalog','information_schema'
)
AND (
    c.relname ILIKE '%fiscal%balance%'
    OR c.relname ILIKE '%ledger%'
    OR c.relname ILIKE '%expenditure%'
    OR c.relname ILIKE '%inflow%'
)
AND c.relkind IN ('r','p','v','m')
ORDER BY n.nspname,c.relname;

\echo ''
\echo '9. SOURCE-YEAR CONSISTENCY GATE'

DO $gate$
DECLARE
    v_bad bigint;
BEGIN
    WITH expected AS (
        SELECT p.program,y.fiscal_year
        FROM (VALUES ('MEDICAID'),('CHIP')) p(program)
        CROSS JOIN generate_series(2018,2024) y(fiscal_year)
    ),
    observed AS (
        SELECT
            'MEDICAID'::text AS program,
            fiscal_year,
            federal_expenditure_amount::numeric AS dollars,
            amount_method,
            is_additive_to_fiscal_balance
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT
            'CHIP',
            fiscal_year,
            federal_expenditure_amount::numeric,
            amount_method,
            is_additive_to_fiscal_balance
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
    ),
    grouped AS (
        SELECT
            program,
            fiscal_year,
            COUNT(*) AS n,
            COUNT(*) FILTER (
                WHERE dollars IS NULL
                   OR dollars <= 0
                   OR amount_method IS DISTINCT FROM
                      'ACTUAL_EXPENDITURE'
                   OR is_additive_to_fiscal_balance IS DISTINCT FROM TRUE
            ) AS invalid_rows
        FROM observed
        GROUP BY program,fiscal_year
    )
    SELECT COUNT(*) INTO v_bad
    FROM expected e
    LEFT JOIN grouped g
      ON g.program=e.program
     AND g.fiscal_year=e.fiscal_year
    WHERE COALESCE(g.n,0) <> 1
       OR COALESCE(g.invalid_rows,0) <> 0;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % invalid CMS source-year controls',v_bad;
    END IF;

    RAISE NOTICE
        'ETL-218B SOURCE-YEAR CONSISTENCY PASS: 14 CONTROLS';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218B COMPLETE - READ ONLY'
