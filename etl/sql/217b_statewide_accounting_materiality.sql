
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-217B - STATEWIDE ACCOUNTING MATERIALITY'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER PROMOTION'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. SOURCE-YEAR ACCOUNTING MATRIX'

WITH revenue AS (
    SELECT fiscal_year, gross_collections_dollars::numeric AS dollars
    FROM reporting.v_washington_revenue_summary
    WHERE fiscal_year BETWEEN 2018 AND 2024
),
measures AS (
    SELECT fiscal_year, 'IRS_COLLECTIONS'::text AS source,
           'REVENUE_CONTROL'::text AS accounting_basis,
           'FFY'::text AS period_basis,
           'STATE'::text AS geography_basis,
           'REVENUE_ONLY'::text AS readiness,
           dollars
    FROM revenue

    UNION ALL
    SELECT fiscal_year, 'CMS_MEDICAID',
           'ACTUAL_EXPENDITURE', 'FFY', 'STATE',
           CASE WHEN is_additive_to_fiscal_balance
                     AND amount_method = 'ACTUAL_EXPENDITURE'
                THEN 'ADDITIVE_CANDIDATE'
                ELSE 'REVIEW_REQUIRED' END,
           federal_expenditure_amount::numeric
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL
    SELECT fiscal_year, 'CMS_CHIP',
           'ACTUAL_EXPENDITURE', 'FFY', 'STATE',
           CASE WHEN is_additive_to_fiscal_balance
                     AND amount_method = 'ACTUAL_EXPENDITURE'
                THEN 'ADDITIVE_CANDIDATE'
                ELSE 'REVIEW_REQUIRED' END,
           federal_expenditure_amount::numeric
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL
    SELECT fiscal_year, 'VA_GDX',
           'ANNUAL_EXPENDITURE', 'FFY', 'COUNTY',
           'INCLUDE_AFTER_RECONCILIATION',
           SUM(va_gdx_expenditure_amount)::numeric
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year

    UNION ALL
    SELECT fiscal_year, 'FEDERAL_CIVILIAN_WAGES',
           'ALLOCATED_COMPENSATION', 'FFY_ALLOCATION',
           'COUNTY_ALLOCATION', 'OVERLAP_REVIEW',
           allocated_wa_civilian_wage_dollars::numeric
    FROM analysis.v_wa_federal_wage_allocation
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL
    SELECT fiscal_year, 'FEDERAL_MILITARY_WAGES',
           'ALLOCATED_COMPENSATION', 'FFY_ALLOCATION',
           'COUNTY_ALLOCATION', 'OVERLAP_REVIEW',
           allocated_wa_military_wage_dollars::numeric
    FROM analysis.v_wa_federal_wage_allocation
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL
    SELECT report_year, 'SSA_' || program_code,
           'DECEMBER_ANNUALIZED_BENEFITS',
           'REPORT_YEAR_ANNUALIZED', 'COUNTY',
           'ACTUAL_CASH_NOT_ESTABLISHED',
           annualized_benefits_dollars::numeric
    FROM reporting.v_washington_ssa_summary
    WHERE report_year BETWEEN 2018 AND 2024
      AND program_code IN (
          'OASDI_DISABILITY',
          'OASDI_RETIREMENT',
          'OASDI_SURVIVORS'
      )

    UNION ALL
    SELECT calendar_year, 'MEDICARE_ORIGINAL_FFS',
           'ACTUAL_PAYMENTS', 'CALENDAR_YEAR',
           'STATE', 'FFY_CONVERSION_NOT_AUTHORIZED',
           original_medicare_actual_ffs_dollars::numeric
    FROM cms.medicare_core_state_year
    WHERE calendar_year BETWEEN 2018 AND 2024
      AND state_id = 48
)
SELECT
    m.fiscal_year AS year_label,
    m.source,
    m.accounting_basis,
    m.period_basis,
    m.geography_basis,
    m.readiness,
    ROUND(m.dollars,2) AS observed_dollars,
    ROUND(
        100 * m.dollars / NULLIF(r.dollars,0),2
    ) AS pct_of_same_label_irs_collections
FROM measures m
JOIN revenue r ON r.fiscal_year = m.fiscal_year
ORDER BY m.fiscal_year,m.source;

\echo ''
\echo '2. FAIL-CLOSED COVERAGE AND NUMERIC GATE'

DO $gate$
DECLARE
    v_bad bigint;
    v_count bigint;
