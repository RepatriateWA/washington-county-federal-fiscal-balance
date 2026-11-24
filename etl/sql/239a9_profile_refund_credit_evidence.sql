\pset pager off
\echo ============================================================
\echo ETL-239A9 - REFUND AND TAX CREDIT EVIDENCE
\echo READ ONLY
\echo ============================================================

BEGIN TRANSACTION READ ONLY;

\echo === 1. IRS COUNTY TAX STRUCTURE ===

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'irs'
  AND table_name = 'county_income_tax'
ORDER BY ordinal_position;

\echo === 2. IRS COUNTY REFUND COVERAGE ===

SELECT
    COUNT(*) AS total_rows,
    COUNT(overpayments_refunded_amount) AS populated_refund_rows,
    COUNT(*) FILTER (
        WHERE overpayments_refunded_amount IS NULL
    ) AS null_refund_rows,
    MIN(overpayments_refunded_amount) AS minimum_refund,
    MAX(overpayments_refunded_amount) AS maximum_refund
FROM irs.county_income_tax;

\echo === 3. ASSISTANCE LISTINGS MATCHING TAX CREDITS ===

SELECT
    cfda_number,
    cfda_title
FROM assistance.assistance_listing
WHERE
    cfda_title ILIKE '%tax credit%'
    OR cfda_title ILIKE '%earned income%'
    OR cfda_title ILIKE '%child tax%'
    OR cfda_title ILIKE '%refundable%'
    OR cfda_title ILIKE '%internal revenue%'
ORDER BY cfda_number;

\echo === 4. EXPENDITURE PROGRAMS MATCHING TAX CREDITS ===

SELECT
    program_code,
    program_name
FROM expenditure.program
WHERE
    program_name ILIKE '%tax credit%'
    OR program_name ILIKE '%earned income%'
    OR program_name ILIKE '%child tax%'
    OR program_name ILIKE '%refund%'
ORDER BY program_code;

\echo === 5. FEDERAL PROGRAM CLASSIFICATIONS ===

SELECT
    program_code,
    program_name,
    program_category,
    is_revenue_program,
    is_expenditure_program
FROM reference.federal_program
WHERE
    program_name ILIKE '%tax credit%'
    OR program_name ILIKE '%earned income%'
    OR program_name ILIKE '%child tax%'
    OR program_name ILIKE '%refund%'
ORDER BY program_code;

ROLLBACK;

\echo === END ETL-239A9 ===
