
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-216H - VA GDX FY2020-FY2023 COMPONENT RECONCILIATION'
\echo 'READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. CATEGORY AND AGGREGATION INVENTORY'

SELECT
    c.category_code,
    c.category_name,
    c.aggregation_role,
    e.fiscal_year,
    COUNT(*) AS observations,
    COUNT(DISTINCT e.county_id) AS counties,
    SUM(e.expenditure_amount) AS dollars
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2023
GROUP BY
    c.category_code,
    c.category_name,
    c.aggregation_role,
    e.fiscal_year
ORDER BY e.fiscal_year, c.aggregation_role, c.category_code;

\echo ''
\echo '2. LOAD-BATCH PROVENANCE'

SELECT
    gdx_load_batch_id,
    fiscal_year,
    source_file,
    source_sha256,
    schema_regime,
    methodology_regime,
    methodology_break,
    load_status,
    source_county_rows,
    loaded_expenditure_rows,
    rejected_row_count
FROM va.gdx_load_batch
WHERE fiscal_year BETWEEN 2020 AND 2023
ORDER BY fiscal_year, gdx_load_batch_id;

\echo ''
\echo '3. COUNTY COMPONENT RECONCILIATION SUMMARY'

WITH county AS (
    SELECT
        e.fiscal_year,
        e.county_id,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_rows,
        COUNT(DISTINCT c.category_code) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_categories,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_EXPENDITURE'
        ) AS total_rows,
        COUNT(*) FILTER (
            WHERE e.expenditure_amount IS NULL
        ) AS null_amount_rows,
        COALESCE(SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ),0) AS component_dollars,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.category_code = 'TOTAL_EXPENDITURE'
        ) AS reported_total_dollars
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year BETWEEN 2020 AND 2023
    GROUP BY e.fiscal_year, e.county_id
)
SELECT
    fiscal_year,
    COUNT(*) AS county_count,
    MIN(component_categories) AS min_component_categories,
    MAX(component_categories) AS max_component_categories,
    COUNT(*) FILTER (
        WHERE component_rows <> 7
           OR component_categories <> 7
           OR total_rows <> 1
           OR null_amount_rows <> 0
           OR component_dollars <> reported_total_dollars
    ) AS failing_counties,
    SUM(component_dollars) AS component_dollars,
    SUM(reported_total_dollars) AS control_dollars,
    SUM(component_dollars - reported_total_dollars)
        AS difference_dollars
FROM county
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '4. FAIL-CLOSED COMPONENT ASSERTIONS'

DO $verify$
DECLARE
    v_failures bigint;
    v_years bigint;
BEGIN
    WITH county AS (
        SELECT
            e.fiscal_year,
            e.county_id,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS component_rows,
            COUNT(DISTINCT c.category_code) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS component_categories,
            COUNT(*) FILTER (
                WHERE c.category_code = 'TOTAL_EXPENDITURE'
            ) AS total_rows,
            COUNT(*) FILTER (
                WHERE e.expenditure_amount IS NULL
            ) AS null_amount_rows,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS component_dollars,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.category_code = 'TOTAL_EXPENDITURE'
            ) AS control_dollars
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2020 AND 2023
        GROUP BY e.fiscal_year, e.county_id
    )
    SELECT
        COUNT(*) FILTER (
            WHERE component_rows <> 7
               OR component_categories <> 7
               OR total_rows <> 1
               OR null_amount_rows <> 0
               OR component_dollars IS NULL
               OR control_dollars IS NULL
               OR component_dollars <> control_dollars
        ),
        COUNT(DISTINCT fiscal_year)
    INTO v_failures, v_years
    FROM county;

    IF v_failures <> 0 OR v_years <> 4 THEN
        RAISE EXCEPTION
            'BLOCK: component failures %, years %',
            v_failures, v_years;
    END IF;

    RAISE NOTICE
        'COUNTY COMPONENT RECONCILIATION PASS';
END
$verify$;

\echo ''
\echo '5. STATEWIDE CONTROL ASSERTIONS'

DO $verify$
DECLARE
    v_failures bigint;
BEGIN
    WITH actual AS (
        SELECT
            fiscal_year,
            SUM(va_gdx_expenditure_amount) AS dollars
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2020 AND 2023
        GROUP BY fiscal_year
    ),
    expected(fiscal_year, dollars) AS (
        VALUES
        (2020,5296544030.00::numeric),
        (2021,5323281703.03::numeric),
        (2022,6218866293.72::numeric),
        (2023,6526168355.17::numeric)
    )
    SELECT COUNT(*) INTO v_failures
    FROM (
        (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    ) differences;

    IF v_failures <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: statewide control differences %',
            v_failures;
    END IF;

    RAISE NOTICE
        'STATEWIDE GDX CONTROLS PASS';
END
$verify$;

ROLLBACK;

\echo ''
\echo 'ETL-216H COMPLETE - READ ONLY'
