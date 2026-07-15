DROP VIEW IF EXISTS reporting.v_washington_partial_fiscal_balance;

CREATE VIEW reporting.v_washington_partial_fiscal_balance AS
WITH receipts AS (
    SELECT
        fiscal_year AS report_year,
        gross_collections_dollars
    FROM reporting.v_washington_revenue_summary
),
tracked_expenditures AS (
    SELECT
        report_year,
        SUM(expenditure_dollars) AS tracked_expenditures_dollars
    FROM reporting.v_washington_tracked_expenditures
    GROUP BY report_year
)
SELECT
    r.report_year,
    r.gross_collections_dollars,
    COALESCE(e.tracked_expenditures_dollars, 0)
        AS tracked_expenditures_dollars,
    r.gross_collections_dollars
        - COALESCE(e.tracked_expenditures_dollars, 0)
        AS partial_fiscal_balance_dollars,
    'Partial balance: IRS gross collections minus annualized SSA OASDI benefits and Original Medicare actual payments. Medicaid, CHIP, VA, USAspending, Medicare Advantage, and other federal expenditures are not yet included.'
        AS methodology_note
FROM receipts r
LEFT JOIN tracked_expenditures e
    ON e.report_year = r.report_year
ORDER BY r.report_year;