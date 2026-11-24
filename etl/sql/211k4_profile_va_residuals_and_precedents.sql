
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211K4 - VA HISTORICAL RESIDUALS AND POLICY PRECEDENTS'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. BENEFIT-FAMILY RESIDUALS
-- ============================================================

\echo ''
\echo '1. BENEFIT FAMILY RESIDUALS'

WITH crosswalk(program_code, family) AS (
    VALUES
    ('64.109','COMPENSATION_PENSION'),
    ('64.110','COMPENSATION_PENSION'),
    ('64.104','COMPENSATION_PENSION'),
    ('64.105','COMPENSATION_PENSION'),
    ('64.028','EDUCATION_VRE'),
    ('64.117','EDUCATION_VRE'),
    ('64.124','EDUCATION_VRE'),
    ('64.032','EDUCATION_VRE'),
    ('64.120','EDUCATION_VRE')
),
assistance AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        x.family,
        COUNT(*) AS transactions,
        SUM(c.federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger c
    JOIN crosswalk x
      ON x.program_code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
    GROUP BY c.action_date_fiscal_year, x.family
),
gdx AS (
    SELECT
        e.fiscal_year,
        k.category_code AS family,
        SUM(e.expenditure_amount) AS expenditures
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category k
      ON k.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
      AND k.category_code IN (
          'COMPENSATION_PENSION', 'EDUCATION_VRE'
      )
    GROUP BY e.fiscal_year, k.category_code
)
SELECT
    g.fiscal_year,
    g.family,
    a.transactions,
    ROUND(a.obligations::numeric, 2) AS obligations,
    ROUND(g.expenditures::numeric, 2) AS expenditures,
    ROUND(
        (g.expenditures - a.obligations)::numeric, 2
    ) AS gdx_minus_obligations
FROM gdx g
JOIN assistance a
  ON a.fiscal_year = g.fiscal_year
 AND a.family = g.family
ORDER BY g.fiscal_year, g.family;

-- ============================================================
-- 2. BURIAL ALLOWANCE / COMPENSATION RESIDUAL COMPARISON
-- ============================================================

\echo ''
\echo '2. BURIAL ALLOWANCE RESIDUAL COMPARISON'

WITH assistance AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        SUM(c.federal_action_obligation) FILTER (
            WHERE BTRIM(c.cfda_number) IN (
                '64.109', '64.110', '64.104', '64.105'
            )
        ) AS compensation_obligations,
        SUM(c.federal_action_obligation) FILTER (
            WHERE BTRIM(c.cfda_number) = '64.101'
        ) AS burial_obligations,
        COUNT(*) FILTER (
            WHERE BTRIM(c.cfda_number) = '64.101'
        ) AS burial_transactions
    FROM analysis.v_certified_assistance_ledger c
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
    GROUP BY c.action_date_fiscal_year
),
gdx AS (
    SELECT
        e.fiscal_year,
        SUM(e.expenditure_amount) AS expenditures
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category k
      ON k.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
      AND k.category_code = 'COMPENSATION_PENSION'
    GROUP BY e.fiscal_year
)
SELECT
    a.fiscal_year,
    a.burial_transactions,
    ROUND(a.burial_obligations::numeric, 2)
        AS burial_obligations,
    ROUND(
        (g.expenditures - a.compensation_obligations)::numeric,
        2
    ) AS compensation_residual,
    ROUND(
        (
            g.expenditures
            - a.compensation_obligations
            - a.burial_obligations
        )::numeric,
        2
    ) AS residual_after_burial
FROM assistance a
JOIN gdx g ON g.fiscal_year = a.fiscal_year
ORDER BY a.fiscal_year;

-- ============================================================
-- 3. FY2020-FY2024 PROGRAM POLICY PRECEDENT
-- ============================================================

\echo ''
\echo '3. LATER-YEAR EFFECTIVE PROGRAM POLICY PRECEDENTS'

WITH programs(program_code, family) AS (
    VALUES
    ('64.109','COMPENSATION_PENSION'),
    ('64.110','COMPENSATION_PENSION'),
    ('64.104','COMPENSATION_PENSION'),
    ('64.105','COMPENSATION_PENSION'),
    ('64.028','EDUCATION_VRE'),
    ('64.117','EDUCATION_VRE'),
    ('64.124','EDUCATION_VRE'),
    ('64.032','EDUCATION_VRE'),
    ('64.120','EDUCATION_VRE'),
    ('64.101','MEMORIAL_BENEFITS')
),
years AS (
    SELECT generate_series(2020, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    p.family,
    p.program_code,
    COUNT(m.federal_inflow_program_policy_mapping_id)
        AS effective_mapping_rows,
    STRING_AGG(
        DISTINCT m.resolved_accounting_disposition,
        ', '
    ) AS dispositions,
    STRING_AGG(
        DISTINCT m.methodology_version,
        ', '
    ) AS methodology_versions,
    STRING_AGG(
        DISTINCT s.preferred_source,
        ', '
    ) AS preferred_sources
FROM years y
CROSS JOIN programs p
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = p.program_code
 AND y.fiscal_year BETWEEN
     COALESCE(m.valid_from_fiscal_year, -9999)
     AND COALESCE(m.valid_through_fiscal_year, 9999)
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
GROUP BY y.fiscal_year, p.family, p.program_code
ORDER BY p.family, p.program_code, y.fiscal_year;

-- ============================================================
-- 4. HISTORICAL CLASSIFICATION COVERAGE
-- ============================================================

\echo ''
\echo '4. FY2018-FY2019 PROGRAM CLASSIFICATION COVERAGE'

WITH programs(program_code, family) AS (
    VALUES
    ('64.109','COMPENSATION_PENSION'),
    ('64.110','COMPENSATION_PENSION'),
    ('64.104','COMPENSATION_PENSION'),
    ('64.105','COMPENSATION_PENSION'),
    ('64.028','EDUCATION_VRE'),
    ('64.117','EDUCATION_VRE'),
    ('64.124','EDUCATION_VRE'),
    ('64.032','EDUCATION_VRE'),
    ('64.120','EDUCATION_VRE'),
    ('64.101','MEMORIAL_BENEFITS')
),
years AS (
    SELECT generate_series(2018, 2019) AS fiscal_year
)
SELECT
    y.fiscal_year,
    p.family,
    p.program_code,
    COUNT(c.federal_inflow_program_classification_id)
        AS effective_classification_rows,
    STRING_AGG(
        DISTINCT c.overlap_risk,
        ', '
    ) AS overlap_risks,
    STRING_AGG(
        DISTINCT c.methodology_version,
        ', '
    ) AS methodology_versions
FROM years y
CROSS JOIN programs p
LEFT JOIN reference.federal_inflow_program_classification c
  ON c.source_system = 'USASPENDING_ASSISTANCE'
 AND c.source_program_code = p.program_code
 AND y.fiscal_year BETWEEN
     COALESCE(c.valid_from_fiscal_year, -9999)
     AND COALESCE(c.valid_through_fiscal_year, 9999)
GROUP BY y.fiscal_year, p.family, p.program_code
ORDER BY p.family, p.program_code, y.fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-211K4 COMPLETE - NO DATABASE WRITES'
