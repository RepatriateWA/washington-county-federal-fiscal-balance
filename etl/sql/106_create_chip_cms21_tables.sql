BEGIN;

CREATE SCHEMA IF NOT EXISTS chip;


-- ============================================================
-- 1. LOAD-BATCH PROVENANCE
-- ============================================================

CREATE TABLE IF NOT EXISTS chip.cms21_load_batch (
    load_batch_id BIGSERIAL PRIMARY KEY,

    fiscal_year INTEGER NOT NULL
        CHECK (fiscal_year BETWEEN 2015 AND 2100),

    source_workbook VARCHAR(500) NOT NULL,
    source_file_name VARCHAR(255) NOT NULL,
    source_file_sha256 CHARACTER(64),

    loaded_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    loader_name VARCHAR(255) NOT NULL,
    loader_version VARCHAR(50),

    notes TEXT,

    CONSTRAINT cms21_load_batch_unique_source
        UNIQUE (
            fiscal_year,
            source_workbook,
            source_file_name
        )
);


-- ============================================================
-- 2. RAW LANDING TABLE
--
-- Preserves worksheet values as read from Excel.
-- Raw financial fields are stored as text so that the landing
-- layer does not silently alter formatting or source content.
-- ============================================================

CREATE TABLE IF NOT EXISTS chip.cms21_raw_row (
    raw_row_id BIGSERIAL PRIMARY KEY,

    load_batch_id BIGINT NOT NULL
        REFERENCES chip.cms21_load_batch(load_batch_id)
        ON DELETE RESTRICT,

    fiscal_year INTEGER NOT NULL
        CHECK (fiscal_year BETWEEN 2015 AND 2100),

    state_fips CHARACTER(2) NOT NULL,
    state_abbreviation CHARACTER(2) NOT NULL,
    state_name VARCHAR(100) NOT NULL,

    worksheet_type VARCHAR(30) NOT NULL,
    source_sheet VARCHAR(255) NOT NULL,
    source_row INTEGER NOT NULL
        CHECK (source_row > 0),

    raw_service_category TEXT,
    raw_total_computable TEXT,
    raw_federal_share TEXT,
    raw_state_share TEXT,

    imported_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT cms21_raw_valid_worksheet_type
        CHECK (
            worksheet_type IN (
                'CHIP',
                'MCHIP',
                'MCHIP_20_PERCENT'
            )
        ),

    CONSTRAINT cms21_raw_unique_source_row
        UNIQUE (
            load_batch_id,
            source_sheet,
            source_row
        )
);


-- ============================================================
-- 3. CURATED EXPENDITURE TABLE
--
-- Contains normalized service categories and parsed numeric
-- values suitable for analysis and reporting.
-- ============================================================

CREATE TABLE IF NOT EXISTS chip.cms21_expenditure (
    chip_expenditure_id BIGSERIAL PRIMARY KEY,

    raw_row_id BIGINT NOT NULL
        REFERENCES chip.cms21_raw_row(raw_row_id)
        ON DELETE RESTRICT,

    load_batch_id BIGINT NOT NULL
        REFERENCES chip.cms21_load_batch(load_batch_id)
        ON DELETE RESTRICT,

    fiscal_year INTEGER NOT NULL
        CHECK (fiscal_year BETWEEN 2015 AND 2100),

    state_fips CHARACTER(2) NOT NULL,
    state_abbreviation CHARACTER(2) NOT NULL,
    state_name VARCHAR(100) NOT NULL,

    worksheet_type VARCHAR(30) NOT NULL,

    service_category_source TEXT NOT NULL,
    service_category_normalized TEXT NOT NULL,

    total_computable BIGINT NOT NULL,
    federal_share BIGINT NOT NULL,
    state_share BIGINT NOT NULL,

    row_type VARCHAR(30) NOT NULL DEFAULT 'DETAIL',
    is_control_total BOOLEAN NOT NULL DEFAULT FALSE,
    is_financing_adjustment BOOLEAN NOT NULL DEFAULT FALSE,
    is_additive_expenditure BOOLEAN NOT NULL DEFAULT TRUE,

    source_workbook VARCHAR(500) NOT NULL,
    source_sheet VARCHAR(255) NOT NULL,
    source_row INTEGER NOT NULL
        CHECK (source_row > 0),

    curated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT cms21_curated_valid_worksheet_type
        CHECK (
            worksheet_type IN (
                'CHIP',
                'MCHIP',
                'MCHIP_20_PERCENT'
            )
        ),

    CONSTRAINT cms21_curated_valid_row_type
        CHECK (
            row_type IN (
                'DETAIL',
                'SUBTOTAL',
                'CONTROL_TOTAL'
            )
        ),

    CONSTRAINT cms21_curated_accounting_identity
        CHECK (
            total_computable = federal_share + state_share
        ),

    CONSTRAINT cms21_curated_control_total_consistency
        CHECK (
            is_control_total =
            (row_type = 'CONTROL_TOTAL')
        ),

    CONSTRAINT cms21_curated_adjustment_consistency
        CHECK (
            (
                worksheet_type = 'MCHIP_20_PERCENT'
                AND is_financing_adjustment = TRUE
                AND is_additive_expenditure = FALSE
            )
            OR
            (
                worksheet_type IN ('CHIP', 'MCHIP')
                AND is_financing_adjustment = FALSE
            )
        ),

    CONSTRAINT cms21_curated_unique_raw_row
        UNIQUE (raw_row_id),

    CONSTRAINT cms21_curated_unique_source_row
        UNIQUE (
            fiscal_year,
            state_fips,
            source_workbook,
            source_sheet,
            source_row
        )
);