BEGIN
    WITH measures AS (
        SELECT fiscal_year, 'IRS' AS source,
               gross_collections_dollars::numeric AS dollars
        FROM reporting.v_washington_revenue_summary
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT fiscal_year, 'MEDICAID',
               federal_expenditure_amount::numeric
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT fiscal_year, 'CHIP',
               federal_expenditure_amount::numeric
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT fiscal_year, 'VA_GDX',
               SUM(va_gdx_expenditure_amount)::numeric
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year

        UNION ALL
        SELECT fiscal_year, 'CIVILIAN_WAGES',
               allocated_wa_civilian_wage_dollars::numeric
        FROM analysis.v_wa_federal_wage_allocation
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT fiscal_year, 'MILITARY_WAGES',
               allocated_wa_military_wage_dollars::numeric
        FROM analysis.v_wa_federal_wage_allocation
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL
        SELECT report_year, 'SSA_' || program_code,
               annualized_benefits_dollars::numeric
        FROM reporting.v_washington_ssa_summary
        WHERE report_year BETWEEN 2018 AND 2024
          AND program_code IN (
              'OASDI_DISABILITY',
              'OASDI_RETIREMENT',
              'OASDI_SURVIVORS'
          )

        UNION ALL
        SELECT calendar_year, 'MEDICARE_FFS',
               original_medicare_actual_ffs_dollars::numeric
        FROM cms.medicare_core_state_year
        WHERE calendar_year BETWEEN 2018 AND 2024
          AND state_id = 48
    ),
    expected AS (
        SELECT y, source
        FROM generate_series(2018,2024) AS y
        CROSS JOIN (
            VALUES
            ('IRS'),('MEDICAID'),('CHIP'),('VA_GDX'),
            ('CIVILIAN_WAGES'),('MILITARY_WAGES'),
            ('SSA_OASDI_DISABILITY'),
            ('SSA_OASDI_RETIREMENT'),
            ('SSA_OASDI_SURVIVORS'),
            ('MEDICARE_FFS')
        ) AS s(source)
    ),
    observed AS (
        SELECT fiscal_year,source,
               COUNT(*) AS n,
               COUNT(*) FILTER (
                   WHERE dollars IS NULL OR dollars < 0
               ) AS invalid
        FROM measures
        GROUP BY fiscal_year,source
    )
    SELECT COUNT(*) INTO v_bad
    FROM expected e
    LEFT JOIN observed o
      ON o.fiscal_year=e.y
     AND o.source=e.source
    WHERE COALESCE(o.n,0) <> 1
       OR COALESCE(o.invalid,0) <> 0;

    SELECT
        COUNT(*)
    INTO v_count
    FROM (
        SELECT fiscal_year
        FROM reporting.v_washington_revenue_summary
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT fiscal_year
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT fiscal_year
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT fiscal_year
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year

        UNION ALL

        SELECT fiscal_year
        FROM analysis.v_wa_federal_wage_allocation
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT fiscal_year
        FROM analysis.v_wa_federal_wage_allocation
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT report_year
        FROM reporting.v_washington_ssa_summary
        WHERE report_year BETWEEN 2018 AND 2024
          AND program_code IN (
              'OASDI_DISABILITY',
              'OASDI_RETIREMENT',
              'OASDI_SURVIVORS'
          )

        UNION ALL

        SELECT calendar_year
        FROM cms.medicare_core_state_year
        WHERE calendar_year BETWEEN 2018 AND 2024
          AND state_id = 48
    ) AS source_year_rows;

    IF v_bad <> 0 OR v_count <> 70 THEN
        RAISE EXCEPTION
            'BLOCK: source-year coverage failures %, rows %',
            v_bad,v_count;
    END IF;

    RAISE NOTICE
        'ETL-217B SOURCE-YEAR COVERAGE PASS: 70 OBSERVATIONS';
END
$gate$;

\echo ''
\echo '3. UNRESOLVED MEDICARE COMPONENT MATERIALITY'

SELECT
    calendar_year,
    ROUND(partc_reconstructed_dollars::numeric,2)
        AS partc_observed_dollars,
    partc_year_completeness,
    ROUND(partd_reconstructed_dollars::numeric,2)
        AS partd_observed_dollars,
    partd_coverage_status,
    timing_basis_status,
    ledger_status
FROM cms.medicare_core_state_year
WHERE calendar_year BETWEEN 2018 AND 2024
  AND state_id = 48
ORDER BY calendar_year;

\echo ''
\echo '4. VA SOURCE-SELECTION POLICY'

SELECT
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

ROLLBACK;

\echo ''
\echo 'ETL-217B COMPLETE - READ ONLY'
