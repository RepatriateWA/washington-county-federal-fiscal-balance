CREATE OR REPLACE VIEW reporting.v_medicare_expenditures_by_county_year AS
SELECT
    mgp.report_year,
    mgp.state_id,
    mgp.county_id,
    sr.state_name,
    cr.county_name,
    mgp.federal_agency_id,
    fa.agency_code,
    fa.agency_name,
    mgp.federal_program_id,
    fp.program_code,
    fp.program_name,
    mgp.total_beneficiaries,
    mgp.original_medicare_beneficiaries,
    mgp.medicare_advantage_beneficiaries,
    mgp.medicare_advantage_rate,
    mgp.total_medicare_payments_dollars,
    mgp.standardized_medicare_payments_dollars,
    mgp.source_file,
    mgp.methodology_note
FROM cms.medicare_geographic_payments mgp
JOIN reference.state_registry sr
    ON sr.state_id = mgp.state_id
JOIN reference.county_registry cr
    ON cr.county_id = mgp.county_id
JOIN reference.federal_agency fa
    ON fa.federal_agency_id = mgp.federal_agency_id
JOIN reference.federal_program fp
    ON fp.federal_program_id = mgp.federal_program_id;


CREATE OR REPLACE VIEW reporting.v_medicare_expenditures_by_state_year AS
SELECT
    report_year,
    state_id,
    state_name,
    federal_agency_id,
    agency_code,
    agency_name,
    federal_program_id,
    program_code,
    program_name,
    SUM(total_beneficiaries) AS total_beneficiaries,
    SUM(original_medicare_beneficiaries)
        AS original_medicare_beneficiaries,
    SUM(medicare_advantage_beneficiaries)
        AS medicare_advantage_beneficiaries,
    SUM(total_medicare_payments_dollars)
        AS actual_medicare_payments_dollars,
    SUM(standardized_medicare_payments_dollars)
        AS standardized_medicare_payments_dollars
FROM reporting.v_medicare_expenditures_by_county_year
GROUP BY
    report_year,
    state_id,
    state_name,
    federal_agency_id,
    agency_code,
    agency_name,
    federal_program_id,
    program_code,
    program_name;


CREATE OR REPLACE VIEW reporting.v_washington_tracked_expenditures AS
SELECT
    report_year,
    'SSA' AS agency_code,
    program_code,
    program_name,
    annualized_benefits_dollars AS expenditure_dollars,
    'Annualized December OASDI benefit amount' AS measure_note
FROM reporting.v_washington_ssa_summary

UNION ALL

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    actual_medicare_payments_dollars AS expenditure_dollars,
    'Actual Original Medicare payments; Medicare Advantage payments not fully represented'
        AS measure_note
FROM reporting.v_medicare_expenditures_by_state_year
WHERE state_name = 'Washington';