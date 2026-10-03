-- ============================================================================
-- ETL-153 — Create OMB Object Class Schema
-- ============================================================================
--
-- Purpose
-- -------
-- Establish the durable PostgreSQL evidence layer for Office of Management
-- and Budget (OMB) government-wide Object Class Analysis observations used
-- by WCFFBP to derive federal wage-obligation accounting controls.
--
-- Initial evidence population
-- ---------------------------
-- FFY2015-FFY2024
--
-- Preferred source vintage:
--
--   target FFY + 2 Budget vintage
--
-- where the target fiscal year is reported by OMB as ACTUAL.
--
-- Required wage object classes:
--
--   11.1  Full-time permanent
--   11.3  Other than full-time permanent
--   11.5  Other personnel compensation
--   11.6  Military personnel - basic allowance for housing
--   11.7  Military personnel
--   11.8  Special personal services payments
--
-- Accounting derivation (not stored as source observations):
--
--   MILITARY_WAGES
--       = 11.6 + 11.7
--
--   NONMILITARY_WAGES
--       = 11.1 + 11.3 + 11.5 + 11.8
--
--   TOTAL_WAGES
--       = MILITARY_WAGES + NONMILITARY_WAGES
--
-- Methodological principle
-- ------------------------
-- Atomic OMB observations are preserved independently of derived WCFFBP
-- accounting controls. Published source values are never silently altered.
--
-- In particular, the manually verified FFY2017 and FFY2018 source
-- observations are identical across all six wage object classes. Those
-- published values are preserved without modification.
-- ============================================================================

BEGIN;


-- ============================================================================
-- Schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS omb;


-- ============================================================================
-- Load batch
-- ============================================================================

CREATE TABLE IF NOT EXISTS omb.object_class_load_batch (

    load_batch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_dataset TEXT NOT NULL,

    source_file TEXT NOT NULL,

    source_sha256 TEXT NOT NULL,

    evidence_file TEXT NOT NULL,

    evidence_sha256 TEXT NOT NULL,

    fiscal_year_start INTEGER NOT NULL,

    fiscal_year_end INTEGER NOT NULL,

    expected_observation_count INTEGER NOT NULL,

    actual_observation_count INTEGER,

    source_verification TEXT NOT NULL,

    load_status TEXT NOT NULL DEFAULT 'STARTED',

    started_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMP WITH TIME ZONE,

    notes TEXT,

    CONSTRAINT object_class_load_batch_year_range_chk
        CHECK (
            fiscal_year_start >= 1900
            AND fiscal_year_end >= fiscal_year_start
        ),

    CONSTRAINT object_class_load_batch_expected_count_chk
        CHECK (
            expected_observation_count > 0
        ),

    CONSTRAINT object_class_load_batch_actual_count_chk
        CHECK (
            actual_observation_count IS NULL
            OR actual_observation_count >= 0
        ),

    CONSTRAINT object_class_load_batch_status_chk
        CHECK (
            load_status IN (
                'STARTED',
                'COMPLETED',
                'FAILED'
            )
        )
);


-- ============================================================================
-- Atomic Object Class observations
-- ============================================================================

CREATE TABLE IF NOT EXISTS omb.object_class_observation (

    object_class_observation_id
        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    load_batch_id BIGINT NOT NULL
        REFERENCES omb.object_class_load_batch (
            load_batch_id
        ),

    target_fiscal_year INTEGER NOT NULL,

    budget_vintage INTEGER NOT NULL,

    value_status TEXT NOT NULL,

    accounting_measure TEXT NOT NULL,

    scope TEXT NOT NULL,

    object_class_code TEXT NOT NULL,

    object_class_description TEXT NOT NULL,

    obligation_millions BIGINT NOT NULL,

    obligation_dollars BIGINT NOT NULL,

    source_page INTEGER NOT NULL,

    source_file TEXT NOT NULL,

    source_sha256 TEXT NOT NULL,

    source_verification TEXT NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT object_class_observation_fiscal_year_chk
        CHECK (
            target_fiscal_year >= 1900
        ),

    CONSTRAINT object_class_observation_budget_vintage_chk
        CHECK (
            budget_vintage >= target_fiscal_year
        ),

    CONSTRAINT object_class_observation_value_status_chk
        CHECK (
            value_status IN (
                'ACTUAL',
                'ESTIMATE'
            )
        ),

    CONSTRAINT object_class_observation_scope_chk
        CHECK (
            scope IN (
                'GOVERNMENT_WIDE'
            )
        ),

    CONSTRAINT object_class_observation_amount_chk
        CHECK (
            obligation_millions >= 0
            AND obligation_dollars >= 0
        ),

    CONSTRAINT object_class_observation_unit_reconciliation_chk
        CHECK (
            obligation_dollars
            = obligation_millions * 1000000
        ),

    CONSTRAINT object_class_observation_source_page_chk
        CHECK (
            source_page > 0
        ),

    CONSTRAINT object_class_observation_unique
        UNIQUE (
            load_batch_id,
            target_fiscal_year,
            budget_vintage,
            object_class_code
        )
);


-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS
    idx_omb_object_class_observation_fiscal_year
ON omb.object_class_observation (
    target_fiscal_year
);


CREATE INDEX IF NOT EXISTS
    idx_omb_object_class_observation_code
ON omb.object_class_observation (
    object_class_code
);


CREATE INDEX IF NOT EXISTS
    idx_omb_object_class_observation_batch
ON omb.object_class_observation (
    load_batch_id
);


-- ============================================================================
-- Structural validation
-- ============================================================================

DO $$
DECLARE
    table_count INTEGER;
BEGIN

    SELECT COUNT(*)
    INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'omb'
      AND table_name IN (
          'object_class_load_batch',
          'object_class_observation'
      );

    IF table_count <> 2 THEN
        RAISE EXCEPTION
            'Expected 2 OMB tables; found %.',
            table_count;
    END IF;

END
$$;


COMMIT;