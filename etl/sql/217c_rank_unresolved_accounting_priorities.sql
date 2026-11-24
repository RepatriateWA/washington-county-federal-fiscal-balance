
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-217C - UNRESOLVED ACCOUNTING PRIORITIES'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER PROMOTION'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. REQUIRED SOURCE OBJECTS'

DO $gate$
DECLARE
    v_missing text;
BEGIN
    WITH required(schema_name, object_name) AS (
        VALUES
        ('reporting','v_washington_revenue_summary'),
        ('reporting','v_washington_chip_expenditures'),
        ('reporting','v_washington_medicaid_expenditures'),
        ('reporting','v_washington_ssa_summary'),
        ('analysis','v_wa_federal_wage_allocation'),
        ('cms','medicare_core_state_year'),
        ('va','v_washington_county_gdx_control_total'),
        ('reference','federal_inflow_source_policy')
    )
    SELECT string_agg(
        format('%I.%I',schema_name,object_name), ', '
    )
    INTO v_missing
    FROM required
    WHERE to_regclass(
        format('%I.%I',schema_name,object_name)
    ) IS NULL;

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'BLOCK: missing objects: %',v_missing;
    END IF;

    RAISE NOTICE 'ETL-217C OBJECT GATE PASS';
END
$gate$;

\echo ''
\echo '2. FY2024 ACCOUNTING PRIORITY MATRIX'

WITH revenue AS (
    SELECT gross_collections_dollars::numeric AS dollars
    FROM reporting.v_washington_revenue_summary
    WHERE fiscal_year = 2024
),
observations AS (
    SELECT
        'SSA_OASDI'::text AS source_family,
        SUM(annualized_benefits_dollars)::numeric AS dollars,
        'DECEMBER_ANNUALIZED'::text AS basis,
        'ACTUAL_ANNUAL_CASH'::text AS missing_control,
        'SOURCE_RECONCILIATION'::text AS next_action
    FROM reporting.v_washington_ssa_summary
    WHERE report_year = 2024
      AND program_code IN (
          'OASDI_DISABILITY',
          'OASDI_RETIREMENT',
          'OASDI_SURVIVORS'
      )

    UNION ALL
    SELECT
        'FEDERAL_WAGES',
        allocated_wa_total_federal_wage_dollars::numeric,
        'ALLOCATED_COMPENSATION',
        'OVERLAP_AND_ALLOCATION_VALIDATION',
        'SOURCE_RECONCILIATION'
    FROM analysis.v_wa_federal_wage_allocation
    WHERE fiscal_year = 2024

    UNION ALL
    SELECT
        'MEDICARE_ORIGINAL_FFS',
        original_medicare_actual_ffs_dollars::numeric,
        'CALENDAR_YEAR_PAYMENTS',
        'FFY_TIMING_CONVERSION',
        'PERIOD_RECONCILIATION'
    FROM cms.medicare_core_state_year
    WHERE calendar_year = 2024 AND state_id = 48

    UNION ALL
    SELECT
        'MEDICARE_PART_C',
        partc_reconstructed_dollars::numeric,
        'PARTIAL_CALENDAR_YEAR',
        'COMPLETE_YEAR_AND_FFY_CONVERSION',
        'SOURCE_COMPLETENESS'
    FROM cms.medicare_core_state_year
    WHERE calendar_year = 2024 AND state_id = 48

    UNION ALL
    SELECT
        'MEDICARE_PART_D',
        partd_reconstructed_dollars::numeric,
        'PARTIAL_DOLLAR_COVERAGE',
        'COMPLETE_PAYMENT_COVERAGE_AND_FFY',
        'SOURCE_COMPLETENESS'
    FROM cms.medicare_core_state_year
    WHERE calendar_year = 2024 AND state_id = 48

    UNION ALL
    SELECT
        'VA_GDX',
        SUM(va_gdx_expenditure_amount)::numeric,
        'ANNUAL_EXPENDITURES',
        'FINAL_LEDGER_OVERLAP_AUTHORIZATION',
        'POLICY_RECONCILIATION'
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year = 2024

    UNION ALL
    SELECT
        'CMS_MEDICAID',
        federal_expenditure_amount::numeric,
        'ACTUAL_FFY_EXPENDITURE',
        'FINAL_LEDGER_CERTIFICATION',
        'CERTIFICATION_REVIEW'
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year = 2024

    UNION ALL
    SELECT
        'CMS_CHIP',
        federal_expenditure_amount::numeric,
        'ACTUAL_FFY_EXPENDITURE',
        'FINAL_LEDGER_CERTIFICATION',
        'CERTIFICATION_REVIEW'
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year = 2024
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY o.dollars DESC NULLS LAST,o.source_family
    ) AS magnitude_rank,
    o.source_family,
    ROUND(o.dollars,2) AS observed_dollars,
    ROUND(
        100 * o.dollars / NULLIF(r.dollars,0),2
    ) AS pct_of_2024_irs_collections,
    o.basis,
    o.missing_control,
    o.next_action
