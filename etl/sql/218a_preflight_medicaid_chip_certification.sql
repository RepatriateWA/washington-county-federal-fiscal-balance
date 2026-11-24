
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218A - MEDICAID AND CHIP CERTIFICATION PREFLIGHT'
\echo 'FY2018-FY2024 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. REQUIRED OBJECT INVENTORY'

DO $gate$
DECLARE
    v_missing text;
BEGIN
    WITH required(schema_name, object_name) AS (
        VALUES
        ('reporting','v_washington_medicaid_expenditures'),
        ('reporting','v_washington_chip_expenditures'),
        ('reference','federal_inflow_source_policy'),
        ('reference','federal_inflow_program_classification'),
        ('reference','federal_inflow_program_policy_mapping'),
        ('reference','federal_inflow_award_classification')
    )
    SELECT string_agg(
        format('%I.%I',schema_name,object_name), ', '
    )
    INTO v_missing
    FROM required
    WHERE to_regclass(
        format('%I.%I',schema_name,object_name)
    ) IS NULL;

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION
            'BLOCK: required objects missing: %',v_missing;
    END IF;

    RAISE NOTICE 'ETL-218A REQUIRED OBJECTS PASS';
END
$gate$;

\echo ''
\echo '2. ACTUAL FEDERAL EXPENDITURE CONTROLS'

WITH source_rows AS (
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
SELECT
    program,
    fiscal_year,
    dollars,
    amount_method,
    is_additive_to_fiscal_balance
FROM source_rows
ORDER BY program,fiscal_year;

\echo ''
\echo '3. CHIP SOURCE PROVENANCE NOTES'

SELECT
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    measure_note
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '4. MEDICAID AND CHIP SOURCE SELECTION POLICIES'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE (
    UPPER(inflow_family) LIKE '%MEDICAID%'
    OR UPPER(inflow_subfamily) LIKE '%MEDICAID%'
    OR UPPER(inflow_family) LIKE '%CHIP%'
    OR UPPER(inflow_subfamily) LIKE '%CHIP%'
)
ORDER BY inflow_family,inflow_subfamily,
         valid_from_fiscal_year,methodology_version;

\echo ''
\echo '5. PROGRAM CLASSIFICATIONS WITH POSSIBLE OVERLAP'

SELECT
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE (
    UPPER(COALESCE(inflow_family,'')) LIKE '%MEDICAID%'
    OR UPPER(COALESCE(inflow_subfamily,'')) LIKE '%MEDICAID%'
    OR UPPER(COALESCE(inflow_family,'')) LIKE '%CHIP%'
    OR UPPER(COALESCE(inflow_subfamily,'')) LIKE '%CHIP%'
    OR UPPER(COALESCE(source_program_title,'')) LIKE '%CHILDREN%HEALTH%INSURANCE%'
)
ORDER BY source_program_code,valid_from_fiscal_year;

\echo ''
\echo '6. PROGRAM-TO-SOURCE-POLICY MAPPINGS'

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE (
    UPPER(p.inflow_family) LIKE '%MEDICAID%'
    OR UPPER(p.inflow_subfamily) LIKE '%MEDICAID%'
    OR UPPER(p.inflow_family) LIKE '%CHIP%'
    OR UPPER(p.inflow_subfamily) LIKE '%CHIP%'
)
ORDER BY m.source_program_code,
         m.valid_from_fiscal_year;

\echo ''
\echo '7. AWARD-LEVEL OVERLAP CLASSIFICATIONS'

SELECT
    source_program_code,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS classification_rows
FROM reference.federal_inflow_award_classification
WHERE (
    UPPER(inflow_family) LIKE '%MEDICAID%'
    OR UPPER(inflow_subfamily) LIKE '%MEDICAID%'
    OR UPPER(inflow_family) LIKE '%CHIP%'
    OR UPPER(inflow_subfamily) LIKE '%CHIP%'
)
GROUP BY
    source_program_code,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY inflow_family,source_program_code,
         methodology_version;

\echo ''
\echo '8. EXISTING LEDGER-RELATED OBJECT INVENTORY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'analysis','reporting','reference','cms','assistance'
)
AND (
    table_name ILIKE '%ledger%'
    OR table_name ILIKE '%certif%'
    OR table_name ILIKE '%medicaid%'
    OR table_name ILIKE '%chip%'
)
ORDER BY table_schema,table_name;

\echo ''
\echo '9. FAIL-CLOSED EXPENDITURE CONTROL GATE'

DO $gate$
DECLARE
    v_bad bigint;
    v_count bigint;
BEGIN
    WITH source_rows AS (
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
    expected AS (
        SELECT program,year_label
        FROM (VALUES ('MEDICAID'),('CHIP')) p(program)
        CROSS JOIN generate_series(2018,2024) y(year_label)
    ),
    actual AS (
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
        FROM source_rows
        GROUP BY program,fiscal_year
    )
    SELECT COUNT(*) INTO v_bad
    FROM expected e
    LEFT JOIN actual a
      ON a.program=e.program
     AND a.fiscal_year=e.year_label
    WHERE COALESCE(a.n,0) <> 1
       OR COALESCE(a.invalid_rows,0) <> 0;

    SELECT COUNT(*) INTO v_count
    FROM (
        SELECT fiscal_year
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT fiscal_year
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
    ) source_years;

    IF v_bad <> 0 OR v_count <> 14 THEN
        RAISE EXCEPTION
            'BLOCK: invalid source-year controls %, rows %',
            v_bad,v_count;
    END IF;

    RAISE NOTICE
        'ETL-218A EXPENDITURE CONTROL GATE PASS: 14 SOURCE-YEARS';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218A COMPLETE - READ ONLY'
