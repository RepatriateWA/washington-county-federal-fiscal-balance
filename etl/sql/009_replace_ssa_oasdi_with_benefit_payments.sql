CREATE SCHEMA IF NOT EXISTS ssa;

DROP TABLE IF EXISTS ssa.county_oasdi_benefits;

CREATE TABLE IF NOT EXISTS ssa.benefit_payments (
    benefit_payment_id BIGSERIAL PRIMARY KEY,

    report_year INTEGER NOT NULL,

    state_id BIGINT
        REFERENCES reference.state_registry(state_id),

    county_id BIGINT
        REFERENCES reference.county_registry(county_id),

    state_name TEXT NOT NULL,
    county_name TEXT NOT NULL,

    agency_code TEXT NOT NULL DEFAULT 'SSA',
    benefit_type TEXT NOT NULL,

    beneficiary_count BIGINT,

    monthly_benefits_thousands BIGINT,
    annual_benefits_thousands BIGINT,

    source_file TEXT NOT NULL,
    source_table TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        report_year,
        state_id,
        county_id,
        benefit_type
    )
);

CREATE INDEX IF NOT EXISTS idx_ssa_benefit_payments_year
    ON ssa.benefit_payments(report_year);

CREATE INDEX IF NOT EXISTS idx_ssa_benefit_payments_county
    ON ssa.benefit_payments(county_id);

CREATE INDEX IF NOT EXISTS idx_ssa_benefit_payments_type
    ON ssa.benefit_payments(benefit_type);