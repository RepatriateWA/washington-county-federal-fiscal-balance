
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '=============================================================='
\echo 'ETL-215B - STATEWIDE ACCOUNTING COMPONENT MATRIX'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER MIGRATION'
\echo '=============================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. EXISTING PARTIAL BALANCE RECONCILIATION'

WITH components AS (
    SELECT
        report_year,
        COUNT(*) AS component_rows,
        COUNT(*) FILTER (WHERE program_code = 'CHIP')
            AS chip_rows,
        SUM(expenditure_dollars) AS component_sum
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year
)
SELECT
    p.report_year,
    c.component_rows,
    c.chip_rows,
    c.component_sum,
    p.tracked_expenditures_dollars,
    c.component_sum - p.tracked_expenditures_dollars
        AS expenditure_difference,
    p.gross_collections_dollars
        - c.component_sum
        - p.partial_fiscal_balance_dollars
        AS balance_difference
FROM reporting.v_washington_partial_fiscal_balance p
LEFT JOIN components c USING (report_year)
WHERE p.report_year BETWEEN 2018 AND 2024
ORDER BY p.report_year;

\echo ''
\echo '2. SEVEN-YEAR SOURCE COMPONENT MATRIX'
\echo 'Amounts are not automatically additive across categories'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
),
component_values AS (
    SELECT
        fiscal_year,
        'IRS_GROSS_COLLECTIONS'::text AS component,
        'GROSS_COLLECTIONS'::text AS measure,
        'FFY'::text AS period_basis,
        'RECEIPT_CONTROL'::text AS treatment,
        gross_collections_dollars::numeric AS amount
    FROM reporting.v_washington_revenue_summary

    UNION ALL

    SELECT
        report_year,
        'SSA_OASDI_' || program_code,
        'ANNUALIZED_DECEMBER_BENEFITS',
        'DECEMBER_SNAPSHOT',
        'PARTIAL_BALANCE_COMPONENT',
        annualized_benefits_dollars::numeric
    FROM reporting.v_washington_ssa_summary

    UNION ALL

    SELECT
        fiscal_year,
        'CMS_MEDICAID',
        'ACTUAL_FEDERAL_EXPENDITURE',
        'FFY',
        'PARTIAL_BALANCE_COMPONENT',
        federal_expenditure_amount::numeric
    FROM reporting.v_washington_medicaid_expenditures

    UNION ALL

    SELECT
        fiscal_year,
        'CMS_CHIP',
        'ACTUAL_FEDERAL_EXPENDITURE',
        'FFY',
        'PARTIAL_BALANCE_COMPONENT_ALREADY_INCLUDED',
        federal_expenditure_amount::numeric
    FROM reporting.v_washington_chip_expenditures

    UNION ALL

    SELECT
        report_year,
        'CMS_ORIGINAL_MEDICARE',
        'ACTUAL_ORIGINAL_MEDICARE_PAYMENTS',
        'SOURCE_REPORT_YEAR',
        'PARTIAL_BALANCE_COMPONENT',
        expenditure_dollars::numeric
    FROM reporting.v_washington_tracked_expenditures
    WHERE program_code = 'MEDICARE'

    UNION ALL

    SELECT
        fiscal_year,
        'OMB_ALLOCATED_FEDERAL_WAGES',
        'ALLOCATED_FEDERAL_WAGE_CONTROL',
        'FFY',
        'RECONCILIATION_PENDING',
        allocated_wa_total_federal_wage_dollars::numeric
    FROM analysis.v_wa_federal_wage_allocation

    UNION ALL

    SELECT
        fiscal_year,
        'VA_GDX',
        'ANNUAL_EXPENDITURE_CONTROL',
        'SOURCE_FISCAL_YEAR',
        'RECONCILIATION_PENDING',
        SUM(va_gdx_expenditure_amount)::numeric
    FROM va.v_washington_county_gdx_control_total
    GROUP BY fiscal_year

    UNION ALL

    SELECT
        action_date_fiscal_year,
        'USASPENDING_ASSISTANCE_GROSS',
        'NET_FEDERAL_ACTION_OBLIGATION',
        'ACTION_DATE_FFY',
        'NONADDITIVE_GROSS_UNIVERSE',
        SUM(federal_action_obligation)::numeric
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (action_date_fiscal_year IN (2018, 2019)
         AND load_batch_id IN (20, 21))
        OR
        (action_date_fiscal_year BETWEEN 2020 AND 2024
         AND reference_state_abbreviation = 'WA')
    )
    GROUP BY action_date_fiscal_year

    UNION ALL

    SELECT
        fiscal_year,
        'USASPENDING_PROCUREMENT_GROSS',
        'NET_FEDERAL_ACTION_OBLIGATION',
        'ACTION_DATE_FFY',
        'NONADDITIVE_GROSS_UNIVERSE',
        SUM(federal_action_obligation)::numeric
    FROM procurement.award_transaction
    GROUP BY fiscal_year
)
SELECT
    y.fiscal_year,
    c.component,
    c.measure,
    c.period_basis,
    c.treatment,
    ROUND(c.amount, 2) AS amount_dollars
