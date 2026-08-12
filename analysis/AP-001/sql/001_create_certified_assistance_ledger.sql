BEGIN;

-- ============================================================================
-- AP-001A — Certified Assistance Analytical Ledger
-- File: analysis/AP-001/sql/001_create_certified_assistance_ledger.sql
--
-- Contract:
--   * One row per assistance.award_transaction.
--   * No Washington filtering.
--   * No aggregation of financial amounts.
--   * DEFC many-to-many relationships are collapsed to transaction-level
--     analytical attributes so financial rows are never multiplied.
--   * federal_action_obligation is the transaction-level fiscal-flow measure.
--   * Overall-award COVID/IIJA amounts are retained for reconciliation only.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS analysis;

COMMENT ON SCHEMA analysis IS
    'Certified analytical views derived from normalized warehouse data. '
    'Analysis objects do not modify ETL-owned source tables.';

CREATE OR REPLACE VIEW analysis.v_certified_assistance_ledger AS

WITH defc_rollup AS (
    SELECT
        atd.assistance_transaction_id,

        ARRAY_AGG(
            DISTINCT efc.defc_code
            ORDER BY efc.defc_code
        ) AS defc_codes,

        ARRAY_AGG(
            DISTINCT efc.funding_family
            ORDER BY efc.funding_family
        ) AS funding_families,

        STRING_AGG(
            DISTINCT efc.defc_code || ': ' || efc.official_description,
            ' | '
            ORDER BY efc.defc_code || ': ' || efc.official_description
        ) AS defc_descriptions,

        BOOL_OR(COALESCE(efc.extraordinary_flag, FALSE))
            AS is_extraordinary,

        BOOL_OR(efc.covid_flag)
            AS is_covid,

        BOOL_OR(efc.iija_flag)
            AS is_iija,

        COUNT(DISTINCT efc.extraordinary_funding_code_id)
            AS defc_code_count

    FROM assistance.award_transaction_defc atd
    JOIN reference.extraordinary_funding_code efc
      ON efc.extraordinary_funding_code_id =
         atd.extraordinary_funding_code_id
    GROUP BY
        atd.assistance_transaction_id
),

place_rollup AS (
    SELECT
        p.place_id,

        p.country_code,
        p.country_name,
        p.state_code,
        p.state_name,
        p.state_fips,
        p.county_name,
        p.county_fips,
        p.city_name,
        p.zip4,
        p.congressional_district_current,
        p.congressional_district_original,

        p.place_identity_key,
        p.place_identity_type,
        p.place_source_condition,

        sr.state_id,
        sr.state_abbreviation AS reference_state_abbreviation,
        sr.state_name AS reference_state_name,

        cr.county_id,
        cr.full_fips AS county_full_fips,
        cr.county_name AS reference_county_name

    FROM procurement.place p

    LEFT JOIN reference.state_registry sr
      ON sr.state_fips = p.state_fips

    LEFT JOIN reference.county_registry cr
      ON cr.state_id = sr.state_id
     AND cr.county_fips = p.county_fips
)

