
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219B5 - VA GDX COUNTY CONTROL CERTIFICATION'
\echo 'FY2018-FY2024 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. ANNUAL SOURCE-TO-REPORTING RECONCILIATION'

WITH county AS (
    SELECT
        e.fiscal_year,
        e.county_id,
        COUNT(*) AS source_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_rows,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
              AND e.expenditure_amount IS NULL
        ) AS null_components,
        COUNT(*) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
              AND e.expenditure_amount IS NULL
        ) AS null_controls,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS known_component_dollars,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS source_control_dollars
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year BETWEEN 2018 AND 2024
    GROUP BY e.fiscal_year,e.county_id
)
SELECT
    c.fiscal_year,
    COUNT(*) AS counties,
    SUM(c.source_rows) AS source_rows,
    SUM(c.null_components) AS null_components,
    SUM(c.known_component_dollars)
        AS known_component_dollars,
    SUM(c.source_control_dollars)
        AS source_control_dollars,
    SUM(v.va_gdx_expenditure_amount)
        AS reporting_control_dollars,
    COUNT(*) FILTER (
        WHERE c.known_component_dollars
              IS DISTINCT FROM c.source_control_dollars
           OR c.source_control_dollars
              IS DISTINCT FROM v.va_gdx_expenditure_amount
           OR c.null_controls <> 0
    ) AS financial_exceptions
FROM county c
LEFT JOIN va.v_washington_county_gdx_control_total v
  ON v.fiscal_year = c.fiscal_year
 AND v.county_id = c.county_id
GROUP BY c.fiscal_year
ORDER BY c.fiscal_year;

\echo ''
\echo '2. INDEPENDENT FAIL-CLOSED CERTIFICATION GATE'

DO $gate$
DECLARE
    v_failures bigint;
    v_years bigint;
    v_counties bigint;
    v_null_2024 bigint;
    v_bad_totals bigint;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'BLOCK: transaction not read-only';
    END IF;

    WITH county AS (
        SELECT
            e.fiscal_year,
            e.county_id,
            COUNT(*) AS source_rows,
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
                WHERE e.fiscal_year < 2024
                  AND e.schema_regime = 'LEGACY_STATE_SHEETS'
            ) AS legacy_rows,
            COUNT(*) FILTER (
                WHERE e.fiscal_year = 2024
                  AND e.schema_regime = 'REVISED_DIRECT_INDIRECT'
            ) AS revised_rows,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
                  AND e.expenditure_amount IS NULL
            ) AS null_components,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
                  AND e.expenditure_amount IS NULL
            ) AS null_controls,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS components,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS controls
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2018 AND 2024
        GROUP BY e.fiscal_year,e.county_id
    ),
    checked AS (
        SELECT
            c.*,
            v.va_gdx_expenditure_amount AS reported
        FROM county c
        LEFT JOIN va.v_washington_county_gdx_control_total v
          ON v.fiscal_year = c.fiscal_year
         AND v.county_id = c.county_id
    )
    SELECT
        COUNT(*),
        COUNT(DISTINCT fiscal_year),
        COUNT(*) FILTER (
            WHERE components IS DISTINCT FROM controls
               OR controls IS DISTINCT FROM reported
               OR null_controls <> 0
               OR (
                   fiscal_year < 2024
                   AND (
                       source_rows <> 8
                       OR component_rows <> 7
                       OR control_rows <> 1
                       OR legacy_control_rows <> 1
                       OR direct_control_rows <> 0
                       OR indirect_control_rows <> 0
                       OR legacy_rows <> source_rows
                       OR null_components <> 0
                   )
               )
               OR (
                   fiscal_year = 2024
                   AND (
                       source_rows <> 11
                       OR component_rows <> 9
                       OR control_rows <> 2
                       OR legacy_control_rows <> 0
                       OR direct_control_rows <> 1
                       OR indirect_control_rows <> 1
                       OR revised_rows <> source_rows
                   )
               )
        ),
        COALESCE(SUM(null_components) FILTER (
            WHERE fiscal_year = 2024
        ),0)
    INTO
        v_counties,
        v_years,
        v_failures,
        v_null_2024
    FROM checked;

    IF v_counties IS DISTINCT FROM 273
       OR v_years IS DISTINCT FROM 7
       OR v_failures IS DISTINCT FROM 0
       OR v_null_2024 IS DISTINCT FROM 56
    THEN
        RAISE EXCEPTION
            'BLOCK: county-years %, years %, failures %, FY2024 NULL components %',
            v_counties,v_years,v_failures,v_null_2024;
    END IF;

    WITH actual AS (
        SELECT
            fiscal_year,
            SUM(va_gdx_expenditure_amount) AS dollars
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    ),
    expected(fiscal_year,dollars) AS (
        VALUES
        (2018,4377268316.65::numeric),
        (2019,4896346222.98::numeric),
        (2020,5296544030.00::numeric),
        (2021,5323281703.03::numeric),
        (2022,6218866293.72::numeric),
        (2023,6526168355.17::numeric),
        (2024,6926923691.03::numeric)
    )
    SELECT COUNT(*) INTO v_bad_totals
    FROM (
        (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    ) differences;

    IF v_bad_totals IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION
            'BLOCK: annual control differences %',
            v_bad_totals;
    END IF;

    RAISE NOTICE
        'ETL-219B5 PASS: 273 county-years, 7 annual controls, 56 retained FY2024 NULL components';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219B5 COMPLETE - READ ONLY'
