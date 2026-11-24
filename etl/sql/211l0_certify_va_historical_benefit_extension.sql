
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211L0 - HISTORICAL VA BENEFIT EXTENSION CERTIFICATION'
\echo 'FY2018-FY2019 | READ ONLY | NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. HISTORICAL PROGRAM-YEAR CONTROLS
-- ============================================================

\echo ''
\echo '1. HISTORICAL TARGET POPULATION'

WITH targets(program_code, family) AS (
    VALUES
    ('64.104','COMPENSATION_PENSION'),
    ('64.105','COMPENSATION_PENSION'),
    ('64.110','COMPENSATION_PENSION'),
    ('64.028','EDUCATION_VRE'),
    ('64.032','EDUCATION_VRE'),
    ('64.117','EDUCATION_VRE'),
    ('64.120','EDUCATION_VRE'),
    ('64.124','EDUCATION_VRE')
)
SELECT
    c.action_date_fiscal_year AS fiscal_year,
    t.family,
    t.program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger c
JOIN targets t
  ON t.program_code = BTRIM(c.cfda_number)
WHERE
    (c.load_batch_id = 20
     AND c.action_date_fiscal_year = 2018)
    OR
    (c.load_batch_id = 21
     AND c.action_date_fiscal_year = 2019)
GROUP BY
    c.action_date_fiscal_year,
    t.family,
    t.program_code
ORDER BY
    c.action_date_fiscal_year,
    t.family,
    t.program_code;

-- ============================================================
-- 2. HISTORICAL POLICY COLLISION INVENTORY
-- ============================================================

\echo ''
\echo '2. HISTORICAL POLICY AND CLASSIFICATION COLLISIONS'

WITH targets(program_code) AS (
    VALUES
    ('64.104'),('64.105'),('64.110'),
    ('64.028'),('64.032'),('64.117'),
    ('64.120'),('64.124')
)
SELECT
    t.program_code,
    (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = t.program_code
          AND COALESCE(m.valid_from_fiscal_year, -9999)
              <= 2019
          AND COALESCE(m.valid_through_fiscal_year, 9999)
              >= 2018
    ) AS overlapping_program_mappings,
    (
        SELECT COUNT(*)
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = t.program_code
          AND COALESCE(a.valid_from_fiscal_year, -9999)
              <= 2019
          AND COALESCE(a.valid_through_fiscal_year, 9999)
              >= 2018
    ) AS overlapping_award_classifications,
    (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_classification c
        WHERE c.source_system = 'USASPENDING_ASSISTANCE'
          AND c.source_program_code = t.program_code
          AND COALESCE(c.valid_from_fiscal_year, -9999)
              <= 2019
          AND COALESCE(c.valid_through_fiscal_year, 9999)
              >= 2018
    ) AS overlapping_program_classifications
FROM targets t
ORDER BY t.program_code;

-- ============================================================
-- 3. LATER-YEAR SOURCE POLICY PRECEDENT
-- ============================================================

\echo ''
\echo '3. FY2020-FY2024 SOURCE POLICY PRECEDENT'

WITH targets(program_code) AS (
    VALUES
    ('64.104'),('64.105'),('64.110'),
    ('64.028'),('64.032'),('64.117'),
    ('64.120'),('64.124')
),
years AS (
    SELECT generate_series(2020, 2024) AS fiscal_year
)
SELECT
    t.program_code,
    COUNT(*) AS expected_program_years,
    COUNT(m.federal_inflow_program_policy_mapping_id)
        AS matching_policy_rows,
    COUNT(*) FILTER (
        WHERE m.resolved_accounting_disposition =
                  'EXCLUDE_DUPLICATE'
          AND s.preferred_source = 'VA_GDX'
          AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
          AND m.methodology_version = 'ANALYSIS-174B-5N-v1'
    ) AS correct_precedent_rows,
    COUNT(*) FILTER (
        WHERE m.federal_inflow_program_policy_mapping_id IS NULL
           OR m.resolved_accounting_disposition IS DISTINCT FROM
              'EXCLUDE_DUPLICATE'
           OR s.preferred_source IS DISTINCT FROM 'VA_GDX'
           OR s.ledger_treatment IS DISTINCT FROM
              'EXCLUDE_DUPLICATE'
           OR m.methodology_version IS DISTINCT FROM
              'ANALYSIS-174B-5N-v1'
    ) AS missing_or_incorrect_rows
FROM targets t
CROSS JOIN years y
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = t.program_code
 AND y.fiscal_year BETWEEN
     COALESCE(m.valid_from_fiscal_year, -9999)
     AND COALESCE(m.valid_through_fiscal_year, 9999)
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
GROUP BY t.program_code
ORDER BY t.program_code;

-- ============================================================
-- 4. INDEPENDENT HISTORICAL GDX CONTROLS
-- ============================================================

\echo ''
\echo '4. HISTORICAL GDX CONTROL RECONCILIATION'

