-- =============================================================
-- Washington County Federal Fiscal Balance Research Platform
-- Migration: 002_metadata_tables.sql
-- Version: 0.2.0
--
-- Purpose:
-- Create metadata tables.
-- =============================================================

BEGIN;

CREATE TABLE metadata.dataset_release (
    release_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version VARCHAR(20) NOT NULL,
    release_date DATE NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE metadata.source_manifest (
    source_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name VARCHAR(200) NOT NULL,
    agency VARCHAR(200),
    source_url TEXT,
    citation TEXT,
    update_frequency VARCHAR(50),
    first_year INTEGER,
    last_year INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE metadata.variable_registry (
    variable_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    variable_name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(200),
    description TEXT,
    units VARCHAR(50),
    data_type VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE metadata.etl_run_log (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    process_name VARCHAR(200) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(25),
    records_processed INTEGER,
    notes TEXT
);

COMMIT;