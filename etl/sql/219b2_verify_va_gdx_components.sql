
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219B2 - VA GDX REVISED COMPONENT RECONCILIATION'
\echo 'FY2018-FY2024 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. ANNUAL COMPONENT AND CONTROL RECONCILIATION'

WITH county AS (
    SELECT
        e.fiscal_year,
        e.county_id,
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
        COUNT(*) FILTER (
            WHERE e.fiscal_year < 2024
              AND e.schema_regime = 'LEGACY_STATE_SHEETS'
        ) AS legacy_rows,
        COUNT(*) FILTER (
            WHERE e.fiscal_year = 2024
              AND e.schema_regime = 'REVISED_DIRECT_INDIRECT'
        ) AS revised_rows,
        COUNT(*) AS total_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_EXPENDITURE'
        ) AS legacy_total_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_DIRECT_EXPENDITURE'
        ) AS direct_total_rows,
        COUNT(*) FILTER (
            WHERE c.category_code = 'TOTAL_INDIRECT_EXPENDITURE'
        ) AS indirect_total_rows,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS component_dollars,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_dollars
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year BETWEEN 2018 AND 2024
    GROUP BY e.fiscal_year,e.county_id
),
reconciled AS (
    SELECT
        c.*,
        v.va_gdx_expenditure_amount AS reporting_dollars,
        CASE
            WHEN c.fiscal_year < 2024 THEN
                c.component_rows = 7
                AND c.control_rows = 1
                AND c.legacy_total_rows = 1
                AND c.direct_total_rows = 0
                AND c.indirect_total_rows = 0
                AND c.legacy_rows = c.total_rows
            ELSE
                c.component_rows = 9
                AND c.control_rows = 2
                AND c.legacy_total_rows = 0
                AND c.direct_total_rows = 1
                AND c.indirect_total_rows = 1
                AND c.revised_rows = c.total_rows
        END AS valid_structure
    FROM county c
    LEFT JOIN va.v_washington_county_gdx_control_total v
      ON v.fiscal_year = c.fiscal_year
     AND v.county_id = c.county_id
)
SELECT
    fiscal_year,
    COUNT(*) AS counties,
    SUM(component_dollars) AS component_dollars,
    SUM(control_dollars) AS source_control_dollars,
    SUM(reporting_dollars) AS reporting_control_dollars,
    COUNT(*) FILTER (
        WHERE valid_structure IS DISTINCT FROM TRUE
           OR null_components <> 0
           OR null_controls <> 0
           OR component_dollars IS DISTINCT FROM control_dollars
           OR control_dollars IS DISTINCT FROM reporting_dollars
    ) AS failing_counties
FROM reconciled
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. FY2024 DIRECT / INDIRECT CONTROL RECONCILIATION'

WITH classified AS (
    SELECT
        e.county_id,
        e.expenditure_class,
        c.aggregation_role,
        e.expenditure_amount
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year = 2024
),
by_class AS (
    SELECT
        county_id,
        expenditure_class,
        SUM(expenditure_amount) FILTER (
            WHERE aggregation_role = 'COMPONENT'
        ) AS component_dollars,
        SUM(expenditure_amount) FILTER (
            WHERE aggregation_role = 'CONTROL_TOTAL'
        ) AS control_dollars
    FROM classified
    GROUP BY county_id, expenditure_class
)
SELECT
    expenditure_class,
    COUNT(*) AS counties,
    SUM(component_dollars) AS component_dollars,
    SUM(control_dollars) AS control_dollars,
    COUNT(*) FILTER (
        WHERE component_dollars IS DISTINCT FROM control_dollars
    ) AS failing_counties
FROM by_class
GROUP BY expenditure_class
ORDER BY expenditure_class;

\echo ''
\echo '3. FAIL-CLOSED INDEPENDENT ASSERTIONS'

DO $gate$
DECLARE
    v_counties bigint;
    v_years bigint;
    v_failures bigint;
    v_bad_class bigint;
    v_bad_reporting bigint;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'BLOCK: transaction not read-only';
    END IF;

    WITH county AS (
        SELECT
            e.fiscal_year,
            e.county_id,
            COUNT(*) AS total_rows,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS component_rows,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows,
            COUNT(*) FILTER (
                WHERE e.expenditure_amount IS NULL
            ) AS null_rows,
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
            WHERE null_rows <> 0
               OR components IS DISTINCT FROM controls
               OR controls IS DISTINCT FROM reported
               OR (
                   fiscal_year < 2024
                   AND (
                       component_rows <> 7
                       OR control_rows <> 1
                       OR legacy_control_rows <> 1
                       OR direct_control_rows <> 0
                       OR indirect_control_rows <> 0
                       OR legacy_rows <> total_rows
                   )
               )
               OR (
                   fiscal_year = 2024
                   AND (
                       component_rows <> 9
                       OR control_rows <> 2
                       OR legacy_control_rows <> 0
                       OR direct_control_rows <> 1
                       OR indirect_control_rows <> 1
                       OR revised_rows <> total_rows
                   )
               )
        )
    INTO v_counties,v_years,v_failures
    FROM checked;

    IF v_counties IS DISTINCT FROM 273
       OR v_years IS DISTINCT FROM 7
       OR v_failures IS DISTINCT FROM 0
    THEN
        RAISE EXCEPTION
            'BLOCK: county observations %, years %, failures %',
            v_counties,v_years,v_failures;
    END IF;

    WITH by_class AS (
        SELECT
            e.county_id,
            e.expenditure_class,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS components,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS controls,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year = 2024
        GROUP BY e.county_id,e.expenditure_class
    )
    SELECT COUNT(*) INTO v_bad_class
    FROM by_class
    WHERE components IS DISTINCT FROM controls
       OR control_rows <> 1
       OR expenditure_class NOT IN ('DIRECT','INDIRECT');

    IF v_bad_class IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION
            'BLOCK: FY2024 direct/indirect class failures %',
            v_bad_class;
    END IF;

    WITH expected AS (
        SELECT
            e.fiscal_year,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS dollars
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2018 AND 2024
        GROUP BY e.fiscal_year
    ),
    actual AS (
        SELECT
            fiscal_year,
            SUM(va_gdx_expenditure_amount) AS dollars
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    )
    SELECT COUNT(*) INTO v_bad_reporting
    FROM (
        (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    ) differences;

    IF v_bad_reporting IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION
            'BLOCK: statewide reporting differences %',
            v_bad_reporting;
    END IF;

    RAISE NOTICE
        'ETL-219B2 PASS: 273 county-years reconcile, including FY2024 direct and indirect controls';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219B2 COMPLETE - READ ONLY'
