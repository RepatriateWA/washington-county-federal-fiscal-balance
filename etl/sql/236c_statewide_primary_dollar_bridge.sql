-- ETL-236C
-- Seven-year statewide primary dollar bridge
-- READ ONLY; observational amounts, not ledger authorizations

BEGIN TRANSACTION READ ONLY;

WITH years AS (
    SELECT generate_series(2018, 2024)::integer AS yr
),
wa_state AS (
    SELECT DISTINCT state_id
    FROM reporting.v_washington_medicaid_expenditures
    WHERE state_abbreviation = 'WA'
      AND fiscal_year BETWEEN 2018 AND 2024
),
observations AS (

    SELECT fiscal_year AS yr,
           'IRS_GROSS_COLLECTIONS'::text AS family,
           'IRS_FISCAL_YEAR'::text AS basis,
           COUNT(*)::bigint AS source_rows,
           SUM(gross_collections_dollars)::numeric AS dollars,
           ''::text AS qualification
    FROM reporting.v_washington_revenue_summary
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year

    UNION ALL

    SELECT report_year,
           'SSA_' || COALESCE(program_code, 'UNKNOWN'),
           'ANNUALIZED_BENEFITS',
           COUNT(*)::bigint,
           SUM(annualized_benefits_dollars)::numeric,
           MAX(COALESCE(program_name, ''))
    FROM reporting.v_washington_ssa_summary
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year, program_code

    UNION ALL

    SELECT fiscal_year,
           'MEDICAID',
           'FEDERAL_EXPENDITURE',
           COUNT(*)::bigint,
           SUM(federal_expenditure_amount)::numeric,
           'Review additive flags and source time basis'
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
      AND state_abbreviation = 'WA'
    GROUP BY fiscal_year

    UNION ALL

    SELECT fiscal_year,
           'CHIP',
           'FEDERAL_EXPENDITURE',
           COUNT(*)::bigint,
           SUM(federal_expenditure_amount)::numeric,
           'Review additive flags'
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
      AND state_abbreviation = 'WA'
    GROUP BY fiscal_year

    UNION ALL

    SELECT fiscal_year,
           'VA_GDX',
           'VA_FISCAL_YEAR',
           COUNT(*)::bigint,
           SUM(va_gdx_expenditure_amount)::numeric,
           'County control total; confirm no statewide aggregate row'
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year

    UNION ALL

    SELECT fiscal_year,
           'FEDERAL_CIVILIAN_WAGES',
           'OMB_ALLOCATED_OBLIGATIONS',
           COUNT(*)::bigint,
           SUM(allocated_wa_civilian_wage_dollars)::numeric,
           MAX(COALESCE(allocation_confidence, ''))
    FROM opm.v_omb_civilian_wage_allocation
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year

    UNION ALL

    SELECT fiscal_year,
           'FEDERAL_MILITARY_WAGES',
           'OMB_ALLOCATED_OBLIGATIONS',
           COUNT(*)::bigint,
           SUM(allocated_wa_military_wage_dollars)::numeric,
           MAX(COALESCE(value_status, ''))
    FROM bea.v_omb_military_wage_allocation
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year

    UNION ALL

    SELECT calendar_year,
           'MEDICARE_FFS_AB',
           'CALENDAR_YEAR',
           COUNT(*)::bigint,
           SUM(original_medicare_actual_ffs_dollars)::numeric,
           MAX(COALESCE(combined_period_status, ''))
    FROM cms.medicare_core_state_year
    WHERE calendar_year BETWEEN 2018 AND 2024
      AND state_id IN (SELECT state_id FROM wa_state)
    GROUP BY calendar_year

    UNION ALL

    SELECT calendar_year,
           'MEDICARE_PART_C',
           'CALENDAR_YEAR',
           COUNT(*)::bigint,
           SUM(partc_reconstructed_dollars)::numeric,
           MAX(
               COALESCE(partc_year_completeness, '') ||
               ' / months=' ||
               COALESCE(partc_months_processed::text, 'NULL')
           )
    FROM cms.medicare_core_state_year
    WHERE calendar_year BETWEEN 2018 AND 2024
      AND state_id IN (SELECT state_id FROM wa_state)
    GROUP BY calendar_year

    UNION ALL

    SELECT calendar_year,
           'MEDICARE_PART_D',
           'CALENDAR_YEAR_INCOMPLETE',
           COUNT(*)::bigint,
           SUM(partd_reconstructed_dollars)::numeric,
           MAX(COALESCE(partd_coverage_status, ''))
    FROM cms.medicare_core_state_year
    WHERE calendar_year BETWEEN 2018 AND 2024
      AND state_id IN (SELECT state_id FROM wa_state)
    GROUP BY calendar_year
)
SELECT
    y.yr AS year,
    families.family,
    COALESCE(o.basis, 'NO_OBSERVATION') AS measure_basis,
    COALESCE(o.source_rows, 0) AS source_rows,
    o.dollars,
    o.qualification
FROM years y
CROSS JOIN (
    SELECT DISTINCT family FROM observations
) families
LEFT JOIN observations o
    ON o.yr = y.yr
   AND o.family = families.family
ORDER BY y.yr, o.family;

ROLLBACK;