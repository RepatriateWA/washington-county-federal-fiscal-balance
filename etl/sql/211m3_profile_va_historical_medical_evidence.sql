
\set ON_ERROR_STOP on
\pset pager off

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M3 - HISTORICAL VA MEDICAL CARE EVIDENCE PROFILE'
\echo '=========================================================================='
\echo 'Fiscal years: 2018-2019'
\echo 'Mode: READ ONLY - NO DATABASE WRITES'
\echo 'Purpose: Validate historical VA Medical Care overlap evidence'
\echo '=========================================================================='

BEGIN TRANSACTION READ ONLY;


-- ==========================================================================
-- SECTION 1 - HISTORICAL PROGRAM IDENTITIES AND TRANSACTION AMOUNTS
-- ==========================================================================
--
-- Evidence basis:
--   ETL-174B-5N-3 established 15 direct GDX Medical Care overlaps.
--
--   AL 64.029 (Purchase Care Program) was not among those 15.
--   It is retained here as a separate review candidate.
--
-- Source population:
--   FY2018 = USAspending assistance load batch 20
--   FY2019 = USAspending assistance load batch 21
--
-- No accounting disposition is changed by this analysis.
-- ==========================================================================

\echo ''
\echo '1. HISTORICAL PROGRAM IDENTITIES AND TRANSACTION AMOUNTS'

