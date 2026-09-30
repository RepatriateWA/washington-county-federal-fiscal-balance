BEGIN;

CREATE SCHEMA IF NOT EXISTS cms;

CREATE TABLE IF NOT EXISTS cms.medicare_core_county_year (
    medicare_core_county_year_id BIGSERIAL PRIMARY KEY,

    calendar_year INTEGER NOT NULL
        CHECK (calendar_year BETWEEN 2015 AND 2024),

    county_fips CHARACTER(5) NOT NULL,
    county_id BIGINT NOT NULL
        REFERENCES reference.county_registry(county_id),

    original_medicare_ffs_dollars NUMERIC,
    partc_dollars NUMERIC,
    partd_dollars NUMERIC,
    core_medicare_dollars NUMERIC,

    original_medicare_status TEXT NOT NULL,
    partc_status TEXT NOT NULL,
    partd_status TEXT NOT NULL,
    core_value_status TEXT NOT NULL,

    partc_months_represented INTEGER,
    partd_months_with_reconstructed_dollars INTEGER,

    partc_year_completeness TEXT NOT NULL,
    partd_coverage_status TEXT NOT NULL,

    time_window_status TEXT NOT NULL,
    timing_basis TEXT NOT NULL,

    original_medicare_geography_basis TEXT NOT NULL,
    partc_geography_basis TEXT NOT NULL,
    partd_geography_basis TEXT NOT NULL,
    partd_payment_match_basis TEXT NOT NULL,

    mssp_treatment TEXT NOT NULL,
    rds_treatment TEXT NOT NULL,
    washington_mffs_treatment TEXT NOT NULL,

    ledger_authorization TEXT NOT NULL,
    methodology_version TEXT NOT NULL,

    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,

    loaded_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_medicare_core_county_year
        UNIQUE (calendar_year, county_fips),

    CONSTRAINT ck_medicare_core_county_fips_wa
        CHECK (county_fips LIKE '53%'),

    CONSTRAINT ck_medicare_core_timing_basis
        CHECK (timing_basis = 'CALENDAR_YEAR'),

    CONSTRAINT ck_medicare_core_methodology
        CHECK (
            methodology_version =
            'CMS-MEDICARE-COUNTY-INTEGRATION-v0.1'
        ),

    CONSTRAINT ck_medicare_core_source_authorization
        CHECK (
            ledger_authorization =
            'NOT_AUTHORIZED_BY_THIS_CERTIFICATION'
        )
);

CREATE INDEX IF NOT EXISTS
    ix_medicare_core_county_year_county_id
ON cms.medicare_core_county_year (county_id);

CREATE INDEX IF NOT EXISTS
    ix_medicare_core_county_year_calendar_year
ON cms.medicare_core_county_year (calendar_year);

COMMENT ON TABLE cms.medicare_core_county_year IS
'Exact database promotion of CMS-MEDICARE-COUNTY-INTEGRATION-v0.1. '
'Preserves certified Original Medicare/FFS, Part C, Part D, and core '
'Medicare county-year results and their methodological status. '
'Loading this table does not itself authorize federal-inflow ledger inclusion.';

COMMENT ON COLUMN cms.medicare_core_county_year.core_medicare_dollars IS
'Original Medicare/FFS + Part C + Part D only when the certified '
'integration artifact reports all core components available. NULL is '
'preserved where the certified artifact does not provide a complete '
'county-year core value.';

COMMENT ON COLUMN cms.medicare_core_county_year.ledger_authorization IS
'Certification-artifact authorization status. ETL-169 preserves '
'NOT_AUTHORIZED_BY_THIS_CERTIFICATION and does not make a ledger decision.';

COMMIT;