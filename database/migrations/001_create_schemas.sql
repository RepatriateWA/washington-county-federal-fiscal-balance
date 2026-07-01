-- ============================================================
-- Washington County Federal Fiscal Balance Database
-- Migration: 001_create_schemas.sql
-- Version: 0.2.0
-- Description: Create PostgreSQL schemas
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA IF NOT EXISTS reference;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS reporting;

COMMENT ON SCHEMA metadata IS 'Metadata, data dictionary, ETL logs, and project management tables';
COMMENT ON SCHEMA reference IS 'Reference and lookup tables such as states and counties';
COMMENT ON SCHEMA raw IS 'Raw imported data exactly as received from source agencies';
COMMENT ON SCHEMA staging IS 'Cleaned and standardized data ready for transformation';
COMMENT ON SCHEMA analytics IS 'Analytical tables and derived fiscal balance calculations';
COMMENT ON SCHEMA reporting IS 'Views and reporting objects';

COMMIT;