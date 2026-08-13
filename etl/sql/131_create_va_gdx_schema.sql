-- ETL-VA-GDX-001
-- Create VA Geographic Distribution of Expenditures (GDX) schema.
--
-- Purpose:
--   Preserve and normalize Washington county-level VA GDX observations
--   for FY2015-FY2024 while retaining source semantics across the
--   FY2024 methodology/schema break.
--
-- Source regimes:
--   FY2015-FY2023 = LEGACY_STATE_SHEETS
--   FY2024        = REVISED_DIRECT_INDIRECT
--
-- Important:
--   Raw VA source workbooks remain immutable in data/raw/va/gdx/.
--   This schema stores normalized observations plus complete source
--   provenance.  It does NOT yet make VA GDX additive to the final
--   federal-fiscal-balance ledger; overlap with USAspending must first
--   be reconciled.

BEGIN;

CREATE SCHEMA IF NOT EXISTS va;


-- ============================================================================
-- 1. LOAD BATCH
-- ============================================================================

CREATE TABLE IF NOT EXISTS va.gdx_load_batch (
    gdx_load_batch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    fiscal_year INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 CHAR(64) NOT NULL,

    schema_regime VARCHAR(40) NOT NULL,
    methodology_regime VARCHAR(40) NOT NULL,
    methodology_break BOOLEAN NOT NULL DEFAULT FALSE,

    load_started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    load_completed_at TIMESTAMP WITHOUT TIME ZONE,

    source_county_rows INTEGER,
    loaded_expenditure_rows INTEGER NOT NULL DEFAULT 0,
    loaded_metric_rows INTEGER NOT NULL DEFAULT 0,
    rejected_row_count INTEGER NOT NULL DEFAULT 0,

    load_status VARCHAR(30) NOT NULL DEFAULT 'STARTED',
    notes TEXT,

    CONSTRAINT ck_gdx_load_fiscal_year
        CHECK (fiscal_year BETWEEN 1996 AND 2100),

    CONSTRAINT ck_gdx_load_schema_regime
        CHECK (
            schema_regime IN (
                'LEGACY_STATE_SHEETS',
                'REVISED_DIRECT_INDIRECT'
            )
        ),

    CONSTRAINT ck_gdx_load_methodology_regime
        CHECK (
            methodology_regime IN (
                'LEGACY_PRE_FY2024',
                'REVISED_FY2024'
            )
        ),

    CONSTRAINT ck_gdx_load_status
        CHECK (
            load_status IN (
                'STARTED',
                'COMPLETED',
                'COMPLETED_WITH_REJECTIONS',
                'FAILED'
            )
        ),

    CONSTRAINT ck_gdx_load_nonnegative_counts
        CHECK (
            COALESCE(source_county_rows, 0) >= 0
            AND loaded_expenditure_rows >= 0
            AND loaded_metric_rows >= 0
            AND rejected_row_count >= 0
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_gdx_load_batch_year_hash
    ON va.gdx_load_batch (
        fiscal_year,
        source_sha256
    );

CREATE INDEX IF NOT EXISTS ix_gdx_load_batch_year
    ON va.gdx_load_batch (
        fiscal_year
    );


-- ============================================================================
-- 2. EXPENDITURE CATEGORY DIMENSION
-- ============================================================================

CREATE TABLE IF NOT EXISTS va.gdx_expenditure_category (
    gdx_category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    category_code VARCHAR(80) NOT NULL,
    category_name VARCHAR(255) NOT NULL,

    aggregation_role VARCHAR(30) NOT NULL,
    first_fiscal_year INTEGER,
    last_fiscal_year INTEGER,

    description TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ux_gdx_category_code
        UNIQUE (category_code),

    CONSTRAINT ck_gdx_category_aggregation_role
        CHECK (
            aggregation_role IN (
                'COMPONENT',
                'CONTROL_TOTAL'
            )
        ),

    CONSTRAINT ck_gdx_category_year_range
        CHECK (
            first_fiscal_year IS NULL
            OR last_fiscal_year IS NULL
            OR first_fiscal_year <= last_fiscal_year
        )
);


-- ============================================================================
-- 3. COUNTY EXPENDITURE OBSERVATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS va.gdx_county_expenditure (
    gdx_county_expenditure_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    gdx_load_batch_id BIGINT NOT NULL,
    fiscal_year INTEGER NOT NULL,

    county_id BIGINT NOT NULL,
    county_name_source VARCHAR(255) NOT NULL,

    schema_regime VARCHAR(40) NOT NULL,
    expenditure_class VARCHAR(20) NOT NULL,

    gdx_category_id BIGINT NOT NULL,

    source_category_name VARCHAR(255) NOT NULL,

    -- Exact numeric observation as represented by the source workbook.
    source_amount NUMERIC(24,6),

    -- FY2015-FY2023 source sheets state "Expenditures in $000s".
    -- FY2024 source sheets state "Expenditures in $s".
    source_unit VARCHAR(20) NOT NULL,

    -- Normalized dollars used for financial reconciliation.
    expenditure_amount NUMERIC(24,2),

    source_sheet VARCHAR(255) NOT NULL,
    source_row_number INTEGER NOT NULL,
    source_column_number INTEGER NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_gdx_expenditure_load_batch
        FOREIGN KEY (gdx_load_batch_id)
        REFERENCES va.gdx_load_batch(gdx_load_batch_id),

    CONSTRAINT fk_gdx_expenditure_county
        FOREIGN KEY (county_id)
        REFERENCES reference.county_registry(county_id),

    CONSTRAINT fk_gdx_expenditure_category
        FOREIGN KEY (gdx_category_id)
        REFERENCES va.gdx_expenditure_category(gdx_category_id),

    CONSTRAINT ck_gdx_expenditure_schema_regime
        CHECK (
            schema_regime IN (
                'LEGACY_STATE_SHEETS',
                'REVISED_DIRECT_INDIRECT'
            )
        ),

    CONSTRAINT ck_gdx_expenditure_class
        CHECK (
            expenditure_class IN (
                'LEGACY',
                'DIRECT',
                'INDIRECT'
            )
        ),

    CONSTRAINT ck_gdx_expenditure_source_unit
        CHECK (
            source_unit IN (
                'USD',
                'USD_THOUSANDS'
            )
        ),

    CONSTRAINT ck_gdx_expenditure_source_location
        CHECK (
            source_row_number > 0
            AND source_column_number > 0
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_gdx_county_expenditure_source
    ON va.gdx_county_expenditure (
        gdx_load_batch_id,
        source_sheet,
        source_row_number,
        source_column_number
    );

CREATE INDEX IF NOT EXISTS ix_gdx_county_expenditure_year_county
    ON va.gdx_county_expenditure (
        fiscal_year,
        county_id
    );

CREATE INDEX IF NOT EXISTS ix_gdx_county_expenditure_category
    ON va.gdx_county_expenditure (
        gdx_category_id
    );


-- ============================================================================
-- 4. NON-EXPENDITURE COUNTY METRICS
-- ============================================================================
-- Legacy GDX workbooks also contain useful contextual measures such as
-- Veteran Population and Unique Patients.  These are intentionally kept
-- outside the expenditure table so they can never be accidentally summed
-- into federal expenditures.

CREATE TABLE IF NOT EXISTS va.gdx_county_metric (
    gdx_county_metric_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    gdx_load_batch_id BIGINT NOT NULL,
    fiscal_year INTEGER NOT NULL,

    county_id BIGINT NOT NULL,
    county_name_source VARCHAR(255) NOT NULL,

    metric_code VARCHAR(80) NOT NULL,
    metric_name VARCHAR(255) NOT NULL,

    source_value NUMERIC(24,6),
    source_unit VARCHAR(30) NOT NULL,

    source_sheet VARCHAR(255) NOT NULL,
    source_row_number INTEGER NOT NULL,
    source_column_number INTEGER NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_gdx_metric_load_batch
        FOREIGN KEY (gdx_load_batch_id)
        REFERENCES va.gdx_load_batch(gdx_load_batch_id),

    CONSTRAINT fk_gdx_metric_county
        FOREIGN KEY (county_id)
        REFERENCES reference.county_registry(county_id),

    CONSTRAINT ck_gdx_metric_source_unit
        CHECK (
            source_unit IN (
                'PERSON_ESTIMATE',
                'PERSON_COUNT'
            )
        ),

    CONSTRAINT ck_gdx_metric_source_location
        CHECK (
            source_row_number > 0
            AND source_column_number > 0
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_gdx_county_metric_source
    ON va.gdx_county_metric (
        gdx_load_batch_id,
        source_sheet,
        source_row_number,
        source_column_number
    );

CREATE INDEX IF NOT EXISTS ix_gdx_county_metric_year_county
    ON va.gdx_county_metric (
        fiscal_year,
        county_id
    );


-- ============================================================================
-- 5. SEED CANONICAL GDX EXPENDITURE CATEGORIES
-- ============================================================================
-- These codes preserve the published GDX concepts.  They do not assert that
-- identically named categories are methodologically identical across every
-- year; schema_regime and source_category_name preserve that distinction.

INSERT INTO va.gdx_expenditure_category (
    category_code,
    category_name,
    aggregation_role,
    first_fiscal_year,
    last_fiscal_year,
    description
)
VALUES
    (
        'TOTAL_EXPENDITURE',
        'Total Expenditure',
        'CONTROL_TOTAL',
        2015,
        2023,
        'Legacy GDX county total expenditure control.'
    ),
    (
        'COMPENSATION_PENSION',
        'Compensation & Pension',
        'COMPONENT',
        2015,
        NULL,
        'VA compensation and pension expenditures.'
    ),
    (
        'CONSTRUCTION',
        'Construction',
        'COMPONENT',
        2015,
        NULL,
        'VA construction and related expenditures.'
    ),
    (
        'EDUCATION_VRE',
        'Education & Vocational Rehabilitation / Employment',
        'COMPONENT',
        2015,
        NULL,
        'VA education and vocational rehabilitation/employment expenditures.'
    ),
    (
        'LOAN_GUARANTY',
        'Loan Guaranty',
        'COMPONENT',
        2015,
        NULL,
        'VA loan guaranty expenditures.'
    ),
    (
        'GENERAL_OPERATING_EXPENSES',
        'General Operating Expenses',
        'COMPONENT',
        2015,
        2023,
        'Legacy GDX general operating expenses.'
    ),
    (
        'INSURANCE_INDEMNITIES',
        'Insurance & Indemnities',
        'COMPONENT',
        2015,
        2023,
        'Legacy GDX insurance and indemnity expenditures.'
    ),
    (
        'MEDICAL_CARE',
        'Medical Care',
        'COMPONENT',
        2015,
        NULL,
        'VA medical care expenditures.'
    ),
    (
        'TOTAL_DIRECT_EXPENDITURE',
        'Total Direct Expenditure',
        'CONTROL_TOTAL',
        2024,
        NULL,
        'FY2024+ GDX direct expenditure control total.'
    ),
    (
        'INSURANCE',
        'Insurance',
        'COMPONENT',
        2024,
        NULL,
        'FY2024+ VA insurance expenditures.'
    ),
    (
        'DIC_SURVIVORS_PENSION',
        'Dependency & Indemnity Compensation and Survivors Pension',
        'COMPONENT',
        2024,
        NULL,
        'FY2024+ DIC and Survivors Pension expenditures.'
    ),
    (
        'TOTAL_INDIRECT_EXPENDITURE',
        'Total Indirect Expenditure',
        'CONTROL_TOTAL',
        2024,
        NULL,
        'FY2024+ GDX indirect expenditure control total.'
    ),
    (
        'MEMORIAL_BENEFITS',
        'Memorial Benefits',
        'COMPONENT',
        2024,
        NULL,
        'FY2024+ VA memorial benefits expenditures.'
    ),
    (
        'SPECIALLY_ADAPTED_HOUSING_AUTOMOBILES',
        'Specially Adapted Housing and Automobiles and Adaptive Equipment',
        'COMPONENT',
        2024,
        NULL,
        'FY2024+ specially adapted housing and automobile/adaptive equipment expenditures.'
    )
ON CONFLICT (category_code) DO NOTHING;


-- ============================================================================
-- 6. REPORTING VIEW: COUNTY CONTROL TOTALS
-- ============================================================================
-- This view exposes one county-level VA control total per year:
--   FY2015-FY2023: legacy Total Expenditure
--   FY2024: Direct control + Indirect control
--
-- It is a reconciliation view only.  It is NOT yet declared additive to the
-- final fiscal-balance ledger because VA/USAspending overlap remains unresolved.

CREATE OR REPLACE VIEW va.v_washington_county_gdx_control_total AS
WITH category_codes AS (
    SELECT
        gdx_category_id,
        category_code
    FROM va.gdx_expenditure_category
),
legacy AS (
    SELECT
        e.fiscal_year,
        e.county_id,
        e.county_name_source,
        SUM(e.expenditure_amount) AS va_gdx_expenditure_amount
    FROM va.gdx_county_expenditure AS e
    JOIN category_codes AS c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year BETWEEN 2015 AND 2023
      AND c.category_code = 'TOTAL_EXPENDITURE'
    GROUP BY
        e.fiscal_year,
        e.county_id,
        e.county_name_source
),
revised AS (
    SELECT
        e.fiscal_year,
        e.county_id,
        e.county_name_source,
        SUM(e.expenditure_amount) AS va_gdx_expenditure_amount
    FROM va.gdx_county_expenditure AS e
    JOIN category_codes AS c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year >= 2024
      AND c.category_code IN (
          'TOTAL_DIRECT_EXPENDITURE',
          'TOTAL_INDIRECT_EXPENDITURE'
      )
    GROUP BY
        e.fiscal_year,
        e.county_id,
        e.county_name_source
)
SELECT * FROM legacy
UNION ALL
SELECT * FROM revised;


COMMENT ON SCHEMA va IS
'Department of Veterans Affairs expenditure domain for the Washington County Federal Fiscal Balance project.';

COMMENT ON TABLE va.gdx_load_batch IS
'Provenance and load accounting for one VA GDX fiscal-year workbook.';

COMMENT ON TABLE va.gdx_expenditure_category IS
'Canonical VA GDX expenditure category dictionary.';

COMMENT ON TABLE va.gdx_county_expenditure IS
'County-level VA GDX expenditure observations normalized to dollars while preserving source units and source location.';

COMMENT ON TABLE va.gdx_county_metric IS
'Non-expenditure county metrics from VA GDX such as Veteran Population and Unique Patients.';

COMMENT ON VIEW va.v_washington_county_gdx_control_total IS
'County-level VA GDX annual control totals. FY2015-FY2023 use legacy Total Expenditure; FY2024+ sum Direct and Indirect control totals. Not yet approved as additive to the final fiscal-balance ledger pending overlap reconciliation.';


COMMIT;