CREATE SCHEMA IF NOT EXISTS reporting;


CREATE OR REPLACE VIEW reporting.v_federal_receipts_by_state_year AS
SELECT
    sc.fiscal_year,
    sc.state_id,
    sc.state_name,
    fa.federal_agency_id,
    fa.agency_code,
    fa.agency_name,
    fp.federal_program_id,
    fp.program_code,
    fp.program_name,
    sc.tax_category,
    sc.gross_collections_thousands,
    sc.gross_collections_thousands * 1000::BIGINT
        AS gross_collections_dollars,
    sc.source_file
FROM irs.state_collections sc
JOIN reference.federal_agency fa
    ON fa.agency_code = 'IRS'
LEFT JOIN reference.federal_program fp
    ON fp.program_code =
        CASE sc.tax_category
            WHEN 'Total'
                THEN 'IRS_GROSS_COLLECTIONS'
            WHEN 'Business income taxes'
                THEN 'IRS_BUSINESS_INCOME'
            WHEN 'Individual income tax, employment taxes, and estate and trust income tax'
                THEN 'IRS_INDIVIDUAL_INCOME'
            WHEN 'Estate tax'
                THEN 'IRS_ESTATE_GIFT'
            WHEN 'Gift tax'
                THEN 'IRS_ESTATE_GIFT'
            WHEN 'Excise taxes'
                THEN 'IRS_EXCISE'
            ELSE NULL
        END;


CREATE OR REPLACE VIEW reporting.v_federal_expenditures_by_county_year AS
SELECT
    bp.report_year,
    bp.state_id,
    bp.county_id,
    bp.state_name,
    bp.county_name,
    fa.federal_agency_id,
    fa.agency_code,
    fa.agency_name,
    fp.federal_program_id,
    fp.program_code,
    fp.program_name,
    bp.ssa_benefit_type_id,
    sbt.benefit_type_code,
    bp.benefit_type,
    bp.beneficiary_count,
    bp.monthly_benefits_thousands,
    bp.annual_benefits_thousands,
    bp.annual_benefits_thousands * 1000::BIGINT
        AS annualized_benefits_dollars,
    bp.source_file,
    bp.source_table
FROM ssa.benefit_payments bp
JOIN reference.federal_agency fa
    ON fa.agency_code = bp.agency_code
LEFT JOIN reference.federal_program fp
    ON fp.federal_program_id = bp.federal_program_id
LEFT JOIN reference.ssa_benefit_type sbt
    ON sbt.ssa_benefit_type_id = bp.ssa_benefit_type_id;


CREATE OR REPLACE VIEW reporting.v_federal_expenditures_by_state_year AS
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
    SUM(beneficiary_count) AS beneficiary_count,
    SUM(monthly_benefits_thousands) AS monthly_benefits_thousands,
    SUM(annual_benefits_thousands) AS annualized_benefits_thousands,
    SUM(annualized_benefits_dollars) AS annualized_benefits_dollars
FROM reporting.v_federal_expenditures_by_county_year
WHERE benefit_type <> 'Total'
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


CREATE OR REPLACE VIEW reporting.v_washington_revenue_summary AS
SELECT
    fiscal_year,
    gross_collections_thousands,
    gross_collections_dollars
FROM reporting.v_federal_receipts_by_state_year
WHERE state_name = 'Washington'
  AND tax_category = 'Total'
ORDER BY fiscal_year;


CREATE OR REPLACE VIEW reporting.v_washington_ssa_summary AS
SELECT
    report_year,
    program_code,
    program_name,
    beneficiary_count,
    annualized_benefits_thousands,
    annualized_benefits_dollars
FROM reporting.v_federal_expenditures_by_state_year
WHERE state_name = 'Washington'
  AND agency_code = 'SSA'
ORDER BY
    report_year,
    program_code;