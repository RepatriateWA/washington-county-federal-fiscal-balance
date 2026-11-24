\pset pager off
\echo ============================================================
\echo ETL-239A10 - IRS COUNTY REFUND PROFILE
\echo READ ONLY
\echo ============================================================

BEGIN TRANSACTION READ ONLY;

\echo === 1. ANNUAL COVERAGE ===

SELECT
    tax_year,
    COUNT(*) AS records,
    COUNT(DISTINCT county_fips) AS distinct_counties,
    COUNT(overpayments_refunded_amount) AS populated,
    COUNT(*) FILTER (
        WHERE overpayments_refunded_amount IS NULL
    ) AS null_records,
    SUM(overpayments_refunded_amount) AS refund_source_units
FROM irs.county_income_tax
GROUP BY tax_year
ORDER BY tax_year;

\echo === 2. NULL DISTRIBUTION ===

SELECT
    tax_year,
    agi_bracket_label,
    COUNT(*) AS records,
    COUNT(*) FILTER (
        WHERE overpayments_refunded_amount IS NULL
    ) AS null_records
FROM irs.county_income_tax
GROUP BY tax_year, agi_bracket_label
ORDER BY tax_year, agi_bracket_label;

\echo === 3. REFUND FIELD DISTRIBUTION ===

SELECT
    tax_year,
    MIN(overpayments_refunded_amount) AS minimum_value,
    MAX(overpayments_refunded_amount) AS maximum_value,
    SUM(overpayments_refunded_amount) AS sum_source_units
FROM irs.county_income_tax
GROUP BY tax_year
ORDER BY tax_year;

ROLLBACK;

\echo === END ETL-239A10 ===
