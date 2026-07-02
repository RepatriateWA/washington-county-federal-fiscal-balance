CREATE SCHEMA IF NOT EXISTS irs;

CREATE TABLE IF NOT EXISTS irs.agi_bracket (
    agi_bracket_id SERIAL PRIMARY KEY,
    agi_bracket_code INTEGER UNIQUE NOT NULL,
    agi_bracket_label TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS irs.county_income_tax (
    county_income_tax_id BIGSERIAL PRIMARY KEY,
    tax_year INTEGER NOT NULL,
    county_id BIGINT REFERENCES reference.county_registry(county_id),
    state_id BIGINT REFERENCES reference.state_registry(state_id),
    county_fips TEXT NOT NULL,
    full_fips TEXT,
    agi_bracket_id INTEGER REFERENCES irs.agi_bracket(agi_bracket_id),
    agi_bracket_label TEXT NOT NULL,

    number_of_returns BIGINT,
    number_of_single_returns BIGINT,
    number_of_joint_returns BIGINT,
    number_of_head_of_household_returns BIGINT,
    adjusted_gross_income BIGINT,
    total_income_amount BIGINT,
    salaries_and_wages_amount BIGINT,
    taxable_interest_amount BIGINT,
    ordinary_dividends_amount BIGINT,
    qualified_dividends_amount BIGINT,
    business_net_income_amount BIGINT,
    net_capital_gain_amount BIGINT,
    taxable_pensions_amount BIGINT,
    taxable_social_security_amount BIGINT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (tax_year, county_fips, agi_bracket_label)
);

CREATE TABLE IF NOT EXISTS irs.import_log (
    import_log_id BIGSERIAL PRIMARY KEY,
    tax_year INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    rows_loaded INTEGER NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);