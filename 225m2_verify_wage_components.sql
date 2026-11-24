\set ON_ERROR_STOP on

BEGIN READ ONLY;

SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars
        AS civilian_wages_usd,
    allocated_wa_military_wage_dollars
        AS military_wages_usd,
    allocated_wa_total_federal_wage_dollars
        AS combined_wages_usd,
    (
        allocated_wa_civilian_wage_dollars
        + allocated_wa_military_wage_dollars
        - allocated_wa_total_federal_wage_dollars
    ) AS component_reconciliation_difference,
    combined_allocation_confidence
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

ROLLBACK;
