CREATE INDEX IF NOT EXISTS idx_state_registry_fips
    ON reference.state_registry (state_fips);

CREATE INDEX IF NOT EXISTS idx_state_registry_abbreviation
    ON reference.state_registry (state_abbreviation);

CREATE INDEX IF NOT EXISTS idx_county_registry_state_id
    ON reference.county_registry (state_id);

CREATE INDEX IF NOT EXISTS idx_county_registry_county_fips
    ON reference.county_registry (county_fips);

CREATE INDEX IF NOT EXISTS idx_county_registry_full_fips
    ON reference.county_registry (full_fips);

CREATE INDEX IF NOT EXISTS idx_irs_county_income_tax_year
    ON irs.county_income_tax (tax_year);

CREATE INDEX IF NOT EXISTS idx_irs_county_income_county_fips
    ON irs.county_income_tax (county_fips);

CREATE INDEX IF NOT EXISTS idx_irs_county_income_year_county
    ON irs.county_income_tax (tax_year, county_fips);

CREATE INDEX IF NOT EXISTS idx_irs_county_income_year_county_bracket
    ON irs.county_income_tax (tax_year, county_fips, agi_bracket_label);