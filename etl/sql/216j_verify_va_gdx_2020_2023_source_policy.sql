
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-216J - INDEPENDENT VA GDX SOURCE-POLICY CERTIFICATION'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. TOTAL VA EXPENDITURE SOURCE POLICIES'

SELECT
    federal_inflow_source_policy_id,
    methodology_version,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
ORDER BY valid_from_fiscal_year;

\echo ''
\echo '2. ANNUAL POLICY COVERAGE'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(s.federal_inflow_source_policy_id) AS policy_count,
    STRING_AGG(
        s.methodology_version, ', '
        ORDER BY s.methodology_version
    ) AS methodology_versions
FROM years y
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.inflow_family = 'VETERANS_AFFAIRS'
 AND s.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
 AND (
     s.valid_from_fiscal_year IS NULL
     OR s.valid_from_fiscal_year <= y.fiscal_year
 )
 AND (
     s.valid_through_fiscal_year IS NULL
     OR s.valid_through_fiscal_year >= y.fiscal_year
 )
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;

\echo ''
\echo '3. INDEPENDENT POLICY ASSERTIONS'

DO $verify$
DECLARE
    v_bad bigint;
BEGIN
    WITH expected(
        methodology_version,
        start_year,
        end_year
    ) AS (
        VALUES
        ('ANALYSIS-213-v1', 2018, 2019),
        ('ANALYSIS-216I-v1', 2020, 2023),
        ('ANALYSIS-149-v1', 2024, 2024)
    ),
    actual AS (
        SELECT
            s.methodology_version,
            s.valid_from_fiscal_year AS start_year,
            s.valid_through_fiscal_year AS end_year
        FROM reference.federal_inflow_source_policy s
        WHERE s.inflow_family = 'VETERANS_AFFAIRS'
          AND s.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
          AND s.accounting_measure = 'ANNUAL_EXPENDITURES'
          AND s.preferred_source = 'VA_GDX'
          AND s.allocation_source = 'VA_GDX'
          AND s.overlapping_sources =
              ARRAY['USASPENDING_PROCUREMENT']::text[]
          AND s.ledger_treatment =
              'INCLUDE_AFTER_RECONCILIATION'
    )
    SELECT COUNT(*) INTO v_bad
    FROM (
        (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    ) differences;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: VA source-policy precedent mismatch: %',
            v_bad;
    END IF;

    -- Every year must have exactly one total-VA policy,
    -- including any malformed or overlapping policy.
    WITH years AS (
        SELECT generate_series(2018, 2024) AS fiscal_year
    ),
    coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(s.federal_inflow_source_policy_id) AS n
        FROM years y
        LEFT JOIN reference.federal_inflow_source_policy s
          ON s.inflow_family = 'VETERANS_AFFAIRS'
         AND s.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
         AND (
             s.valid_from_fiscal_year IS NULL
             OR s.valid_from_fiscal_year <= y.fiscal_year
         )
         AND (
             s.valid_through_fiscal_year IS NULL
             OR s.valid_through_fiscal_year >= y.fiscal_year
         )
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*) INTO v_bad
    FROM coverage
    WHERE n <> 1;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % fiscal years lack unique VA policy',
            v_bad;
    END IF;

    RAISE NOTICE 'SOURCE-POLICY COVERAGE PASS';
END
$verify$;

\echo ''
\echo '4. INDEPENDENT COUNTY COMPONENT RECONCILIATION'

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
              AND c.aggregation_role = 'CONTROL_TOTAL'
        ) AS control_rows,
        COUNT(*) FILTER (
            WHERE e.expenditure_amount IS NULL
        ) AS null_rows,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.aggregation_role = 'COMPONENT'
        ) AS components,
        SUM(e.expenditure_amount) FILTER (
            WHERE c.category_code = 'TOTAL_EXPENDITURE'
              AND c.aggregation_role = 'CONTROL_TOTAL'
        ) AS reported_total
    FROM va.gdx_county_expenditure e
    JOIN va.gdx_expenditure_category c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year BETWEEN 2020 AND 2023
    GROUP BY e.fiscal_year, e.county_id
)
SELECT
    fiscal_year,
    COUNT(*) AS counties,
    COUNT(*) FILTER (
        WHERE component_rows <> 7
           OR component_categories <> 7
           OR control_rows <> 1
           OR null_rows <> 0
           OR components IS NULL
           OR reported_total IS NULL
           OR components <> reported_total
    ) AS failed_counties,
    SUM(components) AS component_dollars,
    SUM(reported_total) AS control_dollars,
    SUM(components - reported_total) AS difference_dollars
FROM county
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '5. FINAL FAIL-CLOSED ACCOUNTING ASSERTIONS'

DO $verify$
DECLARE
    v_counties bigint;
    v_bad bigint;
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
                  AND c.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows,
            COUNT(*) FILTER (
                WHERE e.expenditure_amount IS NULL
            ) AS null_rows,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS components,
            SUM(e.expenditure_amount) FILTER (
                WHERE c.category_code = 'TOTAL_EXPENDITURE'
                  AND c.aggregation_role = 'CONTROL_TOTAL'
            ) AS reported_total
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2020 AND 2023
        GROUP BY e.fiscal_year, e.county_id
    )
    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE component_rows <> 7
               OR component_categories <> 7
               OR control_rows <> 1
               OR null_rows <> 0
               OR components IS NULL
               OR reported_total IS NULL
               OR components <> reported_total
        )
    INTO v_counties, v_bad
    FROM county;

    IF v_counties <> 156 OR v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: county count %, failures %',
            v_counties, v_bad;
    END IF;

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
    SELECT COUNT(*) INTO v_bad
    FROM (
        (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
        UNION ALL
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    ) differences;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: statewide GDX control mismatch';
    END IF;

    RAISE NOTICE
        'INDEPENDENT ACCOUNTING CERTIFICATION PASS';
END
$verify$;

ROLLBACK;

\echo ''
\echo 'ETL-216J COMPLETE - READ ONLY'
