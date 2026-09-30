BEGIN;

CREATE SCHEMA IF NOT EXISTS cms;

CREATE TABLE IF NOT EXISTS cms.medicare_core_state_year (
    medicare_core_state_year_id BIGSERIAL PRIMARY KEY,

    calendar_year INTEGER NOT NULL
        CHECK (calendar_year BETWEEN 2015 AND 2024),

    state_id BIGINT NOT NULL
        REFERENCES reference.state_registry(state_id),

    original_medicare_actual_ffs_dollars NUMERIC NOT NULL,
    partc_reconstructed_dollars NUMERIC NOT NULL,
    partd_reconstructed_dollars NUMERIC NOT NULL,
    core_medicare_sum_dollars NUMERIC NOT NULL,

    original_medicare_county_rows INTEGER NOT NULL,
    original_medicare_beneficiaries BIGINT NOT NULL,

    partc_months_processed INTEGER NOT NULL,
    partc_year_completeness TEXT NOT NULL,

    partc_reconstruction_coverage_pct NUMERIC NOT NULL,
    partc_accounting_coverage_pct NUMERIC NOT NULL,

    partd_dollar_source_field TEXT NOT NULL,
    partd_coverage_status TEXT NOT NULL,

    combined_period_status TEXT NOT NULL,
    timing_basis_status TEXT NOT NULL,

    ledger_status TEXT NOT NULL,
    methodology_version TEXT NOT NULL,

    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,

    loaded_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_medicare_core_state_year
        UNIQUE (calendar_year, state_id),

    CONSTRAINT ck_medicare_core_state_year_counties
        CHECK (original_medicare_county_rows = 39),

    CONSTRAINT ck_medicare_core_state_year_months
        CHECK (partc_months_processed BETWEEN 1 AND 12),

    CONSTRAINT ck_medicare_core_state_methodology
        CHECK (
            methodology_version =
            'CMS-MEDICARE-ACCOUNTING-INTEGRATION-PROFILE-v0.1'
        ),

    CONSTRAINT ck_medicare_core_state_ledger_status
        CHECK (
            ledger_status = 'NOT_YET_AUTHORIZED'
        )
);

CREATE INDEX IF NOT EXISTS
    ix_medicare_core_state_year_state_id
ON cms.medicare_core_state_year (state_id);

COMMENT ON TABLE cms.medicare_core_state_year IS
'Exact database promotion of the certified Washington Medicare state-level '
'accounting integration profile CMS-MEDICARE-ACCOUNTING-INTEGRATION-PROFILE-v0.1. '
'Original Medicare/FFS, Part C, Part D, and core Medicare values are preserved '
'from the certification artifact. ETL-170 performs no CY-to-FFY conversion, '
'imputation, extrapolation, scaling, or federal-inflow ledger authorization.';

COMMENT ON COLUMN cms.medicare_core_state_year.core_medicare_sum_dollars IS
'Certified state-level Original Medicare/FFS + reconstructed Part C + '
'reconstructed Part D amount from the accounting-integration artifact. '
'This value is not derived by summing cms.medicare_core_county_year.';

COMMENT ON COLUMN cms.medicare_core_state_year.ledger_status IS
'Status preserved from the source certification artifact. ETL-170 does not '
'authorize final federal-inflow ledger inclusion.';

COMMIT;