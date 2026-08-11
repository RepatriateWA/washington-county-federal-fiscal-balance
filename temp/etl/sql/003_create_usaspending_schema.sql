-- 003_create_usaspending_schema.sql
-- COVID-001 / USAspending Assistance Pipeline
-- Creates durable source-preserving tables for assistance transactions.

CREATE SCHEMA IF NOT EXISTS usaspending;

CREATE TABLE IF NOT EXISTS usaspending.load_history (
    load_id BIGSERIAL PRIMARY KEY,
    source_archive TEXT NOT NULL,
    source_member TEXT NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    fiscal_year INTEGER,
    row_count_loaded BIGINT NOT NULL DEFAULT 0,
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    status TEXT NOT NULL DEFAULT 'started',
    error_message TEXT,
    UNIQUE (source_sha256, source_member)
);

CREATE TABLE IF NOT EXISTS usaspending.assistance_transactions (
    transaction_id BIGSERIAL PRIMARY KEY,

    -- Provenance
    load_id BIGINT NOT NULL REFERENCES usaspending.load_history(load_id),
    source_archive TEXT NOT NULL,
    source_member TEXT NOT NULL,
    source_row_number BIGINT NOT NULL,

    -- Stable USAspending identifiers
    assistance_transaction_unique_key TEXT,
    assistance_award_unique_key TEXT,
    award_id_fain TEXT,
    modification_number TEXT,
    award_id_uri TEXT,

    -- Financial fields
    federal_action_obligation NUMERIC,
    total_obligated_amount NUMERIC,
    total_outlayed_amount_for_overall_award NUMERIC,
    generated_pragmatic_obligations NUMERIC,

    -- COVID / emergency fields
    disaster_emergency_fund_codes_for_overall_award TEXT,
    outlayed_amount_from_covid19_supplementals_for_overall_award NUMERIC,
    obligated_amount_from_covid19_supplementals_for_overall_award NUMERIC,

    -- Dates
    action_date DATE,
    action_date_fiscal_year INTEGER,

    -- Agency
    awarding_agency_code TEXT,
    awarding_agency_name TEXT,
    awarding_sub_agency_code TEXT,
    awarding_sub_agency_name TEXT,
    funding_agency_code TEXT,
    funding_agency_name TEXT,

    -- Recipient
    recipient_uei TEXT,
    recipient_duns TEXT,
    recipient_name TEXT,
    recipient_name_raw TEXT,
    recipient_city_name TEXT,
    recipient_county_fips_code TEXT,
    recipient_county_name TEXT,
    recipient_state_fips_code TEXT,
    recipient_state_code TEXT,
    recipient_state_name TEXT,
    recipient_zip_code TEXT,

    -- Place of performance
    primary_place_of_performance_country_code TEXT,
    primary_place_of_performance_country_name TEXT,
    primary_place_of_performance_city_name TEXT,
    place_of_performance_county_fips_code TEXT,
    primary_place_of_performance_county_name TEXT,
    place_of_performance_state_fips_code TEXT,
    primary_place_of_performance_state_name TEXT,
    primary_place_of_performance_zip_4 TEXT,

    -- Program
    cfda_number TEXT,
    cfda_title TEXT,
    assistance_type_code TEXT,
    assistance_type_description TEXT,
    transaction_description TEXT,
    prime_award_base_transaction_description TEXT,

    -- Record metadata
    action_type_code TEXT,
    action_type_description TEXT,
    correction_delete_indicator_code TEXT,
    correction_delete_indicator_description TEXT,
    record_type_code TEXT,
    record_type_description TEXT,
    usaspending_permalink TEXT,
    initial_report_date DATE,
    last_modified_date TIMESTAMP WITHOUT TIME ZONE,

    -- Derived but transparent COVID flags
    covid_confirmed BOOLEAN GENERATED ALWAYS AS (
        COALESCE(obligated_amount_from_covid19_supplementals_for_overall_award, 0) <> 0
        OR COALESCE(outlayed_amount_from_covid19_supplementals_for_overall_award, 0) <> 0
    ) STORED,

    covid_basis TEXT GENERATED ALWAYS AS (
        CASE
            WHEN COALESCE(obligated_amount_from_covid19_supplementals_for_overall_award, 0) <> 0
              OR COALESCE(outlayed_amount_from_covid19_supplementals_for_overall_award, 0) <> 0
                THEN 'USAspending COVID-19 supplemental amount'
            WHEN NULLIF(TRIM(disaster_emergency_fund_codes_for_overall_award), '') IS NOT NULL
                THEN 'DEFC present; supplemental amount zero or null'
            ELSE 'No COVID supplemental amount identified'
        END
    ) STORED,

    loaded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (load_id, source_row_number)
);

CREATE INDEX IF NOT EXISTS idx_usa_assistance_tx_unique_key
    ON usaspending.assistance_transactions (assistance_transaction_unique_key);

CREATE INDEX IF NOT EXISTS idx_usa_assistance_award_unique_key
    ON usaspending.assistance_transactions (assistance_award_unique_key);

CREATE INDEX IF NOT EXISTS idx_usa_assistance_fy
    ON usaspending.assistance_transactions (action_date_fiscal_year);

CREATE INDEX IF NOT EXISTS idx_usa_assistance_recipient_state
    ON usaspending.assistance_transactions (recipient_state_code);

CREATE INDEX IF NOT EXISTS idx_usa_assistance_pop_state_fips
    ON usaspending.assistance_transactions (place_of_performance_state_fips_code);

CREATE INDEX IF NOT EXISTS idx_usa_assistance_covid
    ON usaspending.assistance_transactions (covid_confirmed);
