-- =============================================================
-- Washington County Federal Fiscal Balance Research Platform
-- Migration: 003_reference_tables.sql
-- Version: 0.2.0
--
-- Purpose:
-- Create geographic reference tables.
-- =============================================================

BEGIN;

CREATE TABLE reference.state_registry (
    state_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state_fips CHAR(2) NOT NULL UNIQUE,
    state_abbreviation CHAR(2) NOT NULL UNIQUE,
    state_name VARCHAR(100) NOT NULL UNIQUE,
    census_region VARCHAR(50),
    census_division VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reference.county_registry (
    county_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state_id BIGINT NOT NULL,
    county_fips CHAR(3) NOT NULL,
    full_fips CHAR(5) NOT NULL UNIQUE,
    county_name VARCHAR(100) NOT NULL,
    county_type VARCHAR(30),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_county_state
        FOREIGN KEY (state_id)
        REFERENCES reference.state_registry(state_id)
);

COMMIT;