FROM years y
LEFT JOIN component_values c
    ON c.fiscal_year = y.fiscal_year
ORDER BY y.fiscal_year, c.component;

\echo ''
\echo '3. HISTORICAL SIX-PROGRAM CONTROL'

WITH historical AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation)::numeric
            AS net_obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id IN (20, 21)
      AND action_date_fiscal_year IN (2018, 2019)
      AND TRIM(cfda_number) IN (
          '10.555', '84.010', '84.027',
          '84.063', '93.558', '93.600'
      )
    GROUP BY action_date_fiscal_year
)
SELECT
    fiscal_year,
    transaction_count,
    ROUND(net_obligations, 2) AS net_obligations,
    CASE
        WHEN fiscal_year = 2018
             AND transaction_count = 7032
             AND net_obligations = 1754545311.77
            THEN 'PASS'
        WHEN fiscal_year = 2019
             AND transaction_count = 6763
             AND net_obligations = 1868124435.30
            THEN 'PASS'
        ELSE 'FAIL'
    END AS control_status
FROM historical
ORDER BY fiscal_year;

\echo ''
\echo '4. COMPONENT COVERAGE BY YEAR'

WITH coverage AS (
    SELECT
        fiscal_year,
        COUNT(*) AS component_rows
    FROM (
        SELECT fiscal_year
        FROM reporting.v_washington_revenue_summary
        WHERE fiscal_year BETWEEN 2018 AND 2024

        UNION ALL

        SELECT report_year
        FROM reporting.v_washington_ssa_summary
        WHERE report_year BETWEEN 2018 AND 2024

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
        FROM analysis.v_wa_federal_wage_allocation
        WHERE fiscal_year BETWEEN 2018 AND 2024
    ) s
    GROUP BY fiscal_year
)
SELECT
    y.fiscal_year,
    COALESCE(c.component_rows, 0) AS component_rows
FROM generate_series(2018, 2024) y(fiscal_year)
LEFT JOIN coverage c USING (fiscal_year)
ORDER BY y.fiscal_year;

\echo ''
\echo '5. MEDICARE CORE COVERAGE AND LEDGER STATUS'

SELECT
    calendar_year,
    original_medicare_actual_ffs_dollars,
    partc_reconstructed_dollars,
    partd_reconstructed_dollars,
    partc_months_processed,
    partc_year_completeness,
    partd_coverage_status,
    combined_period_status,
    timing_basis_status,
    ledger_status
FROM cms.medicare_core_state_year
WHERE calendar_year BETWEEN 2018 AND 2024
ORDER BY calendar_year;

ROLLBACK;

\echo ''
\echo 'ETL-215B COMPLETE - READ ONLY'
