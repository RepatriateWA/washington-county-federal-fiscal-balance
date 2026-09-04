-- ============================================================================
-- ETL-160 — Federal Wage Allocation Certification
-- ============================================================================
--
-- Purpose
-- -------
-- Create the authoritative WCFFBP Washington federal-wage allocation view
-- for FFY2015-FFY2024 by combining the independently validated civilian and
-- military wage allocation components.
--
-- Accounting control:
--
--     OMB government-wide federal budget object-class obligations
--
-- Civilian allocation:
--
--     OPM FedScope
--     ANALYSIS-158-v1
--
-- Military allocation:
--
--     BEA SAINC7N line 2002
--     ANALYSIS-157-v1
--
-- Important boundary:
--
--     OMB determines the federal fiscal accounting amount.
--     OPM and BEA provide geographic allocation evidence only.
--
--     Direct OPM/BEA wage-dollar series are not additive federal inflows.
--
-- ============================================================================

BEGIN;


CREATE SCHEMA IF NOT EXISTS analysis;


-- ============================================================================
-- Combined federal wage allocation view
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_wa_federal_wage_allocation AS

SELECT
    c.fiscal_year,

    -- ------------------------------------------------------------------------
    -- OMB national accounting controls
    -- ------------------------------------------------------------------------

    c.omb_nonmilitary_wage_obligations_dollars
        AS omb_civilian_wage_control_dollars,

    m.omb_military_wage_control_dollars,

    (
        c.omb_nonmilitary_wage_obligations_dollars
        + m.omb_military_wage_control_dollars
    )::NUMERIC(24,2)
        AS omb_total_federal_wage_control_dollars,


    -- ------------------------------------------------------------------------
    -- Washington civilian allocation
    -- ------------------------------------------------------------------------

    c.wa_known_salary_share
        AS civilian_wa_allocation_share,

    (
        c.wa_known_salary_share * 100
    )::NUMERIC(18,6)
        AS civilian_wa_allocation_share_percent,

    c.allocated_wa_civilian_wage_dollars,


    -- ------------------------------------------------------------------------
    -- Washington military allocation
    -- ------------------------------------------------------------------------

    m.bea_wa_share
        AS military_wa_allocation_share,

    m.bea_wa_share_percent
        AS military_wa_allocation_share_percent,

    m.allocated_wa_military_wage_dollars,


    -- ------------------------------------------------------------------------
    -- Combined Washington federal wage allocation
    -- ------------------------------------------------------------------------

    (
        c.allocated_wa_civilian_wage_dollars
        + m.allocated_wa_military_wage_dollars
    )::NUMERIC(24,2)
        AS allocated_wa_total_federal_wage_dollars,


    -- ------------------------------------------------------------------------
    -- Allocation evidence / confidence
    -- ------------------------------------------------------------------------

    c.allocation_confidence
        AS civilian_allocation_confidence,

    'HIGH'
        AS military_allocation_confidence,

    CASE
        WHEN c.allocation_confidence = 'MEDIUM_HIGH'
            THEN 'MEDIUM_HIGH'
        ELSE 'MEDIUM'
    END
        AS combined_allocation_confidence,


    -- ------------------------------------------------------------------------
    -- Civilian suppression diagnostics
    -- ------------------------------------------------------------------------

    c.workstat1_employment
        AS civilian_opm_workstat1_employment,

    c.workstat1_blank_salary_employment
        AS civilian_opm_blank_salary_employment,

    c.workstat1_blank_salary_employment_pct
        AS civilian_opm_blank_salary_employment_pct,

    c.us_type_known_salary_mass_dollars
        AS civilian_opm_us_known_salary_mass_dollars,

    c.wa_known_salary_mass_dollars
        AS civilian_opm_wa_known_salary_mass_dollars,


    -- ------------------------------------------------------------------------
    -- Military reconciliation diagnostics
    -- ------------------------------------------------------------------------

    m.bea_us_military_wages_dollars,

    m.bea_wa_military_wages_dollars,

    m.allocation_minus_bea_direct_dollars
        AS military_allocation_minus_bea_direct_dollars,

    m.allocation_to_bea_ratio
        AS military_allocation_to_bea_ratio,


    -- ------------------------------------------------------------------------
    -- Provenance
    -- ------------------------------------------------------------------------

    c.budget_vintage
        AS civilian_omb_budget_vintage,

    m.budget_vintage
        AS military_omb_budget_vintage,

    c.value_status
        AS civilian_value_status,

    m.value_status
        AS military_value_status,

    c.methodology_version
        AS civilian_methodology_version,

    'ANALYSIS-157-v1'
        AS military_methodology_version,

    'ANALYSIS-160-v1'
        AS certification_methodology_version

FROM opm.v_omb_civilian_wage_allocation c

JOIN bea.v_omb_military_wage_allocation m
    ON m.fiscal_year = c.fiscal_year;


-- ============================================================================
-- Validation
-- ============================================================================

