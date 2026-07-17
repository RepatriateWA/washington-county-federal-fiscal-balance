BEGIN;

CREATE SCHEMA IF NOT EXISTS cms;
CREATE SCHEMA IF NOT EXISTS reference;

-------------------------------------------------------------------------------
-- Medicaid service-category dimension
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reference.medicaid_service_category (

    medicaid_service_category_id BIGSERIAL PRIMARY KEY,

    service_category_name TEXT NOT NULL,

    normalized_service_category_name TEXT NOT NULL,

    default_row_type TEXT NOT NULL DEFAULT 'DETAIL',

    is_adjustment BOOLEAN NOT NULL DEFAULT FALSE,

    description TEXT,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_medicaid_service_category_name
        UNIQUE (service_category_name),

    CONSTRAINT uq_medicaid_service_category_normalized
        UNIQUE (normalized_service_category_name),

    CONSTRAINT chk_medicaid_service_category_row_type
        CHECK (
            default_row_type IN (
                'DETAIL',
                'ADJUSTMENT'
            )
        )
);

COMMENT ON TABLE reference.medicaid_service_category IS
    'Normalized CMS Medicaid service categories used by the curated '
    'Medicaid expenditure fact table.';

COMMENT ON COLUMN
    reference.medicaid_service_category.normalized_service_category_name IS
    'Lowercase, whitespace-normalized category name used for matching '
    'across annual CMS workbooks.';

COMMENT ON COLUMN
    reference.medicaid_service_category.is_adjustment IS
    'True for rebates, collections, offsets, recoveries, and other '
    'accounting adjustments that may contain negative expenditures.';

-------------------------------------------------------------------------------
-- Curated Medicaid service-expenditure fact table
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cms.medicaid_service_expenditures (

    medicaid_service_expenditure_id BIGSERIAL PRIMARY KEY,

    fiscal_year INTEGER NOT NULL,

    state_id BIGINT NOT NULL,

    federal_program_id BIGINT NOT NULL,

    medicaid_service_category_id BIGINT NOT NULL,

    source_raw_row_id BIGINT NOT NULL,

    row_type TEXT NOT NULL,

    total_computable NUMERIC(20, 2),

    federal_share NUMERIC(20, 2),

    federal_share_medicaid NUMERIC(20, 2),

    federal_share_arra NUMERIC(20, 2),

    federal_share_covid NUMERIC(20, 2),

    state_share NUMERIC(20, 2),

    expenditure_time_basis TEXT NOT NULL
        DEFAULT 'FEDERAL_FISCAL_YEAR',

    geographic_level TEXT NOT NULL
        DEFAULT 'STATE',

    source_agency TEXT NOT NULL
        DEFAULT 'Centers for Medicare & Medicaid Services',

    source_system TEXT NOT NULL
        DEFAULT 'Medicaid Budget and Expenditure System',

    source_report TEXT NOT NULL
        DEFAULT 'Medicaid Financial Management Report - Net Services',

    source_file TEXT NOT NULL,

    source_worksheet TEXT NOT NULL,

    source_row_number INTEGER NOT NULL,

    loaded_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_medicaid_service_expenditure_state
        FOREIGN KEY (state_id)
        REFERENCES reference.state_registry (state_id),

    CONSTRAINT fk_medicaid_service_expenditure_program
        FOREIGN KEY (federal_program_id)
        REFERENCES reference.federal_program (federal_program_id),

    CONSTRAINT fk_medicaid_service_expenditure_category
        FOREIGN KEY (medicaid_service_category_id)
        REFERENCES reference.medicaid_service_category (
            medicaid_service_category_id
        ),

    CONSTRAINT fk_medicaid_service_expenditure_raw
        FOREIGN KEY (source_raw_row_id)
        REFERENCES cms_raw.medicaid_mbes (raw_row_id),

    CONSTRAINT uq_medicaid_service_expenditure_raw
        UNIQUE (source_raw_row_id),

    CONSTRAINT chk_medicaid_service_expenditure_year
        CHECK (
            fiscal_year BETWEEN 1965 AND 2100
        ),

    CONSTRAINT chk_medicaid_service_expenditure_row_type
        CHECK (
            row_type IN (
                'DETAIL',
                'ADJUSTMENT'
            )
        ),

    CONSTRAINT chk_medicaid_expenditure_time_basis
        CHECK (
            expenditure_time_basis IN (
                'FEDERAL_FISCAL_YEAR'
            )
        ),

    CONSTRAINT chk_medicaid_expenditure_geographic_level
        CHECK (
            geographic_level IN (
                'STATE'
            )
        )
);

