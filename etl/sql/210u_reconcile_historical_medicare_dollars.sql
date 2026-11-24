-- ============================================================
-- WCFFBP ETL-210U
-- HISTORICAL MEDICARE DOLLAR AND COMPLETENESS RECONCILIATION
--
-- Scope: Washington, calendar/report years 2018-2019
-- Supplemental context: 2020-2024
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-210U - HISTORICAL MEDICARE DOLLAR RECONCILIATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. STATEWIDE CORE MEDICARE ACCOUNTING
-- ============================================================

\echo ''
\echo '1. CMS CORE STATEWIDE DOLLAR VALUES'

SELECT
    calendar_year,
    state_id,
    original_medicare_actual_ffs_dollars,
    partc_reconstructed_dollars,
    partd_reconstructed_dollars,
    core_medicare_sum_dollars,
    original_medicare_county_rows,
    original_medicare_beneficiaries
FROM cms.medicare_core_state_year
WHERE calendar_year BETWEEN 2018 AND 2024
ORDER BY calendar_year, state_id;


-- ============================================================
-- 2. COMPLETENESS AND TIMING
-- ============================================================

\echo ''
\echo '2. CMS CORE STATEWIDE COMPLETENESS'

SELECT
    calendar_year,
    partc_months_processed,
    partc_year_completeness,
    partc_reconstruction_coverage_pct,
    partc_accounting_coverage_pct,
    partd_dollar_source_field,
    partd_coverage_status,
    combined_period_status,
    timing_basis_status,
    ledger_status,
    methodology_version
FROM cms.medicare_core_state_year
WHERE calendar_year BETWEEN 2018 AND 2024
ORDER BY calendar_year;


-- ============================================================
-- 3. COUNTY-TO-STATE CORE RECONCILIATION
-- ============================================================

\echo ''
\echo '3. CORE COUNTY SUMS VERSUS STATEWIDE CONTROLS'

WITH county AS (
    SELECT
        calendar_year,
        COUNT(*) AS county_rows,
        COUNT(DISTINCT BTRIM(county_fips::text))
            AS distinct_county_fips,
        COUNT(*) FILTER (
            WHERE county_id IS NULL
        ) AS missing_county_ids,
        SUM(original_medicare_ffs_dollars)
            AS county_ffs,
        SUM(partc_dollars)
            AS county_partc,
        SUM(partd_dollars)
            AS county_partd,
        SUM(core_medicare_dollars)
            AS county_core
    FROM cms.medicare_core_county_year
    WHERE calendar_year BETWEEN 2018 AND 2024
    GROUP BY calendar_year
)
SELECT
    s.calendar_year,
    c.county_rows,
    c.distinct_county_fips,
    c.missing_county_ids,
    ROUND(
        (c.county_ffs -
         s.original_medicare_actual_ffs_dollars)::numeric,
        2
    ) AS ffs_difference,
    ROUND(
        (c.county_partc -
         s.partc_reconstructed_dollars)::numeric,
        2
    ) AS partc_difference,
    ROUND(
        (c.county_partd -
         s.partd_reconstructed_dollars)::numeric,
        2
    ) AS partd_difference,
    ROUND(
        (c.county_core -
         s.core_medicare_sum_dollars)::numeric,
        2
    ) AS core_difference
FROM cms.medicare_core_state_year s
JOIN county c
  ON c.calendar_year = s.calendar_year
WHERE s.calendar_year BETWEEN 2018 AND 2024
ORDER BY s.calendar_year;


-- ============================================================
-- 4. COUNTY COMPLETENESS AND LEDGER STATUS
-- ============================================================

\echo ''
\echo '4. COUNTY-LEVEL COMPLETENESS AND AUTHORIZATION'

SELECT
    calendar_year,
    original_medicare_status,
    partc_status,
    partd_status,
    core_value_status,
    partc_year_completeness,
    partd_coverage_status,
    time_window_status,
    timing_basis,
    ledger_authorization,
    COUNT(*) AS county_rows,
    ROUND(SUM(core_medicare_dollars)::numeric, 2)
        AS core_dollars
FROM cms.medicare_core_county_year
WHERE calendar_year BETWEEN 2018 AND 2024
GROUP BY
    calendar_year,
    original_medicare_status,
    partc_status,
    partd_status,
    core_value_status,
    partc_year_completeness,
    partd_coverage_status,
    time_window_status,
    timing_basis,
    ledger_authorization
ORDER BY calendar_year, county_rows DESC;


-- ============================================================
-- 5. GEOGRAPHIC MEDICARE PAYMENT SERIES
-- ============================================================

\echo ''
\echo '5. GEOGRAPHIC PAYMENT SERIES BY REPORT YEAR'

SELECT
    report_year,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT county_id) AS distinct_counties,
    COUNT(*) FILTER (
        WHERE total_medicare_payments_dollars IS NULL
    ) AS missing_payment_values,
    ROUND(
        SUM(total_medicare_payments_dollars)::numeric,
        2
    ) AS actual_payment_dollars,
    ROUND(
        SUM(standardized_medicare_payments_dollars)::numeric,
        2
    ) AS standardized_payment_dollars
