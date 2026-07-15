CREATE TABLE IF NOT EXISTS cms_raw.medicare_geographic_variation (

    raw_row_id BIGSERIAL PRIMARY KEY,

    report_year INTEGER,

    geography_level TEXT,

    geography_name TEXT,

    geography_code TEXT,

    age_group TEXT,

    total_beneficiaries NUMERIC,

    original_medicare_beneficiaries NUMERIC,

    medicare_advantage_beneficiaries NUMERIC,

    medicare_advantage_rate NUMERIC,

    total_medicare_payments NUMERIC,

    standardized_medicare_payments NUMERIC,

    source_file TEXT,

    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);