-- ============================================================
-- 4. INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_cms21_load_batch_year
    ON chip.cms21_load_batch (
        fiscal_year
    );

CREATE INDEX IF NOT EXISTS idx_cms21_raw_year_state
    ON chip.cms21_raw_row (
        fiscal_year,
        state_fips
    );

CREATE INDEX IF NOT EXISTS idx_cms21_raw_batch
    ON chip.cms21_raw_row (
        load_batch_id
    );

CREATE INDEX IF NOT EXISTS idx_cms21_raw_worksheet
    ON chip.cms21_raw_row (
        worksheet_type
    );

CREATE INDEX IF NOT EXISTS idx_cms21_expenditure_year_state
    ON chip.cms21_expenditure (
        fiscal_year,
        state_fips
    );

CREATE INDEX IF NOT EXISTS idx_cms21_expenditure_batch
    ON chip.cms21_expenditure (
        load_batch_id
    );

CREATE INDEX IF NOT EXISTS idx_cms21_expenditure_worksheet
    ON chip.cms21_expenditure (
        worksheet_type
    );

CREATE INDEX IF NOT EXISTS idx_cms21_expenditure_control_total
    ON chip.cms21_expenditure (
        fiscal_year,
        state_fips,
        is_control_total
    );

CREATE INDEX IF NOT EXISTS idx_cms21_expenditure_additive
    ON chip.cms21_expenditure (
        fiscal_year,
        state_fips,
        is_additive_expenditure
    );


-- ============================================================
-- 5. CURATED ANALYTICAL VIEWS
-- ============================================================

CREATE OR REPLACE VIEW chip.v_cms21_additive_expenditures AS
SELECT
    chip_expenditure_id,
    fiscal_year,
    state_fips,
    state_abbreviation,
    state_name,
    worksheet_type,
    service_category_source,
    service_category_normalized,
    total_computable,
    federal_share,
    state_share,
    row_type,
    is_control_total,
    source_workbook,
    source_sheet,
    source_row
FROM chip.cms21_expenditure
WHERE is_additive_expenditure = TRUE;


CREATE OR REPLACE VIEW chip.v_cms21_financing_adjustments AS
SELECT
    chip_expenditure_id,
    fiscal_year,
    state_fips,
    state_abbreviation,
    state_name,
    worksheet_type,
    service_category_source,
    service_category_normalized,
    total_computable,
    federal_share,
    state_share,
    row_type,
    is_control_total,
    source_workbook,
    source_sheet,
    source_row
FROM chip.cms21_expenditure
WHERE is_financing_adjustment = TRUE;


CREATE OR REPLACE VIEW chip.v_cms21_control_totals AS
SELECT
    fiscal_year,
    state_fips,
    state_abbreviation,
    state_name,
    worksheet_type,
    total_computable,
    federal_share,
    state_share,
    is_financing_adjustment,
    is_additive_expenditure,
    source_workbook,
    source_sheet,
    source_row
FROM chip.cms21_expenditure
WHERE is_control_total = TRUE;


COMMIT;