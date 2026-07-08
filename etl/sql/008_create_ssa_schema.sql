CREATE SCHEMA IF NOT EXISTS ssa;

CREATE TABLE IF NOT EXISTS ssa.county_oasdi_benefits (
    county_oasdi_benefits_id BIGSERIAL PRIMARY KEY,

    report_year INTEGER NOT NULL,

    state_id BIGINT REFERENCES reference.state_registry(state_id),
    county_id BIGINT REFERENCES reference.county_registry(county_id),

    state_name TEXT NOT NULL,
    county_name TEXT NOT NULL,

    beneficiary_count BIGINT,
    total_monthly_benefits_thousands BIGINT,
    total_annual_benefits_thousands BIGINT,

    source_file TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (report_year, state_id, county_id)
);

CREATE INDEX IF NOT EXISTS idx_ssa_oasdi_year
    ON ssa.county_oasdi_benefits(report_year);

CREATE INDEX IF NOT EXISTS idx_ssa_oasdi_county
    ON ssa.county_oasdi_benefits(county_id);