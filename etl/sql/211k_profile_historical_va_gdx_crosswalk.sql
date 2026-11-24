
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211K - HISTORICAL VA GDX CROSSWALK PROFILE'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- 1. Historical GDX category inventory
\echo ''
\echo '1. HISTORICAL GDX CATEGORY INVENTORY'

SELECT
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT e.county_id) AS distinct_counties,
    ROUND(SUM(e.expenditure_amount)::numeric, 2)
        AS washington_expenditure
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
GROUP BY
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY e.fiscal_year, c.category_code;

-- 2. GDX control/component reconciliation
\echo ''
\echo '2. GDX COMPONENT RECONCILIATION'

WITH totals AS (
    SELECT
        e.fiscal_year,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_rows,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_amount,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_amount
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
    GROUP BY e.fiscal_year
)
SELECT
    fiscal_year,
    control_rows,
    component_rows,
    ROUND(control_amount::numeric, 2) AS control_amount,
    ROUND(component_amount::numeric, 2) AS component_amount,
    ROUND(
        (component_amount - control_amount)::numeric, 2
    ) AS difference
FROM totals
ORDER BY fiscal_year;

-- 3. Historical VA program crosswalk
-- Explicit Class A candidates recovered from ETL-174B-5N-3.
-- Evidence classifications only; no policy changes.
\echo ''
\echo '3. HISTORICAL VA CLASS A CROSSWALK CANDIDATES'

WITH crosswalk(program_code, gdx_family) AS (
    VALUES
        ('64.109', 'COMPENSATION_PENSION'),
        ('64.110', 'COMPENSATION_PENSION'),
        ('64.104', 'COMPENSATION_PENSION'),
        ('64.105', 'COMPENSATION_PENSION'),
        ('64.028', 'EDUCATION_VRE'),
        ('64.117', 'EDUCATION_VRE'),
        ('64.124', 'EDUCATION_VRE'),
        ('64.032', 'EDUCATION_VRE'),
        ('64.120', 'EDUCATION_VRE'),
        ('64.041', 'MEDICAL_CARE'),
        ('64.045', 'MEDICAL_CARE'),
        ('64.012', 'MEDICAL_CARE'),
        ('64.040', 'MEDICAL_CARE'),
        ('64.048', 'MEDICAL_CARE'),
        ('64.047', 'MEDICAL_CARE'),
        ('64.013', 'MEDICAL_CARE'),
        ('64.050', 'MEDICAL_CARE'),
        ('64.039', 'MEDICAL_CARE'),
        ('64.049', 'MEDICAL_CARE'),
        ('64.042', 'MEDICAL_CARE'),
        ('64.044', 'MEDICAL_CARE'),
        ('64.011', 'MEDICAL_CARE'),
        ('64.046', 'MEDICAL_CARE'),
        ('64.043', 'MEDICAL_CARE'),
        ('64.005', 'CONSTRUCTION'),
        ('64.101', 'MEMORIAL_BENEFITS'),
        ('64.203', 'MEMORIAL_BENEFITS'),
        ('64.206', 'MEMORIAL_BENEFITS')
),
historical AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        COUNT(*) AS transactions,
        SUM(c.federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger c
    WHERE (
        c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018
    ) OR (
        c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019
    )
    GROUP BY
        c.action_date_fiscal_year,
        BTRIM(c.cfda_number)
)
SELECT
    h.fiscal_year,
    h.program_code,
    x.gdx_family,
    h.transactions,
    ROUND(h.obligations::numeric, 2) AS obligations
FROM historical h
JOIN crosswalk x
  ON x.program_code = h.program_code
ORDER BY
    h.fiscal_year,
    ABS(h.obligations) DESC,
    h.program_code;

-- 4. Current policy status of historical Class A candidates
\echo ''
\echo '4. CURRENT PROGRAM POLICY STATUS'

WITH crosswalk(program_code) AS (
    VALUES
        ('64.109'), ('64.110'), ('64.104'), ('64.105'),
        ('64.028'), ('64.117'), ('64.124'), ('64.032'),
        ('64.120'), ('64.041'), ('64.045'), ('64.012'),
        ('64.040'), ('64.048'), ('64.047'), ('64.013'),
        ('64.050'), ('64.039'), ('64.049'), ('64.042'),
        ('64.044'), ('64.011'), ('64.046'), ('64.043'),
        ('64.005'), ('64.101'), ('64.203'), ('64.206')
),
historical AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        COUNT(*) AS transactions,
        SUM(c.federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger c
    WHERE (
        c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018
    ) OR (
        c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019
    )
    GROUP BY
        c.action_date_fiscal_year,
        BTRIM(c.cfda_number)
)
SELECT
    h.fiscal_year,
    h.program_code,
    h.transactions,
    ROUND(h.obligations::numeric, 2) AS obligations,
    COUNT(p.federal_inflow_program_policy_mapping_id)
        AS matching_policy_rows,
    STRING_AGG(
        DISTINCT p.resolved_accounting_disposition,
        ', '
    ) AS program_dispositions,
    STRING_AGG(
        DISTINCT p.methodology_version,
        ', '
    ) AS methodology_versions
FROM historical h
JOIN crosswalk x
  ON x.program_code = h.program_code
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = h.program_code
 AND h.fiscal_year BETWEEN
     COALESCE(p.valid_from_fiscal_year, -9999)
     AND COALESCE(p.valid_through_fiscal_year, 9999)
GROUP BY
    h.fiscal_year,
    h.program_code,
    h.transactions,
    h.obligations
ORDER BY
    h.fiscal_year,
    ABS(h.obligations) DESC,
    h.program_code;

ROLLBACK;

\echo ''
\echo 'ETL-211K COMPLETE - NO DATABASE WRITES'
