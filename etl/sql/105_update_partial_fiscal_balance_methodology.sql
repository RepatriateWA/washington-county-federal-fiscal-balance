BEGIN;

CREATE OR REPLACE VIEW reporting.v_washington_partial_fiscal_balance AS

WITH receipts AS (
    SELECT
        v_washington_revenue_summary.fiscal_year AS report_year,
        v_washington_revenue_summary.gross_collections_dollars
    FROM reporting.v_washington_revenue_summary
),

tracked_expenditures AS (
    SELECT
        v_washington_tracked_expenditures.report_year,
        SUM(
            v_washington_tracked_expenditures.expenditure_dollars
        ) AS tracked_expenditures_dollars
    FROM reporting.v_washington_tracked_expenditures
    GROUP BY
        v_washington_tracked_expenditures.report_year
)

SELECT
    r.report_year,
    r.gross_collections_dollars,

    COALESCE(
        e.tracked_expenditures_dollars,
        0::NUMERIC
    ) AS tracked_expenditures_dollars,

    r.gross_collections_dollars::NUMERIC
        - COALESCE(
            e.tracked_expenditures_dollars,
            0::NUMERIC
        ) AS partial_fiscal_balance_dollars,

    (
        'Partial balance: IRS gross collections minus annualized '
        || 'SSA OASDI benefits, Original Medicare actual payments, '
        || 'and CMS Medicaid federal Total Net Expenditures. '
        || 'CHIP, VA, USAspending, Medicare Advantage, and other '
        || 'federal expenditures are not yet included.'
    )::TEXT AS methodology_note

FROM receipts AS r

LEFT JOIN tracked_expenditures AS e
    ON e.report_year = r.report_year

ORDER BY
    r.report_year;

COMMENT ON VIEW reporting.v_washington_partial_fiscal_balance IS
    'Partial Washington federal fiscal balance calculated as IRS gross '
    'collections minus tracked federal expenditures: SSA OASDI annualized '
    'benefits, Original Medicare actual payments, and Medicaid federal '
    'Total Net Expenditures for 2015 through 2024.';

COMMIT;