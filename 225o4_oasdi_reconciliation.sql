BEGIN READ ONLY;

WITH registry_controls (
    report_year,
    registry_amount
) AS (
    VALUES
        (2018, 22964784000::numeric),
        (2019, 24211632000::numeric),
        (2020, 25423704000::numeric),
        (2021, 27643404000::numeric),
        (2022, 30924420000::numeric),
        (2023, 32990628000::numeric),
        (2024, 35082120000::numeric)
),
reporting_totals AS (
    SELECT
        report_year,
        COUNT(*) AS reporting_rows,
        SUM(annualized_benefits_dollars) AS reporting_amount
    FROM reporting.v_washington_ssa_summary
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year
),
published_totals AS (
    SELECT
        report_year,
        COUNT(*) AS county_total_rows,
        SUM(monthly_benefits_thousands::numeric * 12000)
            AS published_annualized_amount
    FROM ssa.benefit_payments
    WHERE report_year BETWEEN 2018 AND 2024
      AND UPPER(TRIM(benefit_type)) = 'TOTAL'
      AND state_name = 'Washington'
    GROUP BY report_year
)
SELECT
    r.report_year,
    v.reporting_rows,
    p.county_total_rows,
    r.registry_amount,
    v.reporting_amount,
    p.published_annualized_amount,
    v.reporting_amount - r.registry_amount
        AS registry_difference,
    v.reporting_amount - p.published_annualized_amount
        AS source_rounding_difference,
    CASE
        WHEN v.reporting_rows = 3
         AND p.county_total_rows = 39
         AND v.reporting_amount = r.registry_amount
        THEN 'PASS'
        ELSE 'REVIEW'
    END AS verification_status
FROM registry_controls r
LEFT JOIN reporting_totals v
    ON v.report_year = r.report_year
LEFT JOIN published_totals p
    ON p.report_year = r.report_year
ORDER BY r.report_year;

COMMIT;
