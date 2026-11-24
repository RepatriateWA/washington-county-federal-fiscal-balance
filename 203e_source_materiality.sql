BEGIN TRANSACTION READ ONLY;

\echo '=== REPORT 1: FEDERAL WAGE ALLOCATIONS ==='

SELECT
    fiscal_year,
    ROUND(allocated_wa_civilian_wage_dollars, 2)
        AS civilian_dollars,
    ROUND(allocated_wa_military_wage_dollars, 2)
        AS military_dollars,
    ROUND(allocated_wa_total_federal_wage_dollars, 2)
        AS combined_dollars,
    combined_allocation_confidence,
    civilian_value_status,
    military_value_status
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo '=== REPORT 2: VA GDX EXPENDITURE CLASSES ==='

SELECT
    fiscal_year,
    expenditure_class,
    source_unit,
    COUNT(*) AS source_rows,
    ROUND(SUM(expenditure_amount), 2)
        AS summed_expenditure_dollars
FROM va.gdx_county_expenditure
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year, expenditure_class, source_unit
ORDER BY fiscal_year, expenditure_class, source_unit;

\echo '=== REPORT 3: ASSISTANCE OBLIGATIONS ==='

SELECT
    fiscal_year,
    transaction_count,
    ROUND(total_obligation, 2) AS total_obligation,
    ROUND(covid_obligation, 2) AS covid_obligation,
    ROUND(covid_excluded_obligation, 2)
        AS covid_excluded_obligation,
    ROUND(wa_county_obligation, 2)
        AS wa_county_obligation,
    ROUND(wa_unspecified_obligation, 2)
        AS wa_unspecified_obligation,
    ROUND(geography_conflict_obligation, 2)
        AS geography_conflict_obligation
FROM analysis.v_statewide_assistance_by_year
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo '=== REPORT 4: PROCUREMENT GEOGRAPHY ==='

SELECT
    fiscal_year,
    geographic_attribution_class,
    transaction_count,
    ROUND(federal_action_obligation, 2)
        AS net_obligations,
    ROUND(covid_obligation, 2) AS covid_obligations,
    ROUND(covid_excluded_obligation, 2)
        AS covid_excluded_obligations
FROM analysis.v_wa_obligation_reconciliation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year, geographic_attribution_class;

COMMIT;