COMMENT ON TABLE cms.medicaid_service_expenditures IS
    'Curated, non-duplicative Medicaid service-level expenditures. '
    'Contains only PRIMARY worksheet rows classified as DETAIL or '
    'ADJUSTMENT and marked for detail reporting.';

COMMENT ON COLUMN cms.medicaid_service_expenditures.federal_share IS
    'Federal Medicaid expenditure amount used in federal fiscal-balance '
    'reporting. Negative adjustments are preserved.';

COMMENT ON COLUMN
    cms.medicaid_service_expenditures.federal_share_medicaid IS
    'Regular federal Medicaid component reported by CMS.';

COMMENT ON COLUMN
    cms.medicaid_service_expenditures.federal_share_arra IS
    'Federal ARRA component reported by CMS.';

COMMENT ON COLUMN
    cms.medicaid_service_expenditures.federal_share_covid IS
    'Federal COVID-related component reported by CMS. May be negative '
    'when prior-period enhanced funding is adjusted.';

-------------------------------------------------------------------------------
-- Official annual statewide control totals
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cms.medicaid_state_control_total (

    medicaid_state_control_total_id BIGSERIAL PRIMARY KEY,

    fiscal_year INTEGER NOT NULL,

    state_id BIGINT NOT NULL,

    federal_program_id BIGINT NOT NULL,

    source_raw_row_id BIGINT NOT NULL,

    total_computable NUMERIC(20, 2) NOT NULL,

    federal_share NUMERIC(20, 2) NOT NULL,

    federal_share_medicaid NUMERIC(20, 2),

    federal_share_arra NUMERIC(20, 2),

    federal_share_covid NUMERIC(20, 2),

    state_share NUMERIC(20, 2) NOT NULL,

    control_total_label TEXT NOT NULL
        DEFAULT 'Total Net Expenditures',

    expenditure_time_basis TEXT NOT NULL
        DEFAULT 'FEDERAL_FISCAL_YEAR',

    source_file TEXT NOT NULL,

    source_worksheet TEXT NOT NULL,

    source_row_number INTEGER NOT NULL,

    loaded_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_medicaid_control_total_state
        FOREIGN KEY (state_id)
        REFERENCES reference.state_registry (state_id),

    CONSTRAINT fk_medicaid_control_total_program
        FOREIGN KEY (federal_program_id)
        REFERENCES reference.federal_program (federal_program_id),

    CONSTRAINT fk_medicaid_control_total_raw
        FOREIGN KEY (source_raw_row_id)
        REFERENCES cms_raw.medicaid_mbes (raw_row_id),

    CONSTRAINT uq_medicaid_control_total_year_state
        UNIQUE (
            fiscal_year,
            state_id,
            federal_program_id
        ),

    CONSTRAINT uq_medicaid_control_total_raw
        UNIQUE (source_raw_row_id),

    CONSTRAINT chk_medicaid_control_total_year
        CHECK (
            fiscal_year BETWEEN 1965 AND 2100
        ),

    CONSTRAINT chk_medicaid_control_total_reconciliation
        CHECK (
            ABS(
                total_computable
                - federal_share
                - state_share
            ) <= 1.00
        ),

    CONSTRAINT chk_medicaid_control_total_time_basis
        CHECK (
            expenditure_time_basis = 'FEDERAL_FISCAL_YEAR'
        )
);

COMMENT ON TABLE cms.medicaid_state_control_total IS
    'Official CMS statewide Medicaid Total Net Expenditures control total '
    'for each federal fiscal year. Used to validate the sum of curated '
    'service-level expenditure rows.';

-------------------------------------------------------------------------------
-- Indexes
-------------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS
    idx_medicaid_service_category_adjustment
ON reference.medicaid_service_category (
    is_adjustment
);

CREATE INDEX IF NOT EXISTS
    idx_medicaid_service_expenditure_year_state
ON cms.medicaid_service_expenditures (
    fiscal_year,
    state_id
);

CREATE INDEX IF NOT EXISTS
    idx_medicaid_service_expenditure_program
ON cms.medicaid_service_expenditures (
    federal_program_id,
    fiscal_year
);

CREATE INDEX IF NOT EXISTS
    idx_medicaid_service_expenditure_category
ON cms.medicaid_service_expenditures (
    medicaid_service_category_id,
    fiscal_year
);

CREATE INDEX IF NOT EXISTS
    idx_medicaid_service_expenditure_row_type
ON cms.medicaid_service_expenditures (
    fiscal_year,
    row_type
);

CREATE INDEX IF NOT EXISTS
    idx_medicaid_control_total_year_state
ON cms.medicaid_state_control_total (
    fiscal_year,
    state_id
);

COMMIT;