FROM cms.medicare_geographic_payments
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY report_year
ORDER BY report_year;


-- ============================================================
-- 6. CORE VERSUS GEOGRAPHIC PAYMENT COMPARISON
-- ============================================================

\echo ''
\echo '6. CORE AND GEOGRAPHIC PAYMENT COMPARISON'
\echo 'WARNING: DIFFERENT MEASURES; DIFFERENCES ARE DIAGNOSTIC'

WITH geographic AS (
    SELECT
        report_year,
        SUM(total_medicare_payments_dollars)
            AS geographic_actual
    FROM cms.medicare_geographic_payments
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year
)
SELECT
    s.calendar_year,
    ROUND(s.core_medicare_sum_dollars::numeric, 2)
        AS reconstructed_core,
    ROUND(g.geographic_actual::numeric, 2)
        AS geographic_actual,
    ROUND(
        (s.core_medicare_sum_dollars -
         g.geographic_actual)::numeric,
        2
    ) AS core_minus_geographic,
    ROUND(
        (
            100 * (
                s.core_medicare_sum_dollars -
                g.geographic_actual
            ) /
            NULLIF(g.geographic_actual, 0)
        )::numeric,
        4
    ) AS difference_pct_of_geographic
FROM cms.medicare_core_state_year s
JOIN geographic g
  ON g.report_year = s.calendar_year
WHERE s.calendar_year BETWEEN 2018 AND 2024
ORDER BY s.calendar_year;


-- ============================================================
-- 7. REPORTING VIEW RECONCILIATION
-- ============================================================

\echo ''
\echo '7. GEOGRAPHIC SOURCE VERSUS STATE REPORTING VIEW'

WITH source_totals AS (
    SELECT
        report_year,
        state_id,
        SUM(total_medicare_payments_dollars)
            AS source_dollars
    FROM cms.medicare_geographic_payments
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year, state_id
),
report_totals AS (
    SELECT
        report_year,
        state_id,
        SUM(actual_medicare_payments_dollars)
            AS reported_dollars
    FROM reporting.v_medicare_expenditures_by_state_year
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year, state_id
)
SELECT
    COALESCE(s.report_year, r.report_year)
        AS report_year,
    COALESCE(s.state_id, r.state_id)
        AS state_id,
    ROUND(s.source_dollars::numeric, 2)
        AS source_dollars,
    ROUND(r.reported_dollars::numeric, 2)
        AS reported_dollars,
    ROUND(
        (s.source_dollars -
         r.reported_dollars)::numeric,
        2
    ) AS difference
FROM source_totals s
FULL OUTER JOIN report_totals r
  ON r.report_year = s.report_year
 AND r.state_id = s.state_id
ORDER BY report_year, state_id;


-- ============================================================
-- 8. HISTORICAL USASPENDING OBLIGATION CONTROL
-- ============================================================

\echo ''
\echo '8. HISTORICAL USASPENDING MEDICARE OBLIGATIONS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COUNT(*) AS transactions,
    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
GROUP BY
    action_date_fiscal_year,
    BTRIM(cfda_number)
ORDER BY fiscal_year, program_code;


-- ============================================================
-- 9. AUTOMATED STRUCTURAL CONTROLS
-- ============================================================

\echo ''
\echo '9. AUTOMATED STRUCTURAL CONTROLS'

DO $$
DECLARE
    v_core_state_rows bigint;
    v_core_county_rows bigint;
    v_geographic_rows bigint;
    v_historical_transactions bigint;
    v_historical_dollars numeric;
    v_historical_mappings bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_core_state_rows
    FROM cms.medicare_core_state_year
    WHERE calendar_year IN (2018, 2019);

    SELECT COUNT(*)
    INTO v_core_county_rows
    FROM cms.medicare_core_county_year
    WHERE calendar_year IN (2018, 2019);

    SELECT COUNT(*)
    INTO v_geographic_rows
    FROM cms.medicare_geographic_payments
    WHERE report_year IN (2018, 2019);

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO
        v_historical_transactions,
        v_historical_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    SELECT COUNT(*)
    INTO v_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code)
          IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999)
          <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999)
          >= 2018;

    IF v_core_state_rows <> 2
       OR v_core_county_rows <> 78
       OR v_geographic_rows <> 78
       OR v_historical_transactions <> 36
       OR ROUND(v_historical_dollars, 2)
          <> 2489730308.00
       OR v_historical_mappings <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210U FAIL: state %, county %, geographic %, transactions %, obligations %, mappings %',
            v_core_state_rows,
            v_core_county_rows,
            v_geographic_rows,
            v_historical_transactions,
            v_historical_dollars,
            v_historical_mappings;
    END IF;

    RAISE NOTICE
        'ETL-210U STRUCTURAL PASS: historical CMS populations and USAspending control conserved';

    RAISE NOTICE
        'MEDICARE ECONOMIC-STREAM AND FISCAL-YEAR CERTIFICATION REMAIN SUBJECT TO REVIEW';

END $$;

COMMIT;

\echo 'ETL-210U COMPLETE - READ ONLY'