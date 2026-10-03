-- ============================================================================
-- ETL-155 — Create BEA Wage Evidence Schema
-- ============================================================================
--
-- Purpose
-- -------
-- Extend the existing BEA evidence schema with tables dedicated to BEA
-- wage-and-salary observations.
--
-- Initial use:
--   BEA Regional API
--   Table SAINC7N
--   Line 2002 — Federal military wages
--   Calendar years 2015-2024
--
-- Geographic evidence population preserved:
--   United States
--   50 states
--   District of Columbia
--   8 BEA regions
--
-- Methodological boundary
-- -----------------------
-- These observations are geographic allocation evidence. They do NOT replace
-- OMB government-wide federal wage obligations as the WCFFBP national
-- accounting control.
--
-- Compensation and wages remain separate evidence families:
--
--   bea.compensation_*  = CAINC6N / SAINC6N compensation evidence
--   bea.wage_*          = SAINC7N wage-and-salary evidence
--
-- ============================================================================

BEGIN;


-- ============================================================================
-- Load-batch provenance
-- ============================================================================

CREATE TABLE IF NOT EXISTS bea.wage_load_batch (

    load_batch_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    dataset_name TEXT NOT NULL,

    source_table TEXT NOT NULL,

    source_line_code TEXT NOT NULL,

    source_file TEXT NOT NULL,

    source_file_sha256 TEXT NOT NULL,

    source_retrieved_utc TIMESTAMP WITH TIME ZONE,

    calendar_year_start INTEGER NOT NULL,

    calendar_year_end INTEGER NOT NULL,

    expected_rows BIGINT,

    rows_loaded BIGINT,

    status TEXT NOT NULL
        DEFAULT 'STARTED',

    notes TEXT,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMP WITHOUT TIME ZONE,

    CONSTRAINT wage_load_batch_year_range_chk
        CHECK (
            calendar_year_start >= 1900
            AND calendar_year_end >= calendar_year_start
        ),

    CONSTRAINT wage_load_batch_expected_rows_chk
        CHECK (
            expected_rows IS NULL
            OR expected_rows > 0
        ),

    CONSTRAINT wage_load_batch_rows_loaded_chk
        CHECK (
            rows_loaded IS NULL
            OR rows_loaded >= 0
        ),

    CONSTRAINT wage_load_batch_status_chk
        CHECK (
            status IN (
                'STARTED',
                'COMPLETED',
                'FAILED'
            )
        )
);


-- ============================================================================
-- Atomic wage observations
-- ============================================================================

CREATE TABLE IF NOT EXISTS bea.wage_observation (

    wage_observation_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    load_batch_id BIGINT NOT NULL
        REFERENCES bea.wage_load_batch (
            load_batch_id
        ),

    wage_family TEXT NOT NULL,

    accounting_measure TEXT NOT NULL,

    reference_period_type TEXT NOT NULL,

    calendar_year INTEGER NOT NULL,

    geographic_basis TEXT NOT NULL,

    geography_level TEXT NOT NULL,

    state_id BIGINT,

    source_dataset TEXT NOT NULL,

    source_table TEXT NOT NULL,

    source_line_code TEXT NOT NULL,

    source_code TEXT,

    source_geo_fips TEXT NOT NULL,

    source_geo_name TEXT NOT NULL,

    source_data_value TEXT NOT NULL,

    source_unit TEXT,

    source_unit_multiplier INTEGER NOT NULL,

    value_dollars NUMERIC NOT NULL,

    source_file TEXT NOT NULL,

    source_file_sha256 TEXT NOT NULL,

    source_row_number BIGINT,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT wage_observation_year_chk
        CHECK (
            calendar_year >= 1900
        ),

    CONSTRAINT wage_observation_value_chk
        CHECK (
            value_dollars >= 0
        ),

    CONSTRAINT wage_observation_geo_level_chk
        CHECK (
            geography_level IN (
                'UNITED_STATES',
                'STATE',
                'DISTRICT_OF_COLUMBIA',
                'BEA_REGION'
            )
        ),

    CONSTRAINT wage_observation_reference_period_chk
        CHECK (
            reference_period_type IN (
                'CALENDAR_YEAR'
            )
        ),

    CONSTRAINT wage_observation_unique
        UNIQUE (
            load_batch_id,
            source_table,
            source_line_code,
            calendar_year,
            source_geo_fips
        )
);


-- ============================================================================
-- Useful indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS
    idx_bea_wage_observation_year
ON bea.wage_observation (
    calendar_year
);


CREATE INDEX IF NOT EXISTS
    idx_bea_wage_observation_geo_fips
ON bea.wage_observation (
    source_geo_fips
);


CREATE INDEX IF NOT EXISTS
    idx_bea_wage_observation_state
ON bea.wage_observation (
    state_id
);


CREATE INDEX IF NOT EXISTS
    idx_bea_wage_observation_family
ON bea.wage_observation (
    wage_family
);


CREATE INDEX IF NOT EXISTS
    idx_bea_wage_observation_batch
ON bea.wage_observation (
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
    WHERE
        table_schema = 'bea'
        AND table_name IN (
            'wage_load_batch',
            'wage_observation'
        );

    IF table_count <> 2 THEN
        RAISE EXCEPTION
            'Expected 2 BEA wage tables; found %.',
            table_count;
    END IF;

    RAISE NOTICE
        'BEA wage evidence schema validation PASSED.';

END
$$;


COMMIT;