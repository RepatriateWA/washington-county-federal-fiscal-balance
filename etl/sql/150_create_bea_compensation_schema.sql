-- ============================================================================
-- ETL-150 — Create BEA Federal Compensation Schema
-- ============================================================================
--
-- Purpose
-- -------
-- Create durable source-specific storage for Bureau of Economic Analysis
-- Regional compensation data used by WCFFBP.
--
-- Initial covered series:
--
--     CAINC6N-2001
--         Federal civilian compensation by county / state aggregate
--
--     CAINC6N-2002
--         Military compensation by county / state aggregate
--
--     SAINC6N-2001
--         Federal civilian compensation state control
--
--     SAINC6N-2002
--         Military compensation state control
--
-- Initial period:
--     Calendar years 2015-2024
--
-- Accounting concept:
--     Compensation of employees
--
-- Reference-period basis:
--     CALENDAR_YEAR
--
-- Geographic basis:
--     PLACE_OF_WORK
--
-- Source units:
--     Thousands of dollars
--
-- Stored normalized value:
--     Whole dollars
--
-- Design principles
-- -----------------
-- * Preserve BEA source observations before projecting them into any common
--   federal-inflow ledger.
-- * Preserve CAINC6N and SAINC6N as independent source observations even where
--   their Washington state values are numerically identical.
-- * Preserve BEA's original GeoFips, GeoName, Code, CL_UNIT, UNIT_MULT, and
--   DataValue fields for auditability.
-- * Link county/state observations to WCFFBP reference geography.
-- * Record acquisition vintage and raw-source provenance through a load batch.
-- ============================================================================

BEGIN;


-- ============================================================================
-- Schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS bea;


-- ============================================================================
-- Load batch
-- ============================================================================
--
-- One row represents one logical BEA compensation load from a preserved
-- acquisition vintage.
--
-- The loader should load the four checksummed source artifacts acquired
-- together:
--
--     CAINC6N-2001
--     CAINC6N-2002
--     SAINC6N-2001
--     SAINC6N-2002
--
-- This separates source acquisition from database loading and allows later
-- BEA vintages to coexist without destroying historical provenance.
-- ============================================================================

CREATE TABLE IF NOT EXISTS bea.compensation_load_batch (

    load_batch_id BIGSERIAL PRIMARY KEY,

    dataset_name TEXT NOT NULL
        DEFAULT 'BEA_REGIONAL_COMPENSATION',

    acquisition_manifest_path TEXT NOT NULL,

    acquisition_manifest_sha256 TEXT,

    source_retrieved_utc TIMESTAMPTZ,

    calendar_year_start INTEGER NOT NULL,

    calendar_year_end INTEGER NOT NULL,

    status TEXT NOT NULL
        DEFAULT 'STARTED',

    rows_loaded BIGINT,

    notes TEXT,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMP WITHOUT TIME ZONE,

    CONSTRAINT bea_compensation_load_batch_year_range_ck
        CHECK (
            calendar_year_start BETWEEN 1900 AND 2200
            AND calendar_year_end BETWEEN 1900 AND 2200
            AND calendar_year_end >= calendar_year_start
        ),

    CONSTRAINT bea_compensation_load_batch_status_ck
        CHECK (
            status IN (
                'STARTED',
                'COMPLETED',
                'FAILED'
            )
        )
);


-- ============================================================================
-- Compensation observation
-- ============================================================================
--
-- One row represents one BEA source observation.
--
-- Important:
--     CAINC6N GeoFips=53000 and SAINC6N GeoFips=53000 are intentionally
--     stored as separate observations. Their exact reconciliation is a
--     validation result, not a reason to collapse the source records.
-- ============================================================================

