-- ============================================================
-- WCFFBP ETL-209V
-- INDEPENDENT POST-MIGRATION VA POLICY VALIDATION
-- FY2018-FY2019 | AL 64.109
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-209V - HISTORICAL VA POLICY VALIDATION'
\echo '============================================================'

-- 1. Validate the three new records and their linkage.

SELECT
    'SOURCE_POLICY' AS policy_layer,
    COUNT(*) AS records
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-209U-v1'

UNION ALL

SELECT
    'PROGRAM_CLASSIFICATION',
    COUNT(*)
FROM reference.federal_inflow_program_classification
WHERE methodology_version = 'ANALYSIS-209U-v1'

UNION ALL

SELECT
    'PROGRAM_POLICY_MAPPING',
    COUNT(*)
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-209U-v1';


-- 2. Verify historical transaction resolution.

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        c.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger c
    WHERE BTRIM(c.cfda_number) = '64.109'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
),
resolved AS (
    SELECT
        h.assistance_transaction_id,
        h.fiscal_year,
        h.obligation,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS matching_policies,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            FILTER (
                WHERE m.resolved_accounting_disposition =
                    'EXCLUDE_DUPLICATE'
            ) AS exclusion_matches,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            FILTER (
                WHERE m.resolved_accounting_disposition =
                    'INCLUDE_ADDITIVE'
            ) AS additive_matches
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = '64.109'
     AND h.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, -9999)
         AND COALESCE(m.valid_through_fiscal_year, 9999)
    GROUP BY
        h.assistance_transaction_id,
        h.fiscal_year,
        h.obligation
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE matching_policies <> 1
    ) AS nonunique_resolutions,
    COUNT(*) FILTER (
        WHERE exclusion_matches <> 1
    ) AS incorrect_exclusions,
    COUNT(*) FILTER (
        WHERE additive_matches <> 0
    ) AS additive_conflicts
FROM resolved
GROUP BY fiscal_year
ORDER BY fiscal_year;


-- 3. Verify mapping-to-source-policy linkage.

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.federal_inflow_source_policy_id,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.preferred_source,
    p.accounting_measure,
    p.ledger_treatment,
    p.methodology_version AS source_methodology
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-209U-v1';


-- 4. Detect any overlapping AL 64.109 mapping windows.

SELECT
    a.federal_inflow_program_policy_mapping_id AS mapping_a,
    b.federal_inflow_program_policy_mapping_id AS mapping_b,
    a.methodology_version AS methodology_a,
    b.methodology_version AS methodology_b
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
  AND a.source_program_code = '64.109';


-- 5. Verify original VA policy preservation.

SELECT
    p.federal_inflow_source_policy_id,
    p.methodology_version,
    p.preferred_source,
    p.ledger_treatment,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year
FROM reference.federal_inflow_source_policy p
WHERE p.federal_inflow_source_policy_id IN (2, 16)
ORDER BY p.federal_inflow_source_policy_id;


-- 6. Check historical program-classification coverage.

WITH years AS (
    SELECT generate_series(2018, 2025) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(c.federal_inflow_program_classification_id)
        AS matching_classifications,
    STRING_AGG(
        c.methodology_version,
        ', ' ORDER BY c.methodology_version
    ) AS methodologies
FROM years y
LEFT JOIN reference.federal_inflow_program_classification c
  ON c.source_system = 'USASPENDING_ASSISTANCE'
 AND c.source_program_code = '64.109'
 AND y.fiscal_year BETWEEN
     COALESCE(c.valid_from_fiscal_year, -9999)
     AND COALESCE(c.valid_through_fiscal_year, 9999)
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;


-- 7. Check historical award-level conflicts.

SELECT
    COUNT(*) AS overlapping_award_classifications
FROM reference.federal_inflow_award_classification a
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND a.source_program_code = '64.109'
  AND COALESCE(a.valid_from_fiscal_year, -9999) <= 2019
  AND COALESCE(a.valid_through_fiscal_year, 9999) >= 2018;


-- 8. Reconcile the historical GDX expenditure controls.

SELECT
    e.fiscal_year,
    COUNT(*) FILTER (
        WHERE c.aggregation_role = 'CONTROL_TOTAL'
    ) AS control_rows,
    COUNT(*) FILTER (
        WHERE c.aggregation_role = 'COMPONENT'
    ) AS component_rows,
    ROUND(
        COALESCE(SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ), 0)::numeric, 2
    ) AS gdx_control_total,
    ROUND(
        COALESCE(SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ), 0)::numeric, 2
    ) AS gdx_component_total,
    ROUND((
        COALESCE(SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ), 0)
        -
        COALESCE(SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ), 0)
    )::numeric, 2) AS difference
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
GROUP BY e.fiscal_year
ORDER BY e.fiscal_year;


-- 9. Automated pass/fail controls.

DO $$
DECLARE
    v_bad bigint;
    v_count bigint;
    v_amount numeric;
BEGIN
    SELECT COUNT(*)
    INTO v_bad
    FROM (
        SELECT
            'source' AS layer,
            COUNT(*) AS n
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version = 'ANALYSIS-209U-v1'

        UNION ALL

        SELECT
            'classification',
            COUNT(*)
        FROM reference.federal_inflow_program_classification
        WHERE methodology_version = 'ANALYSIS-209U-v1'

        UNION ALL

        SELECT
            'mapping',
            COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-209U-v1'
    ) x
    WHERE n <> 1;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209V policy record-count failure';
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '64.109'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    IF v_count <> 929
       OR ROUND(v_amount, 2) <> 4384945713.00 THEN
        RAISE EXCEPTION
            'ETL-209V historical source-control failure';
    END IF;

    SELECT COUNT(*)
    INTO v_bad
    FROM (
        SELECT
            h.action_date_fiscal_year AS fiscal_year,
            COUNT(*) AS n,
            COALESCE(SUM(h.federal_action_obligation), 0)
                AS amount,
            COUNT(m.federal_inflow_program_policy_mapping_id)
                AS matched,
            COUNT(m.federal_inflow_program_policy_mapping_id)
                FILTER (
                    WHERE m.resolved_accounting_disposition =
                        'EXCLUDE_DUPLICATE'
                ) AS excluded
        FROM analysis.v_certified_assistance_ledger h
        LEFT JOIN reference.federal_inflow_program_policy_mapping m
          ON m.source_system = 'USASPENDING_ASSISTANCE'
         AND m.source_program_code = '64.109'
         AND h.action_date_fiscal_year BETWEEN
             COALESCE(m.valid_from_fiscal_year, -9999)
             AND COALESCE(m.valid_through_fiscal_year, 9999)
        WHERE BTRIM(h.cfda_number) = '64.109'
          AND (
               (h.load_batch_id = 20
                AND h.action_date_fiscal_year = 2018)
            OR (h.load_batch_id = 21
                AND h.action_date_fiscal_year = 2019)
          )
        GROUP BY h.action_date_fiscal_year
    ) q
    WHERE NOT (
        (fiscal_year = 2018
         AND n = 465
         AND ROUND(amount, 2) = 2011292248.00)
        OR
        (fiscal_year = 2019
         AND n = 464
         AND ROUND(amount, 2) = 2373653465.00)
    )
       OR matched <> n
       OR excluded <> n;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209V fiscal-year resolution failure';
    END IF;

    RAISE NOTICE
        'ETL-209V CORE VALIDATION PASS';

END $$;

ROLLBACK;

\echo 'ETL-209V READ-ONLY VALIDATION COMPLETE'