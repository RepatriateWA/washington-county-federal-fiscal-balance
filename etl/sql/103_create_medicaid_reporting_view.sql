BEGIN;

CREATE SCHEMA IF NOT EXISTS reporting;

DROP VIEW IF EXISTS reporting.v_washington_medicaid_expenditures;

CREATE VIEW reporting.v_washington_medicaid_expenditures AS
SELECT
    mct.fiscal_year,
    sr.state_id,
    sr.state_fips,
    sr.state_abbreviation,
    sr.state_name,

    fp.federal_program_id,

    /*
     * Retain the program dimension's canonical identifying fields where
     * available through the foreign-key relationship.
     */
    mct.total_computable,
    mct.federal_share AS federal_expenditure_amount,
    mct.federal_share_medicaid,
    mct.federal_share_arra,
    mct.federal_share_covid,
    mct.state_share,

    mct.control_total_label,
    mct.expenditure_time_basis,

    'STATE'::TEXT AS geographic_level,

    'Centers for Medicare & Medicaid Services'::TEXT
        AS federal_agency_name,

    'Medicaid'::TEXT AS federal_program_name,

    'ACTUAL_EXPENDITURE'::TEXT AS amount_method,

    TRUE AS is_additive_to_fiscal_balance,

    mct.source_file,
    mct.source_worksheet,
    mct.source_row_number,
    mct.loaded_at

FROM cms.medicaid_state_control_total AS mct

INNER JOIN reference.state_registry AS sr
    ON sr.state_id = mct.state_id

INNER JOIN reference.federal_program AS fp
    ON fp.federal_program_id = mct.federal_program_id

WHERE sr.state_abbreviation = 'WA';

COMMENT ON VIEW reporting.v_washington_medicaid_expenditures IS
    'Washington Medicaid federal expenditures from the official CMS '
    'MBES Total Net Expenditures control row. This view is additive to '
    'fiscal-balance reporting. Overlapping service-level rows are excluded.';

COMMIT;