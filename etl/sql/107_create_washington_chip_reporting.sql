-- Migration 107
-- Add Washington CHIP reporting and integrate CHIP into the tracked-expenditures view.

BEGIN;

CREATE SCHEMA IF NOT EXISTS reporting;

CREATE OR REPLACE VIEW reporting.v_washington_chip_expenditures AS
WITH additive_control_totals AS (
    SELECT
        c.fiscal_year,
        c.state_fips,
        c.state_abbreviation,
        c.state_name,
        c.worksheet_type,
        c.federal_share,
        c.total_computable,
        c.state_share,
        c.source_workbook,
        c.source_sheet,
        c.source_row
    FROM chip.v_cms21_control_totals AS c
    WHERE c.is_additive_expenditure = TRUE
      AND c.is_financing_adjustment = FALSE
      AND c.state_abbreviation = 'WA'
),
annual_totals AS (
    SELECT
        fiscal_year,
        state_fips,
        state_abbreviation,
        state_name,
        SUM(total_computable)::bigint AS total_computable,
        SUM(federal_share)::bigint AS federal_expenditure_amount,
        SUM(state_share)::bigint AS state_share,
        COUNT(*)::integer AS additive_control_total_count,
        STRING_AGG(worksheet_type, ', ' ORDER BY worksheet_type) AS included_worksheet_types,
        STRING_AGG(DISTINCT source_workbook, '; ' ORDER BY source_workbook) AS source_workbooks
    FROM additive_control_totals
    GROUP BY fiscal_year, state_fips, state_abbreviation, state_name
)
SELECT
    a.fiscal_year,
    sr.state_id,
    a.state_fips,
    a.state_abbreviation,
    a.state_name,
    fp.federal_program_id,
    a.total_computable,
    a.federal_expenditure_amount,
    a.state_share,
    a.additive_control_total_count,
    a.included_worksheet_types,
    'STATE'::text AS geographic_level,
    'Centers for Medicare & Medicaid Services'::text AS federal_agency_name,
    'CHIP'::text AS federal_program_name,
    'ACTUAL_EXPENDITURE'::text AS amount_method,
    TRUE AS is_additive_to_fiscal_balance,
    'Federal fiscal year; CHIP and MCHIP additive control totals; MCHIP 20% financing adjustment excluded.'::text AS measure_note,
    a.source_workbooks
FROM annual_totals AS a
JOIN reference.state_registry AS sr
  ON sr.state_fips = a.state_fips
LEFT JOIN reference.federal_program AS fp
  ON UPPER(fp.program_code) = 'CHIP';

COMMENT ON VIEW reporting.v_washington_chip_expenditures IS
'Annual Washington CHIP federal expenditures from CMS-21 additive control totals. Includes CHIP and MCHIP; excludes the MCHIP 20% financing adjustment.';

CREATE OR REPLACE VIEW reporting.v_washington_tracked_expenditures AS
SELECT
    s.report_year,
    'SSA'::text AS agency_code,
    s.program_code,
    s.program_name,
    s.annualized_benefits_dollars AS expenditure_dollars,
    'Annualized December OASDI benefit amount'::text AS measure_note
FROM reporting.v_washington_ssa_summary AS s

UNION ALL

SELECT
    m.report_year,
    m.agency_code,
    m.program_code,
    m.program_name,
    m.actual_medicare_payments_dollars AS expenditure_dollars,
    ('Actual Original Medicare payments; ' || 'Medicare Advantage payments not fully represented')::text AS measure_note
FROM reporting.v_medicare_expenditures_by_state_year AS m
WHERE m.state_name::text = 'Washington'::text

UNION ALL

SELECT
    md.fiscal_year AS report_year,
    'CMS'::text AS agency_code,
    'MEDICAID'::text AS program_code,
    'Medicaid'::text AS program_name,
    md.federal_expenditure_amount AS expenditure_dollars,
    ('Actual federal Medicaid expenditure from CMS MBES ' ||
     'Total Net Expenditures control total; federal fiscal year; ' ||
     'overlapping service-level rows excluded.')::text AS measure_note
FROM reporting.v_washington_medicaid_expenditures AS md
WHERE md.is_additive_to_fiscal_balance = TRUE

UNION ALL

SELECT
    c.fiscal_year AS report_year,
    'CMS'::text AS agency_code,
    'CHIP'::text AS program_code,
    'CHIP'::text AS program_name,
    c.federal_expenditure_amount AS expenditure_dollars,
    c.measure_note
FROM reporting.v_washington_chip_expenditures AS c
WHERE c.is_additive_to_fiscal_balance = TRUE;

COMMENT ON VIEW reporting.v_washington_tracked_expenditures IS
'Washington annual tracked federal expenditures for SSA OASDI, Medicare, Medicaid, and CHIP. Year bases and measurement limitations are documented in measure_note.';

COMMIT;