SELECT
    e.fiscal_year,
    COUNT(*) FILTER (
        WHERE k.aggregation_role = 'CONTROL_TOTAL'
    ) AS control_rows,
    COUNT(*) FILTER (
        WHERE k.aggregation_role = 'COMPONENT'
    ) AS component_rows,
    ROUND(
        COALESCE(SUM(e.expenditure_amount) FILTER (
            WHERE k.aggregation_role = 'CONTROL_TOTAL'
        ), 0)::numeric, 2
    ) AS control_dollars,
    ROUND(
        COALESCE(SUM(e.expenditure_amount) FILTER (
            WHERE k.aggregation_role = 'COMPONENT'
        ), 0)::numeric, 2
    ) AS component_dollars,
    ROUND(
        (
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE k.aggregation_role = 'COMPONENT'
            ), 0)
            -
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE k.aggregation_role = 'CONTROL_TOTAL'
            ), 0)
        )::numeric, 2
    ) AS difference
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category k
  ON k.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
GROUP BY e.fiscal_year
ORDER BY e.fiscal_year;

-- ============================================================
-- 5. CERTIFICATION GATE
-- ============================================================

\echo ''
\echo '5. CERTIFICATION GATE'

WITH targets(program_code) AS (
    VALUES
    ('64.104'),('64.105'),('64.110'),
    ('64.028'),('64.032'),('64.117'),
    ('64.120'),('64.124')
),
historical AS (
    SELECT
        COUNT(*) AS transactions,
        COALESCE(SUM(c.federal_action_obligation), 0)
            AS obligations,
        COUNT(DISTINCT (
            c.action_date_fiscal_year,
            BTRIM(c.cfda_number)
        )) AS program_years
    FROM analysis.v_certified_assistance_ledger c
    JOIN targets t
      ON t.program_code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
collisions AS (
    SELECT
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping m
            JOIN targets t
              ON t.program_code = m.source_program_code
            WHERE m.source_system = 'USASPENDING_ASSISTANCE'
              AND COALESCE(m.valid_from_fiscal_year, -9999)
                  <= 2019
              AND COALESCE(m.valid_through_fiscal_year, 9999)
                  >= 2018
        )
        +
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_award_classification a
            JOIN targets t
              ON t.program_code = a.source_program_code
            WHERE a.source_system = 'USASPENDING_ASSISTANCE'
              AND COALESCE(a.valid_from_fiscal_year, -9999)
                  <= 2019
              AND COALESCE(a.valid_through_fiscal_year, 9999)
                  >= 2018
        )
        +
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_classification c
            JOIN targets t
              ON t.program_code = c.source_program_code
            WHERE c.source_system = 'USASPENDING_ASSISTANCE'
              AND COALESCE(c.valid_from_fiscal_year, -9999)
                  <= 2019
              AND COALESCE(c.valid_through_fiscal_year, 9999)
                  >= 2018
        ) AS collision_rows
),
precedent AS (
    SELECT
        COUNT(*) AS valid_program_years
    FROM targets t
    CROSS JOIN generate_series(2020, 2024) y(fiscal_year)
    WHERE (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping m
        JOIN reference.federal_inflow_source_policy s
          ON s.federal_inflow_source_policy_id =
             m.federal_inflow_source_policy_id
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = t.program_code
          AND y.fiscal_year BETWEEN
              COALESCE(m.valid_from_fiscal_year, -9999)
              AND COALESCE(m.valid_through_fiscal_year, 9999)
          AND m.resolved_accounting_disposition =
              'EXCLUDE_DUPLICATE'
          AND m.methodology_version = 'ANALYSIS-174B-5N-v1'
          AND s.preferred_source = 'VA_GDX'
          AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
    ) = 1
    AND (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = t.program_code
          AND y.fiscal_year BETWEEN
              COALESCE(m.valid_from_fiscal_year, -9999)
              AND COALESCE(m.valid_through_fiscal_year, 9999)
    ) = 1
),
gdx AS (
    SELECT
        COUNT(*) AS valid_years
    FROM (
        SELECT
            e.fiscal_year,
            COUNT(*) FILTER (
                WHERE k.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows,
            COUNT(*) FILTER (
                WHERE k.aggregation_role = 'COMPONENT'
            ) AS component_rows,
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE k.aggregation_role = 'COMPONENT'
            ), 0)
            -
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE k.aggregation_role = 'CONTROL_TOTAL'
            ), 0) AS difference
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category k
          ON k.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year IN (2018, 2019)
        GROUP BY e.fiscal_year
    ) q
    WHERE q.control_rows = 39
      AND q.component_rows = 273
      AND ROUND(q.difference, 2) = 0
)
SELECT
    h.transactions,
    ROUND(h.obligations::numeric, 2) AS obligations,
    h.program_years,
    c.collision_rows,
    p.valid_program_years AS valid_precedent_program_years,
    g.valid_years AS valid_gdx_years,
    CASE
        WHEN h.program_years = 16
         AND ROUND(h.obligations, 2) = 1274305391.00
         AND c.collision_rows = 0
         AND p.valid_program_years = 40
         AND g.valid_years = 2
        THEN 'PASS'
        ELSE 'FAIL'
    END AS certification_result
FROM historical h
CROSS JOIN collisions c
CROSS JOIN precedent p
CROSS JOIN gdx g;

ROLLBACK;

\echo ''
\echo 'ETL-211L0 COMPLETE - NO DATABASE WRITES'
