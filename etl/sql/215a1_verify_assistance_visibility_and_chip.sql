
\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-215A1 - HISTORICAL ASSISTANCE VISIBILITY'

SELECT
    action_date_fiscal_year AS fiscal_year,
    load_batch_id,
    COALESCE(reference_state_abbreviation, '[NULL]')
        AS reference_state,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
GROUP BY
    action_date_fiscal_year,
    load_batch_id,
    reference_state_abbreviation
ORDER BY 1, 2, 3;

\echo ''
\echo 'HISTORICAL SIX-PROGRAM CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE reference_state_abbreviation = 'WA'
    ) AS rows_explicitly_marked_wa,
    COUNT(*) FILTER (
        WHERE reference_state_abbreviation IS NULL
    ) AS rows_with_null_state
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
  AND TRIM(cfda_number) IN (
      '10.555', '84.010', '84.027',
      '84.063', '93.558', '93.600'
  )
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo 'CHIP INCLUDED IN TRACKED EXPENDITURES'

SELECT
    report_year,
    COUNT(*) FILTER (
        WHERE program_code = 'CHIP'
    ) AS chip_component_rows,
    ROUND(SUM(expenditure_dollars) FILTER (
        WHERE program_code = 'CHIP'
    )::numeric, 2) AS chip_in_tracked_total,
    ROUND(SUM(expenditure_dollars)::numeric, 2)
        AS all_tracked_expenditures
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY report_year
ORDER BY report_year;

ROLLBACK;

\echo 'ETL-215A1 COMPLETE - READ ONLY'