WITH evidence (
    program_code,
    evidence_class,
    gdx_family
) AS (
    VALUES
        ('64.011', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.012', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.013', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.039', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.040', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.041', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.042', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.043', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.044', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.045', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.046', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.047', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.048', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.049', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.050', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE'),
        ('64.029', 'SEPARATE_REVIEW', 'NOT_ESTABLISHED')
)
SELECT
    c.action_date_fiscal_year AS fiscal_year,
    e.program_code,
    MAX(c.cfda_title) AS reported_program_title,
    e.evidence_class,
    e.gdx_family,
    COUNT(c.assistance_transaction_id) AS transactions,
    ROUND(
        COALESCE(SUM(c.federal_action_obligation), 0)::numeric,
        2
    ) AS net_obligations
FROM evidence e
LEFT JOIN analysis.v_certified_assistance_ledger c
    ON BTRIM(c.cfda_number) = e.program_code
   AND (
        (
            c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018
        )
        OR
        (
            c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019
        )
   )
GROUP BY
    c.action_date_fiscal_year,
    e.program_code,
    e.evidence_class,
    e.gdx_family
ORDER BY
    fiscal_year,
    e.program_code;


-- ==========================================================================
-- SECTION 2 - DIRECT MEDICAL CARE VS SEPARATE REVIEW
-- ==========================================================================
--
-- Aggregate the original 15 direct-overlap programs independently
-- from AL 64.029.
--
-- These are USAspending federal action obligations, not VA GDX
-- expenditures. Numerical equality is neither expected nor required.
-- ==========================================================================

\echo ''
\echo '2. DIRECT MEDICAL CARE VS SEPARATE REVIEW'

WITH evidence (
    program_code,
    evidence_class
) AS (
    VALUES
        ('64.011', 'A_DIRECT_GDX_OVERLAP'),
        ('64.012', 'A_DIRECT_GDX_OVERLAP'),
        ('64.013', 'A_DIRECT_GDX_OVERLAP'),
        ('64.039', 'A_DIRECT_GDX_OVERLAP'),
        ('64.040', 'A_DIRECT_GDX_OVERLAP'),
        ('64.041', 'A_DIRECT_GDX_OVERLAP'),
        ('64.042', 'A_DIRECT_GDX_OVERLAP'),
        ('64.043', 'A_DIRECT_GDX_OVERLAP'),
        ('64.044', 'A_DIRECT_GDX_OVERLAP'),
        ('64.045', 'A_DIRECT_GDX_OVERLAP'),
        ('64.046', 'A_DIRECT_GDX_OVERLAP'),
        ('64.047', 'A_DIRECT_GDX_OVERLAP'),
        ('64.048', 'A_DIRECT_GDX_OVERLAP'),
        ('64.049', 'A_DIRECT_GDX_OVERLAP'),
        ('64.050', 'A_DIRECT_GDX_OVERLAP'),
        ('64.029', 'SEPARATE_REVIEW')
)
SELECT
    c.action_date_fiscal_year AS fiscal_year,
    e.evidence_class,
    COUNT(*) AS transactions,
    COUNT(DISTINCT e.program_code) AS programs,
    ROUND(
        SUM(c.federal_action_obligation)::numeric,
        2
    ) AS net_obligations,
    ROUND(
        SUM(ABS(c.federal_action_obligation))::numeric,
        2
    ) AS gross_absolute_obligations
FROM analysis.v_certified_assistance_ledger c
JOIN evidence e
    ON e.program_code = BTRIM(c.cfda_number)
WHERE
    (
        c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018
    )
    OR
    (
        c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019
    )
GROUP BY
    c.action_date_fiscal_year,
    e.evidence_class
ORDER BY
    fiscal_year,
    e.evidence_class;


-- ==========================================================================
-- SECTION 3 - GDX TABLE STRUCTURE
-- ==========================================================================
--
-- Report the PostgreSQL column definitions for the two source tables.
-- This documents the schema used for subsequent reconciliation.
-- ==========================================================================

\echo ''
\echo '3. GDX TABLE STRUCTURE'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'va'
  AND table_name IN (
      'gdx_expenditure_category',
      'gdx_county_expenditure'
  )
ORDER BY
    table_name,
    ordinal_position;


-- ==========================================================================
-- SECTION 4 - GDX EXPENDITURE CATEGORY DEFINITIONS
-- ==========================================================================
--
-- Show canonical category codes, names, aggregation roles,
-- and fiscal-year applicability.
--
-- Medical Care is expected to be a COMPONENT, not a CONTROL_TOTAL.
-- ==========================================================================

\echo ''
\echo '4. GDX EXPENDITURE CATEGORY DEFINITIONS'

SELECT
    k.gdx_category_id,
    k.category_code,
    k.category_name,
    k.aggregation_role,
    k.first_fiscal_year,
    k.last_fiscal_year,
    k.description
FROM va.gdx_expenditure_category k
ORDER BY
    k.category_code;


-- ==========================================================================
-- SECTION 5 - FY2018-FY2019 GDX MEDICAL CARE EXPENDITURES
-- ==========================================================================
--
-- Select the canonical MEDICAL_CARE category directly.
--
-- Report:
--   Fiscal year
--   GDX category
--   Number of expenditure rows
--   Distinct Washington counties
--   Total expenditure dollars
--
-- This section deliberately does not combine GDX control totals
-- with component expenditure records.
-- ==========================================================================

\echo ''
\echo '5. FY2018-FY2019 GDX MEDICAL CARE EXPENDITURES'

SELECT
    e.fiscal_year,
    k.category_code,
    k.category_name,
    k.aggregation_role,
    COUNT(*) AS expenditure_rows,
    COUNT(DISTINCT e.county_id) AS counties,
    ROUND(
        SUM(e.expenditure_amount)::numeric,
        2
    ) AS expenditure_dollars
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category k
    ON k.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
  AND k.category_code = 'MEDICAL_CARE'
  AND k.aggregation_role = 'COMPONENT'
GROUP BY
    e.fiscal_year,
    k.category_code,
    k.category_name,
    k.aggregation_role
ORDER BY
    e.fiscal_year,
    k.category_code;


-- ==========================================================================
-- SECTION 6 - LATER-YEAR POLICY PRECEDENT: AL 64.011 VS AL 64.029
-- ==========================================================================
--
-- Investigate the difference between:
--
--   AL 64.011 - Veterans Dental Care
--     Included in original Class A Medical Care evidence.
--
--   AL 64.029 - Purchase Care Program
--     Not included in original Class A Medical Care evidence.
--
-- Examine policy mappings without extending their validity dates.
-- ==========================================================================

\echo ''
\echo '6. LATER-YEAR POLICY PRECEDENT: AL 64.011 VS AL 64.029'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.inflow_subfamily
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
    ON s.federal_inflow_source_policy_id =
       m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN ('64.011', '64.029')
ORDER BY
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.methodology_version;


-- ==========================================================================
-- END OF READ-ONLY ANALYSIS
-- ==========================================================================

ROLLBACK;

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M3 COMPLETE - NO DATABASE WRITES'
\echo '=========================================================================='
