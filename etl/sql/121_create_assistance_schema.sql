BEGIN;

CREATE SCHEMA IF NOT EXISTS assistance;

COMMENT ON SCHEMA assistance IS
    'Normalized USAspending federal financial assistance awards and transactions.';


-- -------------------------------------------------------------------------
-- Canonical assistance award
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assistance.award (
    assistance_award_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    assistance_award_unique_key TEXT NOT NULL,
    award_id_fain TEXT,
    award_id_uri TEXT,
    sai_number TEXT,

    recipient_id BIGINT,

    awarding_agency_id BIGINT,
    awarding_subagency_id BIGINT,
    funding_agency_id BIGINT,
    funding_subagency_id BIGINT,

    assistance_listing_id BIGINT,
    assistance_type_id BIGINT,
    funding_opportunity_id BIGINT,

    period_of_performance_start_date DATE,
    period_of_performance_current_end_date DATE,

    total_obligated_amount NUMERIC(20, 2),
    total_outlayed_amount NUMERIC(20, 2),
    total_non_federal_funding_amount NUMERIC(20, 2),
    total_face_value_of_loan NUMERIC(20, 2),
    total_loan_subsidy_cost NUMERIC(20, 2),

    canonical_recipient_name TEXT,
    canonical_award_description TEXT,

    first_action_date DATE,
    last_action_date DATE,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_assistance_award_unique_key
        UNIQUE (assistance_award_unique_key),

    CONSTRAINT ck_assistance_award_identifier_present
        CHECK (
            award_id_fain IS NOT NULL
            OR award_id_uri IS NOT NULL
        ),

    CONSTRAINT ck_assistance_award_action_dates
        CHECK (
            first_action_date IS NULL
            OR last_action_date IS NULL
            OR first_action_date <= last_action_date
        )
);

COMMENT ON TABLE assistance.award IS
    'One canonical row per USAspending assistance award.';

COMMENT ON COLUMN assistance.award.assistance_award_unique_key IS
    'Authoritative source award identity supplied by USAspending.';

COMMENT ON COLUMN assistance.award.award_id_fain IS
    'Federal Award Identification Number when applicable.';

COMMENT ON COLUMN assistance.award.award_id_uri IS
    'USAspending URI-style assistance award identifier when applicable.';

COMMENT ON COLUMN assistance.award.sai_number IS
    'System for Award Management or state application identifier source value; not an award identity key.';


-- -------------------------------------------------------------------------
-- Assistance award transaction
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assistance.award_transaction (
    assistance_transaction_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    load_batch_id BIGINT NOT NULL,
    source_row_number BIGINT NOT NULL,

    assistance_transaction_unique_key TEXT NOT NULL,
    assistance_award_id BIGINT NOT NULL,

    modification_number TEXT,

    action_date DATE,
    action_date_fiscal_year INTEGER,

    federal_action_obligation NUMERIC(20, 2),

    total_obligated_amount NUMERIC(20, 2),
    total_outlayed_amount_for_overall_award NUMERIC(20, 2),

    indirect_cost_federal_share_amount NUMERIC(20, 2),
    non_federal_funding_amount NUMERIC(20, 2),
    total_non_federal_funding_amount NUMERIC(20, 2),

    face_value_of_loan NUMERIC(20, 2),
    original_loan_subsidy_cost NUMERIC(20, 2),
    total_face_value_of_loan NUMERIC(20, 2),
    total_loan_subsidy_cost NUMERIC(20, 2),

    generated_pragmatic_obligations NUMERIC(20, 2),

    covid_overall_award_obligation NUMERIC(20, 2),
    covid_overall_award_outlay NUMERIC(20, 2),

    iija_overall_award_obligation NUMERIC(20, 2),
    iija_overall_award_outlay NUMERIC(20, 2),

    disaster_emergency_fund_codes_raw TEXT,

    recipient_id BIGINT,
    place_of_performance_id BIGINT,

    awarding_agency_id BIGINT,
    awarding_subagency_id BIGINT,
    funding_agency_id BIGINT,
    funding_subagency_id BIGINT,

    assistance_listing_id BIGINT,
    assistance_type_id BIGINT,
    funding_opportunity_id BIGINT,

    transaction_description TEXT,
    action_type_code TEXT,
    record_type_code TEXT,
    correction_delete_indicator_code TEXT,

    usaspending_permalink TEXT,
    initial_report_date DATE,
    last_modified_date DATE,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_assistance_transaction_unique_key
        UNIQUE (assistance_transaction_unique_key),

    CONSTRAINT uq_assistance_transaction_batch_row
        UNIQUE (load_batch_id, source_row_number),

    CONSTRAINT fk_assistance_transaction_award
        FOREIGN KEY (assistance_award_id)
        REFERENCES assistance.award (
            assistance_award_id
        ),

    CONSTRAINT ck_assistance_transaction_fiscal_year
        CHECK (
            action_date_fiscal_year IS NULL
            OR action_date_fiscal_year BETWEEN 1900 AND 2200
        )
);

COMMENT ON TABLE assistance.award_transaction IS
    'One normalized row per USAspending assistance prime transaction.';

COMMENT ON COLUMN assistance.award_transaction.federal_action_obligation IS
    'Transaction-level obligation used for annual fiscal-flow measurement.';

COMMENT ON COLUMN assistance.award_transaction.covid_overall_award_obligation IS
    'Cumulative overall-award COVID obligation supplied by USAspending; used for classification support and reconciliation, not annual transaction-flow measurement.';

COMMENT ON COLUMN assistance.award_transaction.iija_overall_award_obligation IS
    'Cumulative overall-award IIJA obligation supplied by USAspending; used for classification support and reconciliation, not annual transaction-flow measurement.';

COMMENT ON COLUMN assistance.award_transaction.disaster_emergency_fund_codes_raw IS
    'Unmodified combined DEFC source value. Parsed relationships will be stored separately.';


-- -------------------------------------------------------------------------
-- Indexes
-- -------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_assistance_award_fain
    ON assistance.award (award_id_fain)
    WHERE award_id_fain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_award_uri
    ON assistance.award (award_id_uri)
    WHERE award_id_uri IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_award_recipient
    ON assistance.award (recipient_id)
    WHERE recipient_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_batch
    ON assistance.award_transaction (load_batch_id);

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_award
    ON assistance.award_transaction (assistance_award_id);

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_action_date
    ON assistance.award_transaction (action_date);

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_fiscal_year
    ON assistance.award_transaction (action_date_fiscal_year);

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_recipient
    ON assistance.award_transaction (recipient_id)
    WHERE recipient_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_place
    ON assistance.award_transaction (place_of_performance_id)
    WHERE place_of_performance_id IS NOT NULL;

COMMIT;