CREATE TABLE IF NOT EXISTS bea.compensation_observation (

    compensation_observation_id BIGSERIAL PRIMARY KEY,

    load_batch_id BIGINT NOT NULL
        REFERENCES bea.compensation_load_batch(load_batch_id),

    -- ------------------------------------------------------------------------
    -- WCFFBP semantic identity
    -- ------------------------------------------------------------------------

    compensation_family TEXT NOT NULL,

    accounting_measure TEXT NOT NULL
        DEFAULT 'COMPENSATION_OF_EMPLOYEES',

    reference_period_type TEXT NOT NULL
        DEFAULT 'CALENDAR_YEAR',

    calendar_year INTEGER NOT NULL,

    geographic_basis TEXT NOT NULL
        DEFAULT 'PLACE_OF_WORK',

    geography_level TEXT NOT NULL,

    -- ------------------------------------------------------------------------
    -- Canonical WCFFBP geography
    -- ------------------------------------------------------------------------

    state_id BIGINT
        REFERENCES reference.state_registry(state_id),

    county_id BIGINT
        REFERENCES reference.county_registry(county_id),

    -- ------------------------------------------------------------------------
    -- BEA source identity
    -- ------------------------------------------------------------------------

    source_dataset TEXT NOT NULL
        DEFAULT 'Regional',

    source_table TEXT NOT NULL,

    source_line_code TEXT NOT NULL,

    source_code TEXT NOT NULL,

    source_geo_fips TEXT NOT NULL,

    source_geo_name TEXT NOT NULL,

    -- ------------------------------------------------------------------------
    -- Source value as delivered by BEA
    -- ------------------------------------------------------------------------

    source_data_value TEXT NOT NULL,

    source_unit TEXT NOT NULL,

    source_unit_multiplier INTEGER NOT NULL,

    -- ------------------------------------------------------------------------
    -- Normalized WCFFBP accounting value
    -- ------------------------------------------------------------------------

    value_dollars NUMERIC(20, 2) NOT NULL,

    -- ------------------------------------------------------------------------
    -- Raw-source provenance
    -- ------------------------------------------------------------------------

    source_file TEXT NOT NULL,

    source_file_sha256 TEXT,

    source_row_number BIGINT,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,


    -- ========================================================================
    -- Semantic constraints
    -- ========================================================================

    CONSTRAINT bea_compensation_family_ck
        CHECK (
            compensation_family IN (
                'FEDERAL_CIVILIAN_COMPENSATION',
                'MILITARY_COMPENSATION'
            )
        ),

    CONSTRAINT bea_compensation_accounting_measure_ck
        CHECK (
            accounting_measure = 'COMPENSATION_OF_EMPLOYEES'
        ),

    CONSTRAINT bea_compensation_reference_period_ck
        CHECK (
            reference_period_type = 'CALENDAR_YEAR'
        ),

    CONSTRAINT bea_compensation_calendar_year_ck
        CHECK (
            calendar_year BETWEEN 1900 AND 2200
        ),

    CONSTRAINT bea_compensation_geographic_basis_ck
        CHECK (
            geographic_basis = 'PLACE_OF_WORK'
        ),

    CONSTRAINT bea_compensation_geography_level_ck
        CHECK (
            geography_level IN (
                'STATE',
                'COUNTY'
            )
        ),

    CONSTRAINT bea_compensation_source_table_ck
        CHECK (
            source_table IN (
                'CAINC6N',
                'SAINC6N'
            )
        ),

    CONSTRAINT bea_compensation_source_line_code_ck
        CHECK (
            source_line_code IN (
                '2001',
                '2002'
            )
        ),

    CONSTRAINT bea_compensation_source_unit_multiplier_ck
        CHECK (
            source_unit_multiplier >= 0
        ),

    CONSTRAINT bea_compensation_geography_fk_ck
        CHECK (
            (
                geography_level = 'STATE'
                AND state_id IS NOT NULL
                AND county_id IS NULL
            )
            OR
            (
                geography_level = 'COUNTY'
                AND state_id IS NOT NULL
                AND county_id IS NOT NULL
            )
        ),

    CONSTRAINT bea_compensation_table_geography_ck
        CHECK (
            (
                source_table = 'SAINC6N'
                AND geography_level = 'STATE'
            )
            OR
            source_table = 'CAINC6N'
        ),

    CONSTRAINT bea_compensation_series_family_ck
        CHECK (
            (
                source_line_code = '2001'
                AND compensation_family =
                    'FEDERAL_CIVILIAN_COMPENSATION'
            )
            OR
            (
                source_line_code = '2002'
                AND compensation_family =
                    'MILITARY_COMPENSATION'
            )
        )
);


-- ============================================================================
-- Uniqueness
-- ============================================================================
--
-- Prevent duplicate loading of the same BEA observation within a load batch.
--
-- source_table is included because:
--
--     CAINC6N / 53000 / 2024
--
-- and:
--
--     SAINC6N / 53000 / 2024
--
-- are distinct source observations even when their values are identical.
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS
    ux_bea_compensation_observation_source
ON bea.compensation_observation (
    load_batch_id,
    source_table,
    source_line_code,
    source_geo_fips,
    calendar_year
);


-- ============================================================================
-- Query / reconciliation indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS
    ix_bea_compensation_family_year
ON bea.compensation_observation (
    compensation_family,
    calendar_year
);


CREATE INDEX IF NOT EXISTS
    ix_bea_compensation_county_year
ON bea.compensation_observation (
    county_id,
    calendar_year
)
WHERE county_id IS NOT NULL;


CREATE INDEX IF NOT EXISTS
    ix_bea_compensation_state_year
ON bea.compensation_observation (
    state_id,
    calendar_year
);


CREATE INDEX IF NOT EXISTS
    ix_bea_compensation_source_series
ON bea.compensation_observation (
    source_table,
    source_line_code,
    calendar_year
);


-- ============================================================================
-- Documentation comments
-- ============================================================================

COMMENT ON SCHEMA bea IS
    'Bureau of Economic Analysis source-specific data and controls.';


COMMENT ON TABLE bea.compensation_load_batch IS
    'Load-batch provenance for preserved BEA Regional compensation acquisition vintages.';


COMMENT ON TABLE bea.compensation_observation IS
    'BEA Regional compensation observations. Initial series are CAINC6N/SAINC6N lines 2001 Federal civilian and 2002 Military. Values are calendar-year, place-of-work compensation measures.';


COMMENT ON COLUMN bea.compensation_observation.value_dollars IS
    'BEA DataValue normalized to dollars using UNIT_MULT. Source observations currently report thousands of dollars with UNIT_MULT=3.';


COMMENT ON COLUMN bea.compensation_observation.source_data_value IS
    'Original BEA DataValue preserved verbatim before numeric normalization.';


COMMENT ON COLUMN bea.compensation_observation.geographic_basis IS
    'Economic geographic attribution basis. Initial BEA compensation series are PLACE_OF_WORK rather than residence-based.';


COMMENT ON COLUMN bea.compensation_observation.reference_period_type IS
    'Initial BEA annual compensation observations are CALENDAR_YEAR and must not be silently relabeled as federal fiscal year.';


COMMIT;