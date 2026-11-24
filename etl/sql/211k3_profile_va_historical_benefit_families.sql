
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211K3 - HISTORICAL VA BENEFIT FAMILY EVIDENCE'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ------------------------------------------------------------
-- 1. GDX category provenance and statewide expenditure totals
-- ------------------------------------------------------------

\echo ''
\echo '1. HISTORICAL GDX CATEGORY PROVENANCE'

SELECT
    e.fiscal_year,
    c.category_code,
    e.schema_regime,
    e.source_category_name,
    e.expenditure_class,
    COUNT(*) AS county_rows,
    ROUND(SUM(e.expenditure_amount)::numeric, 2)
        AS gdx_expenditures
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
  AND c.category_code IN (
      'COMPENSATION_PENSION',
      'EDUCATION_VRE'
  )
GROUP BY
    e.fiscal_year,
    c.category_code,
    e.schema_regime,
    e.source_category_name,
    e.expenditure_class
ORDER BY
    e.fiscal_year,
    c.category_code,
    e.source_category_name;

-- ------------------------------------------------------------
-- 2. Program-level historical obligation comparison
-- ------------------------------------------------------------

\echo ''
\echo '2. PROGRAM OBLIGATIONS VS GDX FAMILY EXPENDITURES'

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
        ('64.120', 'EDUCATION_VRE')
),
historical AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        MAX(c.cfda_title) AS program_title,
        COUNT(*) AS transactions,
        SUM(c.federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger c
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
    GROUP BY
        c.action_date_fiscal_year,
        BTRIM(c.cfda_number)
),
gdx AS (
    SELECT
        e.fiscal_year,
        c.category_code,
        SUM(e.expenditure_amount) AS expenditures
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
      AND c.category_code IN (
          'COMPENSATION_PENSION',
          'EDUCATION_VRE'
      )
    GROUP BY
        e.fiscal_year,
        c.category_code
)
SELECT
    h.fiscal_year,
    x.gdx_family,
    h.program_code,
    h.program_title,
    h.transactions,
    ROUND(h.obligations::numeric, 2) AS obligations,
    ROUND(g.expenditures::numeric, 2)
        AS family_gdx_expenditures,
    ROUND(
        100.0 * h.obligations
        / NULLIF(g.expenditures, 0),
        2
    ) AS obligation_to_gdx_percent
FROM historical h
JOIN crosswalk x
  ON x.program_code = h.program_code
LEFT JOIN gdx g
  ON g.fiscal_year = h.fiscal_year
 AND g.category_code = x.gdx_family
ORDER BY
    h.fiscal_year,
    x.gdx_family,
    h.program_code;

-- ------------------------------------------------------------
-- 3. Family-level annual comparison
-- ------------------------------------------------------------

\echo ''
\echo '3. FAMILY-LEVEL ANNUAL COMPARISON'

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
        ('64.120', 'EDUCATION_VRE')
),
assistance AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        x.gdx_family,
        SUM(c.federal_action_obligation) AS obligations,
        COUNT(*) AS transactions,
        COUNT(DISTINCT x.program_code) AS programs
    FROM analysis.v_certified_assistance_ledger c
    JOIN crosswalk x
      ON x.program_code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
    GROUP BY
        c.action_date_fiscal_year,
        x.gdx_family
),
gdx AS (
    SELECT
        e.fiscal_year,
        c.category_code AS gdx_family,
        SUM(e.expenditure_amount) AS expenditures
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year IN (2018, 2019)
      AND c.category_code IN (
          'COMPENSATION_PENSION',
          'EDUCATION_VRE'
      )
    GROUP BY
        e.fiscal_year,
        c.category_code
)
SELECT
    a.fiscal_year,
    a.gdx_family,
    a.programs,
    a.transactions,
    ROUND(a.obligations::numeric, 2)
        AS assistance_obligations,
    ROUND(g.expenditures::numeric, 2)
        AS gdx_expenditures,
    ROUND(
        (a.obligations - g.expenditures)::numeric, 2
    ) AS obligation_minus_expenditure,
    ROUND(
        100.0 * a.obligations
        / NULLIF(g.expenditures, 0),
        2
    ) AS obligation_to_gdx_percent
FROM assistance a
LEFT JOIN gdx g
  ON g.fiscal_year = a.fiscal_year
 AND g.gdx_family = a.gdx_family
ORDER BY
    a.fiscal_year,
    a.gdx_family;

-- ------------------------------------------------------------
-- 4. Existing classification evidence and effective dates
-- ------------------------------------------------------------

\echo ''
\echo '4. EXISTING PROGRAM CLASSIFICATION EVIDENCE'

SELECT
    source_program_code,
    source_program_title,
    overlap_risk,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN (
      '64.109', '64.110', '64.104', '64.105',
      '64.028', '64.117', '64.124',
      '64.032', '64.120'
  )
ORDER BY
    source_program_code,
    valid_from_fiscal_year,
    methodology_version;

ROLLBACK;

\echo ''
\echo 'ETL-211K3 COMPLETE - NO DATABASE WRITES'
