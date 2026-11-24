
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219B3 - DIAGNOSE FY2024 VA GDX STRUCTURAL EXCEPTIONS'
\echo 'READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. FY2024 COUNTY STRUCTURAL COUNTS'

WITH county AS (
    SELECT
        e.county_id,
        COUNT(*) AS total_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_DIRECT_EXPENDITURE'
        ) AS direct_control_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_INDIRECT_EXPENDITURE'
        ) AS indirect_control_rows,
        COUNT(*) FILTER (
            WHERE e.schema_regime = 'REVISED_DIRECT_INDIRECT'
        ) AS revised_rows,
        COUNT(*) FILTER (
            WHERE e.expenditure_amount IS NULL
        ) AS null_rows,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_dollars,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_dollars
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year = 2024
    GROUP BY e.county_id
)
SELECT
    total_rows,
    component_rows,
    control_rows,
    direct_control_rows,
    indirect_control_rows,
    revised_rows,
    null_rows,
    COUNT(*) AS counties,
    COUNT(*) FILTER (
        WHERE component_dollars IS DISTINCT FROM control_dollars
    ) AS financial_mismatches
FROM county
GROUP BY
    total_rows,
    component_rows,
    control_rows,
    direct_control_rows,
    indirect_control_rows,
    revised_rows,
    null_rows
ORDER BY counties DESC, total_rows;

\echo ''
\echo '2. FY2024 EXCEPTION CONDITIONS BY COUNTY'

WITH county AS (
    SELECT
        e.county_id,
        COUNT(*) AS total_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_EXPENDITURE'
        ) AS legacy_control_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_DIRECT_EXPENDITURE'
        ) AS direct_control_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_INDIRECT_EXPENDITURE'
        ) AS indirect_control_rows,
        COUNT(*) FILTER (
            WHERE e.schema_regime = 'REVISED_DIRECT_INDIRECT'
        ) AS revised_rows,
        COUNT(*) FILTER (
            WHERE e.expenditure_amount IS NULL
        ) AS null_rows,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_dollars,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_dollars
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year = 2024
    GROUP BY e.county_id
)
SELECT
    c.county_id,
    c.total_rows,
    c.component_rows,
    c.control_rows,
    c.revised_rows,
    c.null_rows,
    c.component_dollars,
    c.control_dollars,
    v.va_gdx_expenditure_amount AS reporting_dollars,
    (c.component_rows <> 9) AS bad_component_count,
    (c.control_rows <> 2) AS bad_control_count,
    (c.legacy_control_rows <> 0) AS bad_legacy_control,
    (c.direct_control_rows <> 1) AS bad_direct_control,
    (c.indirect_control_rows <> 1) AS bad_indirect_control,
    (c.revised_rows <> c.total_rows) AS bad_schema_regime,
    (c.null_rows <> 0) AS bad_null_amount,
    (c.component_dollars IS DISTINCT FROM c.control_dollars)
        AS bad_component_sum,
    (c.control_dollars IS DISTINCT FROM
        v.va_gdx_expenditure_amount) AS bad_reporting_sum
FROM county c
LEFT JOIN va.v_washington_county_gdx_control_total v
  ON v.fiscal_year = 2024
 AND v.county_id = c.county_id
WHERE c.component_rows <> 9
   OR c.control_rows <> 2
   OR c.legacy_control_rows <> 0
   OR c.direct_control_rows <> 1
   OR c.indirect_control_rows <> 1
   OR c.revised_rows <> c.total_rows
   OR c.null_rows <> 0
   OR c.component_dollars IS DISTINCT FROM c.control_dollars
   OR c.control_dollars IS DISTINCT FROM
      v.va_gdx_expenditure_amount
ORDER BY c.county_id;

\echo ''
\echo '3. FY2024 NULL-AMOUNT SOURCE RECORDS'

SELECT
    e.county_id,
    e.expenditure_class,
    c.category_code,
    c.aggregation_role,
    e.expenditure_amount
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year = 2024
  AND e.expenditure_amount IS NULL
ORDER BY e.county_id, c.category_code;

ROLLBACK;

\echo ''
\echo 'ETL-219B3 COMPLETE - READ ONLY'