SELECT
    -- ------------------------------------------------------------------------
    -- Transaction identity and provenance
    -- ------------------------------------------------------------------------
    t.assistance_transaction_id,
    t.assistance_transaction_unique_key,
    t.load_batch_id,
    t.source_row_number,

    t.action_date,
    t.action_date_fiscal_year,
    t.modification_number,

    -- ------------------------------------------------------------------------
    -- Certified transaction-level fiscal measure
    -- ------------------------------------------------------------------------
    t.federal_action_obligation,

    -- Additional source financial fields retained without reinterpretation
    t.total_obligated_amount,
    t.total_outlayed_amount_for_overall_award,
    t.indirect_cost_federal_share_amount,
    t.non_federal_funding_amount,
    t.total_non_federal_funding_amount,
    t.face_value_of_loan,
    t.original_loan_subsidy_cost,
    t.total_face_value_of_loan,
    t.total_loan_subsidy_cost,
    t.generated_pragmatic_obligations,

    -- Overall-award supplemental values:
    -- classification/reconciliation support, not annual transaction flow
    t.covid_overall_award_obligation,
    t.covid_overall_award_outlay,
    t.iija_overall_award_obligation,
    t.iija_overall_award_outlay,
    t.disaster_emergency_fund_codes_raw,

    -- ------------------------------------------------------------------------
    -- Canonical award
    -- ------------------------------------------------------------------------
    a.assistance_award_id,
    a.assistance_award_unique_key,
    a.award_id_fain,
    a.award_id_uri,
    a.sai_number,
    a.canonical_award_description,
    a.period_of_performance_start_date,
    a.period_of_performance_current_end_date,
    a.first_action_date AS award_first_action_date,
    a.last_action_date AS award_last_action_date,

    -- ------------------------------------------------------------------------
    -- Transaction recipient
    -- ------------------------------------------------------------------------
    r.recipient_id,
    r.recipient_identity_key,
    r.recipient_identity_type,
    r.recipient_source_condition,
    r.recipient_uei,
    r.recipient_duns,
    r.recipient_name,
    r.recipient_name_normalized,
    r.recipient_parent_uei,
    r.recipient_parent_name,
    r.recipient_type_code,
    r.business_categories,

    -- ------------------------------------------------------------------------
    -- Awarding agency
    -- ------------------------------------------------------------------------
    aa.agency_id AS awarding_agency_id,
    aa.agency_code AS awarding_agency_code,
    aa.agency_name AS awarding_agency_name,
    aa.agency_level AS awarding_agency_level,

    asa.agency_id AS awarding_subagency_id,
    asa.agency_code AS awarding_subagency_code,
    asa.agency_name AS awarding_subagency_name,

    -- ------------------------------------------------------------------------
    -- Funding agency
    -- ------------------------------------------------------------------------
    fa.agency_id AS funding_agency_id,
    fa.agency_code AS funding_agency_code,
    fa.agency_name AS funding_agency_name,
    fa.agency_level AS funding_agency_level,

    fsa.agency_id AS funding_subagency_id,
    fsa.agency_code AS funding_subagency_code,
    fsa.agency_name AS funding_subagency_name,

    -- ------------------------------------------------------------------------
    -- Assistance classification
    -- ------------------------------------------------------------------------
    al.assistance_listing_id,
    al.cfda_number,
    al.cfda_title,

    aty.assistance_type_id,
    aty.assistance_type_code,
    aty.assistance_type_description,

    -- ------------------------------------------------------------------------
    -- Place of performance
    -- ------------------------------------------------------------------------
    pr.place_id AS place_of_performance_id,
    pr.place_identity_key,
    pr.place_identity_type,
    pr.place_source_condition,

    pr.country_code AS performance_country_code,
    pr.country_name AS performance_country_name,
    pr.state_code AS performance_state_code,
    pr.state_name AS performance_state_name,
    pr.state_fips AS performance_state_fips,

    pr.state_id AS reference_state_id,
    pr.reference_state_abbreviation,
    pr.reference_state_name,

    pr.county_name AS performance_county_name,
    pr.county_fips AS performance_county_fips,
    pr.county_id AS reference_county_id,
    pr.county_full_fips,
    pr.reference_county_name,

    pr.city_name AS performance_city_name,
    pr.zip4 AS performance_zip4,
    pr.congressional_district_current,
    pr.congressional_district_original,

    -- ------------------------------------------------------------------------
    -- Extraordinary funding / DEFC rollup
    -- ------------------------------------------------------------------------
    COALESCE(d.defc_code_count, 0) AS defc_code_count,
    d.defc_codes,
    d.funding_families,
    d.defc_descriptions,

    COALESCE(d.is_extraordinary, FALSE) AS is_extraordinary,
    COALESCE(d.is_covid, FALSE) AS is_covid,
    COALESCE(d.is_iija, FALSE) AS is_iija,

    CASE
        WHEN COALESCE(d.is_covid, FALSE) THEN 'COVID'
        WHEN COALESCE(d.is_iija, FALSE) THEN 'IIJA'
        WHEN COALESCE(d.is_extraordinary, FALSE) THEN 'OTHER_EXTRAORDINARY'
        ELSE 'NOT_EXTRAORDINARY'
    END AS extraordinary_summary_class,

    -- ------------------------------------------------------------------------
    -- Transaction descriptors / source traceability
    -- ------------------------------------------------------------------------
    t.transaction_description,
    t.action_type_code,
    t.record_type_code,
    t.correction_delete_indicator_code,
    t.usaspending_permalink,
    t.initial_report_date,
    t.last_modified_date

FROM assistance.award_transaction t

JOIN assistance.award a
  ON a.assistance_award_id = t.assistance_award_id

LEFT JOIN procurement.recipient r
  ON r.recipient_id = t.recipient_id

LEFT JOIN procurement.agency aa
  ON aa.agency_id = t.awarding_agency_id

LEFT JOIN procurement.agency asa
  ON asa.agency_id = t.awarding_subagency_id

LEFT JOIN procurement.agency fa
  ON fa.agency_id = t.funding_agency_id

LEFT JOIN procurement.agency fsa
  ON fsa.agency_id = t.funding_subagency_id

LEFT JOIN assistance.assistance_listing al
  ON al.assistance_listing_id = t.assistance_listing_id

LEFT JOIN assistance.assistance_type aty
  ON aty.assistance_type_id = t.assistance_type_id

LEFT JOIN place_rollup pr
  ON pr.place_id = t.place_of_performance_id

LEFT JOIN defc_rollup d
  ON d.assistance_transaction_id = t.assistance_transaction_id
;

COMMENT ON VIEW analysis.v_certified_assistance_ledger IS
    'AP-001A certified transaction-level analytical ledger. One row per '
    'normalized USAspending Assistance transaction. DEFC relationships are '
    'rolled up to prevent row multiplication. No Washington filtering or '
    'financial aggregation is applied.';

COMMIT;