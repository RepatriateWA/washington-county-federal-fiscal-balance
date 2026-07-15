CREATE SCHEMA IF NOT EXISTS cms;

CREATE TABLE IF NOT EXISTS cms.medicare_geographic_payments (
    medicare_geographic_payment_id BIGSERIAL PRIMARY KEY,

    report_year INTEGER NOT NULL,

    state_id BIGINT NOT NULL
        REFERENCES reference.state_registry(state_id),

    county_id BIGINT NOT NULL
        REFERENCES reference.county_registry(county_id),

    federal_agency_id BIGINT NOT NULL
        REFERENCES reference.federal_agency(federal_agency_id),

    federal_program_id BIGINT NOT NULL
        REFERENCES reference.federal_program(federal_program_id),

    geography_code TEXT NOT NULL,
    age_group TEXT NOT NULL DEFAULT 'All',

    total_beneficiaries BIGINT,
    original_medicare_beneficiaries BIGINT,
    medicare_advantage_beneficiaries BIGINT,
    medicare_advantage_rate NUMERIC,

    total_medicare_payments_dollars NUMERIC,
    standardized_medicare_payments_dollars NUMERIC,

    source_file TEXT NOT NULL,
    methodology_note TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        report_year,
        county_id,
        age_group
    )
);

CREATE INDEX IF NOT EXISTS idx_cms_medicare_year
    ON cms.medicare_geographic_payments(report_year);

CREATE INDEX IF NOT EXISTS idx_cms_medicare_county
    ON cms.medicare_geographic_payments(county_id);

CREATE INDEX IF NOT EXISTS idx_cms_medicare_program
    ON cms.medicare_geographic_payments(federal_program_id);