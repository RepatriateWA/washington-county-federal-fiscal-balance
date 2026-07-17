BEGIN;

CREATE OR REPLACE VIEW reporting.v_washington_tracked_expenditures AS

/*
 * SSA OASDI
 */
SELECT
    v_washington_ssa_summary.report_year,
    'SSA'::TEXT AS agency_code,
    v_washington_ssa_summary.program_code,
    v_washington_ssa_summary.program_name,
    v_washington_ssa_summary.annualized_benefits_dollars
        AS expenditure_dollars,
    'Annualized December OASDI benefit amount'::TEXT
        AS measure_note
FROM reporting.v_washington_ssa_summary

UNION ALL

/*
 * Original Medicare
 */
SELECT
    v_medicare_expenditures_by_state_year.report_year,
    v_medicare_expenditures_by_state_year.agency_code,
    v_medicare_expenditures_by_state_year.program_code,
    v_medicare_expenditures_by_state_year.program_name,
    v_medicare_expenditures_by_state_year
        .actual_medicare_payments_dollars
        AS expenditure_dollars,
    (
        'Actual Original Medicare payments; '
        || 'Medicare Advantage payments not fully represented'
    )::TEXT AS measure_note
FROM reporting.v_medicare_expenditures_by_state_year
WHERE
    v_medicare_expenditures_by_state_year.state_name::TEXT
        = 'Washington'::TEXT

UNION ALL

/*
 * Medicaid
 */
SELECT
    v_washington_medicaid_expenditures.fiscal_year
        AS report_year,
    'CMS'::TEXT AS agency_code,
    'MEDICAID'::TEXT AS program_code,
    'Medicaid'::TEXT AS program_name,
    v_washington_medicaid_expenditures
        .federal_expenditure_amount
        AS expenditure_dollars,
    (
        'Actual federal Medicaid expenditure from CMS MBES '
        || 'Total Net Expenditures control total; federal fiscal year; '
        || 'overlapping service-level rows excluded.'
    )::TEXT AS measure_note
FROM reporting.v_washington_medicaid_expenditures
WHERE
    v_washington_medicaid_expenditures
        .is_additive_to_fiscal_balance = TRUE;

COMMENT ON VIEW reporting.v_washington_tracked_expenditures IS
    'Washington federal expenditures currently tracked in the warehouse: '
    'SSA OASDI annualized benefits, Original Medicare actual payments, '
    'and Medicaid actual federal expenditures from the CMS MBES '
    'Total Net Expenditures control total.';

COMMIT;