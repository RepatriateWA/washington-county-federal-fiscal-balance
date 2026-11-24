\pset pager off
\echo ============================================================
\echo ETL-239A11 - IRS REFUND GEOGRAPHY RECONCILIATION
\echo READ ONLY
\echo ============================================================

BEGIN TRANSACTION READ ONLY;

\echo === 1. GEOGRAPHIC IDENTIFIERS ===

SELECT DISTINCT
    county_fips,
    full_fips
FROM irs.county_income_tax
WHERE tax_year = 2023
ORDER BY county_fips, full_fips;

\echo === 2. TOTAL AGI CATEGORY BY YEAR ===

SELECT
    tax_year,
    county_fips,
    full_fips,
    overpayments_refunded_amount
FROM irs.county_income_tax
WHERE agi_bracket_label = 'Total'
  AND county_fips IN ('000', '0')
ORDER BY tax_year, county_fips;

\echo === 3. STATEWIDE VS COUNTY SUMS ===

SELECT
    tax_year,
    SUM(overpayments_refunded_amount) FILTER (
        WHERE agi_bracket_label = 'Total'
          AND county_fips IN ('000', '0')
    ) AS statewide_total_source_units,
    SUM(overpayments_refunded_amount) FILTER (
        WHERE agi_bracket_label = 'Total'
          AND county_fips NOT IN ('000', '0')
    ) AS county_sum_source_units
FROM irs.county_income_tax
GROUP BY tax_year
ORDER BY tax_year;

ROLLBACK;

\echo === END ETL-239A11 ===