FROM observations o
CROSS JOIN revenue r
ORDER BY magnitude_rank;

\echo ''
\echo '3. SEVEN-YEAR SOURCE COVERAGE'

WITH observed AS (
    SELECT 'SSA_OASDI'::text AS source_family,
           report_year AS year_label
    FROM reporting.v_washington_ssa_summary
    WHERE report_year BETWEEN 2018 AND 2024
      AND program_code IN (
          'OASDI_DISABILITY',
          'OASDI_RETIREMENT',
          'OASDI_SURVIVORS'
      )
    GROUP BY report_year
    HAVING COUNT(*) = 3

    UNION ALL
    SELECT 'FEDERAL_WAGES',fiscal_year
    FROM analysis.v_wa_federal_wage_allocation
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL
    SELECT 'MEDICARE',calendar_year
    FROM cms.medicare_core_state_year
    WHERE calendar_year BETWEEN 2018 AND 2024
      AND state_id = 48

    UNION ALL
    SELECT 'VA_GDX',fiscal_year
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
    HAVING COUNT(*) = 39
       AND COUNT(DISTINCT county_id) = 39

    UNION ALL
    SELECT 'CMS_MEDICAID',fiscal_year
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL
    SELECT 'CMS_CHIP',fiscal_year
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
)
SELECT
    source_family,
    COUNT(*) AS years_present,
    MIN(year_label) AS first_year,
    MAX(year_label) AS last_year
FROM observed
GROUP BY source_family
ORDER BY source_family;

\echo ''
\echo '4. SOURCE-POLICY COVERAGE FOR VA'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.federal_inflow_source_policy_id) AS policies,
    STRING_AGG(
        p.methodology_version, ', '
        ORDER BY p.methodology_version
    ) AS methodology_versions
FROM years y
LEFT JOIN reference.federal_inflow_source_policy p
  ON p.inflow_family = 'VETERANS_AFFAIRS'
 AND p.inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
 AND (
     p.valid_from_fiscal_year IS NULL
     OR p.valid_from_fiscal_year <= y.fiscal_year
 )
 AND (
     p.valid_through_fiscal_year IS NULL
     OR p.valid_through_fiscal_year >= y.fiscal_year
 )
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;

\echo ''
\echo '5. FAIL-CLOSED SOURCE COVERAGE GATE'

DO $gate$
DECLARE
    v_bad integer;
BEGIN
    WITH years AS (
        SELECT generate_series(2018,2024) AS yr
    ),
    coverage AS (
        SELECT 'IRS'::text AS source, fiscal_year AS yr
        FROM reporting.v_washington_revenue_summary
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT 'SSA',report_year
        FROM reporting.v_washington_ssa_summary
        WHERE report_year BETWEEN 2018 AND 2024
          AND program_code IN (
              'OASDI_DISABILITY',
              'OASDI_RETIREMENT',
              'OASDI_SURVIVORS'
          )
        GROUP BY report_year
        HAVING COUNT(*) = 3

        UNION ALL
        SELECT 'WAGES',fiscal_year
        FROM analysis.v_wa_federal_wage_allocation
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT 'MEDICARE',calendar_year
        FROM cms.medicare_core_state_year
        WHERE calendar_year BETWEEN 2018 AND 2024
          AND state_id = 48

        UNION ALL
        SELECT 'VA',fiscal_year
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
        HAVING COUNT(*) = 39
           AND COUNT(DISTINCT county_id) = 39

        UNION ALL
        SELECT 'MEDICAID',fiscal_year
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT 'CHIP',fiscal_year
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
    ),
    expected AS (
        SELECT s.source,y.yr
        FROM (
            VALUES ('IRS'),('SSA'),('WAGES'),
                   ('MEDICARE'),('VA'),('MEDICAID'),('CHIP')
        ) s(source)
        CROSS JOIN years y
    ),
    counts AS (
        SELECT source,yr,COUNT(*) AS n
        FROM coverage
        GROUP BY source,yr
    )
    SELECT COUNT(*) INTO v_bad
    FROM expected e
    LEFT JOIN counts c
      ON c.source=e.source AND c.yr=e.yr
    WHERE COALESCE(c.n,0) <> 1;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % missing or duplicate source-year controls',
            v_bad;
    END IF;

    RAISE NOTICE
        'ETL-217C SEVEN-YEAR SOURCE COVERAGE PASS';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-217C COMPLETE - READ ONLY'