DO $$
DECLARE
    v_rows INTEGER;
    v_bad_years INTEGER;
    v_bad_omb_controls INTEGER;
    v_bad_allocations INTEGER;
    v_bad_arithmetic INTEGER;
    v_bad_methodology INTEGER;
    v_bad_military_reconciliation INTEGER;
BEGIN

    -- ------------------------------------------------------------------------
    -- Exactly ten fiscal years must be certified.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_rows
    FROM analysis.v_wa_federal_wage_allocation
    WHERE fiscal_year BETWEEN 2015 AND 2024;


    IF v_rows <> 10 THEN
        RAISE EXCEPTION
            'ETL-160 validation failed: expected 10 federal wage rows; found %.',
            v_rows;
    END IF;


    -- ------------------------------------------------------------------------
    -- Every fiscal year must occur exactly once.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_years
    FROM (
        SELECT fiscal_year
        FROM analysis.v_wa_federal_wage_allocation
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        HAVING COUNT(*) <> 1
    ) AS bad;


    IF v_bad_years <> 0 THEN
        RAISE EXCEPTION
            'ETL-160 validation failed: % fiscal year(s) do not occur exactly once.',
            v_bad_years;
    END IF;


    -- ------------------------------------------------------------------------
    -- OMB accounting controls must be positive.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_omb_controls
    FROM analysis.v_wa_federal_wage_allocation
    WHERE omb_civilian_wage_control_dollars IS NULL
       OR omb_civilian_wage_control_dollars <= 0
       OR omb_military_wage_control_dollars IS NULL
       OR omb_military_wage_control_dollars <= 0
       OR omb_total_federal_wage_control_dollars IS NULL
       OR omb_total_federal_wage_control_dollars <= 0;


    IF v_bad_omb_controls <> 0 THEN
        RAISE EXCEPTION
            'ETL-160 validation failed: % year(s) contain invalid OMB wage controls.',
            v_bad_omb_controls;
    END IF;


    -- ------------------------------------------------------------------------
    -- Washington allocations must be positive.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_allocations
    FROM analysis.v_wa_federal_wage_allocation
    WHERE allocated_wa_civilian_wage_dollars IS NULL
       OR allocated_wa_civilian_wage_dollars <= 0
       OR allocated_wa_military_wage_dollars IS NULL
       OR allocated_wa_military_wage_dollars <= 0
       OR allocated_wa_total_federal_wage_dollars IS NULL
       OR allocated_wa_total_federal_wage_dollars <= 0;


    IF v_bad_allocations <> 0 THEN
        RAISE EXCEPTION
            'ETL-160 validation failed: % year(s) contain invalid Washington wage allocations.',
            v_bad_allocations;
    END IF;


    -- ------------------------------------------------------------------------
    -- Combined arithmetic must be exact.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_arithmetic
    FROM analysis.v_wa_federal_wage_allocation
    WHERE
        omb_total_federal_wage_control_dollars
        <>
        (
            omb_civilian_wage_control_dollars
            + omb_military_wage_control_dollars
        )
       OR
        allocated_wa_total_federal_wage_dollars
        <>
        (
            allocated_wa_civilian_wage_dollars
            + allocated_wa_military_wage_dollars
        );


    IF v_bad_arithmetic <> 0 THEN
        RAISE EXCEPTION
            'ETL-160 validation failed: % year(s) fail combined wage arithmetic.',
            v_bad_arithmetic;
    END IF;


    -- ------------------------------------------------------------------------
    -- Source-policy methodology identifiers must be preserved.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_methodology
    FROM analysis.v_wa_federal_wage_allocation
    WHERE civilian_methodology_version <> 'ANALYSIS-158-v1'
       OR military_methodology_version <> 'ANALYSIS-157-v1'
       OR certification_methodology_version <> 'ANALYSIS-160-v1';


    IF v_bad_methodology <> 0 THEN
        RAISE EXCEPTION
            'ETL-160 validation failed: % year(s) have unexpected methodology identifiers.',
            v_bad_methodology;
    END IF;


    -- ------------------------------------------------------------------------
    -- Military geographic reconciliation inherited from ETL-156 must remain
    -- exact.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_military_reconciliation
    FROM bea.v_omb_military_wage_allocation
    WHERE fiscal_year BETWEEN 2015 AND 2024
      AND (
            state_dc_reconciliation_difference_dollars <> 0
         OR region_reconciliation_difference_dollars <> 0
         OR state_dc_row_count <> 51
         OR region_row_count <> 8
         OR us_row_count <> 1
         OR wa_row_count <> 1
      );


    IF v_bad_military_reconciliation <> 0 THEN
        RAISE EXCEPTION
            'ETL-160 validation failed: % year(s) fail inherited military geographic reconciliation.',
            v_bad_military_reconciliation;
    END IF;


    RAISE NOTICE
        'ETL-160 validation PASSED: Washington federal civilian + military wage allocation certified for FFY2015-FFY2024.';

END
$$;


COMMIT;