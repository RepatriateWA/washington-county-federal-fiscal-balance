-- ETL-202A.3
-- Annual source coverage inventory, FY/CY 2015-2024
-- READ ONLY: no production writes

\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH observations AS (
    SELECT 'IRS_STATE_COLLECTIONS'::text AS source_name,
           'FFY'::text AS period_basis,
           fiscal_year AS year_value
    FROM irs.state_collections

    UNION ALL
    SELECT 'IRS_COUNTY_INCOME_TAX', 'TY', tax_year
    FROM irs.county_income_tax

    UNION ALL
    SELECT 'SSA_BENEFITS', 'REPORT_YEAR', report_year
    FROM ssa.benefit_payments

    UNION ALL
    SELECT 'VA_GDX', 'FFY', fiscal_year
    FROM va.gdx_county_expenditure

    UNION ALL
    SELECT 'MEDICARE_CORE_COUNTY', 'CY', calendar_year
    FROM cms.medicare_core_county_year

    UNION ALL
    SELECT 'MEDICARE_GEOGRAPHIC', 'REPORT_YEAR', report_year
    FROM cms.medicare_geographic_payments

    UNION ALL
    SELECT 'MEDICAID_MBES', 'FFY', fiscal_year
    FROM cms_raw.medicaid_mbes

    UNION ALL
    SELECT 'CHIP_CMS21', 'FFY', fiscal_year
    FROM chip.cms21_expenditure

    UNION ALL
    SELECT 'BEA_COMPENSATION', 'CY', calendar_year
    FROM bea.compensation_observation

    UNION ALL
    SELECT 'OMB_OBJECT_CLASS', 'FFY', target_fiscal_year
    FROM omb.object_class_observation

    UNION ALL
    SELECT 'PROCUREMENT', 'FFY', fiscal_year
    FROM procurement.award_transaction

    UNION ALL
    SELECT 'ASSISTANCE', 'FFY', action_date_fiscal_year
    FROM assistance.award_transaction
),
source_registry AS (
    SELECT DISTINCT source_name, period_basis
    FROM observations
),
years AS (
    SELECT generate_series(2015, 2024) AS year_value
)
SELECT
    s.source_name,
    s.period_basis,
    y.year_value,
    COUNT(o.year_value) AS observation_rows,
    CASE
        WHEN COUNT(o.year_value) > 0 THEN 'PRESENT'
        ELSE 'NO_ROWS'
    END AS coverage_status
FROM source_registry s
CROSS JOIN years y
LEFT JOIN observations o
  ON o.source_name = s.source_name
 AND o.period_basis = s.period_basis
 AND o.year_value = y.year_value
GROUP BY s.source_name, s.period_basis, y.year_value
ORDER BY s.source_name, y.year_value;

ROLLBACK;
