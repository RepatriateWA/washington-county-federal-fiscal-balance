\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT
    report_year,
    gross_collections_dollars,
    tracked_expenditures_dollars,
    partial_fiscal_balance_dollars,
    methodology_note
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2020 AND 2024
ORDER BY report_year;

ROLLBACK;