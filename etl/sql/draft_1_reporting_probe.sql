-- ================================================================================================
-- WCFFBP DRAFT-1 REPORTING-LAYER PROBE
-- READ ONLY
-- ================================================================================================

-- --------------------------------------------------------------------------------
-- 1. COLUMN DEFINITIONS
-- --------------------------------------------------------------------------------

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE (table_schema, table_name) IN
(
    ('reporting', 'v_federal_receipts_by_state_year'),
    ('reporting', 'v_federal_expenditures_by_state_year'),
    ('reporting', 'v_washington_partial_fiscal_balance'),
    ('reporting', 'v_washington_revenue_summary'),
    ('reporting', 'v_washington_tracked_expenditures'),
    ('reporting', 'v_medicare_expenditures_by_state_year'),
    ('reporting', 'v_washington_medicaid_expenditures'),
    ('reporting', 'v_washington_chip_expenditures'),
    ('reporting', 'v_washington_ssa_summary'),
    ('analysis', 'v_wa_federal_wage_allocation'),
    ('va', 'v_washington_county_gdx_control_total')
)
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- --------------------------------------------------------------------------------
-- 2. EXISTING PARTIAL FISCAL BALANCE
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_washington_partial_fiscal_balance
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 3. WASHINGTON REVENUE / RECEIPTS
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_washington_revenue_summary
ORDER BY 1;

SELECT *
FROM reporting.v_federal_receipts_by_state_year
WHERE
       state_abbreviation = 'WA'
    OR state_abbreviation IS NULL
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 4. EXISTING TRACKED EXPENDITURES
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_washington_tracked_expenditures
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 5. EXISTING STATE EXPENDITURE AGGREGATE
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_federal_expenditures_by_state_year
WHERE
       state_abbreviation = 'WA'
    OR state_abbreviation IS NULL
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 6. SSA
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_washington_ssa_summary
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 7. MEDICARE
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_medicare_expenditures_by_state_year
WHERE
       state_abbreviation = 'WA'
    OR state_abbreviation IS NULL
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 8. MEDICAID
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_washington_medicaid_expenditures
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 9. CHIP
-- --------------------------------------------------------------------------------

SELECT *
FROM reporting.v_washington_chip_expenditures
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 10. FEDERAL WAGES
-- --------------------------------------------------------------------------------

SELECT *
FROM analysis.v_wa_federal_wage_allocation
ORDER BY 1;


-- --------------------------------------------------------------------------------
-- 11. VA GDX STATE CONTROL
-- --------------------------------------------------------------------------------

SELECT *
FROM va.v_washington_county_gdx_control_total
ORDER BY 1;