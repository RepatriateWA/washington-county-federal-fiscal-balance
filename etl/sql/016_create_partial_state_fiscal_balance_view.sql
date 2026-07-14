CREATE OR REPLACE VIEW reporting.v_washington_partial_fiscal_balance AS
WITH receipts AS (
    SELECT
        fiscal_year AS report_year,
        gross_collections_dollars
    FROM reporting.v_washington_revenue_summary
),
ssa_expenditures AS (
    SELECT
        report_year,
        SUM(annualized_benefits_dollars) AS ssa_annualized_expenditures_dollars
    FROM reporting.v_washington_ssa_summary
    GROUP BY report_year
)
SELECT
    r.report_year,
    r.gross_collections_dollars,
    COALESCE(s.ssa_annualized_expenditures_dollars, 0)
        AS ssa_annualized_expenditures_dollars,
    r.gross_collections_dollars
        - COALESCE(s.ssa_annualized_expenditures_dollars, 0)
        AS partial_fiscal_balance_dollars,
    'Partial balance: IRS gross collections minus annualized SSA OASDI benefits only'
        AS methodology_note
FROM receipts r
LEFT JOIN ssa_expenditures s
    ON s.report_year = r.report_year
ORDER BY r.report_year;