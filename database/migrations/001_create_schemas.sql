-- =============================================================
-- Washington County Federal Fiscal Balance Research Platform
-- Migration: 001_create_schemas.sql
-- Version: 0.2.0
--
-- Purpose:
-- Create the PostgreSQL schemas used throughout the project.
-- =============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA IF NOT EXISTS reference;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS reporting;

COMMENT ON SCHEMA metadata IS
'Project metadata, ETL logs, variables, source catalog';

COMMENT ON SCHEMA reference IS
'Reference data such as states, counties and lookup tables';

COMMENT ON SCHEMA raw IS
'Raw imported data exactly as received from source agencies';

COMMENT ON SCHEMA staging IS
'Validated and standardized data';

COMMENT ON SCHEMA analytics IS
'Fiscal balance calculations and derived tables';

COMMENT ON SCHEMA reporting IS
'Views and export-ready reporting objects';

COMMIT;