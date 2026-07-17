BEGIN;

CREATE SCHEMA IF NOT EXISTS reference;
CREATE SCHEMA IF NOT EXISTS cms;

-------------------------------------------------------------------------------
-- 1. Upgrade the existing Medicaid service-category dimension
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reference.medicaid_service_category (
    medicaid_service_category_id BIGSERIAL PRIMARY KEY,
    service_category_name TEXT NOT NULL,
    is_adjustment BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE reference.medicaid_service_category
    ADD COLUMN IF NOT EXISTS normalized_service_category_name TEXT;

ALTER TABLE reference.medicaid_service_category
    ADD COLUMN IF NOT EXISTS default_row_type TEXT;

ALTER TABLE reference.medicaid_service_category
    ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE reference.medicaid_service_category
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE;

UPDATE reference.medicaid_service_category
SET normalized_service_category_name =
    LOWER(
        REGEXP_REPLACE(
            TRIM(service_category_name),
            '\s+',
            ' ',
            'g'
        )
    )
WHERE normalized_service_category_name IS NULL
   OR TRIM(normalized_service_category_name) = '';

UPDATE reference.medicaid_service_category
SET default_row_type =
    CASE
        WHEN is_adjustment THEN 'ADJUSTMENT'
        ELSE 'DETAIL'
    END
WHERE default_row_type IS NULL;

UPDATE reference.medicaid_service_category
SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
WHERE updated_at IS NULL;

ALTER TABLE reference.medicaid_service_category
    ALTER COLUMN normalized_service_category_name SET NOT NULL;

ALTER TABLE reference.medicaid_service_category
    ALTER COLUMN default_row_type SET DEFAULT 'DETAIL';

ALTER TABLE reference.medicaid_service_category
    ALTER COLUMN default_row_type SET NOT NULL;

ALTER TABLE reference.medicaid_service_category
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE reference.medicaid_service_category
    ALTER COLUMN updated_at SET NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT normalized_service_category_name
        FROM reference.medicaid_service_category
        GROUP BY normalized_service_category_name
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Duplicate normalized Medicaid service-category names exist.';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_medicaid_service_category_name
ON reference.medicaid_service_category (
    service_category_name
);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_medicaid_service_category_normalized
ON reference.medicaid_service_category (
    normalized_service_category_name
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_service_category_row_type'
          AND conrelid =
              'reference.medicaid_service_category'::regclass
    ) THEN
        ALTER TABLE reference.medicaid_service_category
            ADD CONSTRAINT chk_medicaid_service_category_row_type
            CHECK (
                default_row_type IN (
                    'DETAIL',
                    'ADJUSTMENT'
                )
            );
    END IF;
END
$$;

COMMENT ON TABLE reference.medicaid_service_category IS
    'Normalized CMS Medicaid service categories used by the curated '
    'Medicaid expenditure fact table.';

COMMENT ON COLUMN
    reference.medicaid_service_category.normalized_service_category_name IS
    'Lowercase and whitespace-normalized category name used for matching '
    'service categories across annual CMS workbooks.';

COMMENT ON COLUMN
    reference.medicaid_service_category.is_adjustment IS
    'True for rebates, offsets, collections, recoveries, and similar '
    'accounting adjustments.';

-------------------------------------------------------------------------------
-- 2. Create or upgrade curated Medicaid service expenditures
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cms.medicaid_service_expenditures (
    medicaid_service_expenditure_id BIGSERIAL PRIMARY KEY
);

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS fiscal_year INTEGER;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS state_id BIGINT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS federal_program_id BIGINT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS medicaid_service_category_id BIGINT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS source_raw_row_id BIGINT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS row_type TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS total_computable NUMERIC(20, 2);

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS federal_share NUMERIC(20, 2);

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS federal_share_medicaid NUMERIC(20, 2);

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS federal_share_arra NUMERIC(20, 2);

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS federal_share_covid NUMERIC(20, 2);

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS state_share NUMERIC(20, 2);

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS expenditure_time_basis TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS geographic_level TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS source_agency TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS source_system TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS source_report TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS source_file TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS source_worksheet TEXT;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS source_row_number INTEGER;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS loaded_at TIMESTAMP WITHOUT TIME ZONE;

UPDATE cms.medicaid_service_expenditures
SET expenditure_time_basis = 'FEDERAL_FISCAL_YEAR'
WHERE expenditure_time_basis IS NULL;

UPDATE cms.medicaid_service_expenditures
SET geographic_level = 'STATE'
WHERE geographic_level IS NULL;

UPDATE cms.medicaid_service_expenditures
SET source_agency =
    'Centers for Medicare & Medicaid Services'
WHERE source_agency IS NULL;

UPDATE cms.medicaid_service_expenditures
SET source_system =
    'Medicaid Budget and Expenditure System'
WHERE source_system IS NULL;

UPDATE cms.medicaid_service_expenditures
SET source_report =
    'Medicaid Financial Management Report - Net Services'
WHERE source_report IS NULL;

UPDATE cms.medicaid_service_expenditures
SET loaded_at = CURRENT_TIMESTAMP
WHERE loaded_at IS NULL;

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN expenditure_time_basis
        SET DEFAULT 'FEDERAL_FISCAL_YEAR';

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN geographic_level
        SET DEFAULT 'STATE';

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN source_agency
        SET DEFAULT 'Centers for Medicare & Medicaid Services';

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN source_system
        SET DEFAULT 'Medicaid Budget and Expenditure System';

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN source_report
        SET DEFAULT 'Medicaid Financial Management Report - Net Services';

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN loaded_at
        SET DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_medicaid_service_expenditure_state'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT fk_medicaid_service_expenditure_state
            FOREIGN KEY (state_id)
            REFERENCES reference.state_registry (state_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_medicaid_service_expenditure_program'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT fk_medicaid_service_expenditure_program
            FOREIGN KEY (federal_program_id)
            REFERENCES reference.federal_program (federal_program_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_medicaid_service_expenditure_category'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT fk_medicaid_service_expenditure_category
            FOREIGN KEY (medicaid_service_category_id)
            REFERENCES reference.medicaid_service_category (
                medicaid_service_category_id
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_medicaid_service_expenditure_raw'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT fk_medicaid_service_expenditure_raw
            FOREIGN KEY (source_raw_row_id)
            REFERENCES cms_raw.medicaid_mbes (raw_row_id);
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_service_expenditure_year'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT chk_medicaid_service_expenditure_year
            CHECK (fiscal_year BETWEEN 1965 AND 2100);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_service_expenditure_row_type'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT chk_medicaid_service_expenditure_row_type
            CHECK (row_type IN ('DETAIL', 'ADJUSTMENT'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_expenditure_time_basis'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT chk_medicaid_expenditure_time_basis
            CHECK (
                expenditure_time_basis = 'FEDERAL_FISCAL_YEAR'
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_expenditure_geographic_level'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT chk_medicaid_expenditure_geographic_level
            CHECK (geographic_level = 'STATE');
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_medicaid_service_expenditure_raw
ON cms.medicaid_service_expenditures (
    source_raw_row_id
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

-------------------------------------------------------------------------------
-- 3. Create or upgrade official Medicaid state control totals
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cms.medicaid_state_control_total (
    medicaid_state_control_total_id BIGSERIAL PRIMARY KEY
);

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS fiscal_year INTEGER;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS state_id BIGINT;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS federal_program_id BIGINT;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS source_raw_row_id BIGINT;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS total_computable NUMERIC(20, 2);

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS federal_share NUMERIC(20, 2);

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS federal_share_medicaid NUMERIC(20, 2);

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS federal_share_arra NUMERIC(20, 2);

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS federal_share_covid NUMERIC(20, 2);

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS state_share NUMERIC(20, 2);

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS control_total_label TEXT;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS expenditure_time_basis TEXT;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS source_file TEXT;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS source_worksheet TEXT;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS source_row_number INTEGER;

ALTER TABLE cms.medicaid_state_control_total
    ADD COLUMN IF NOT EXISTS loaded_at TIMESTAMP WITHOUT TIME ZONE;

UPDATE cms.medicaid_state_control_total
SET control_total_label = 'Total Net Expenditures'
WHERE control_total_label IS NULL;

UPDATE cms.medicaid_state_control_total
SET expenditure_time_basis = 'FEDERAL_FISCAL_YEAR'
WHERE expenditure_time_basis IS NULL;

UPDATE cms.medicaid_state_control_total
SET loaded_at = CURRENT_TIMESTAMP
WHERE loaded_at IS NULL;

ALTER TABLE cms.medicaid_state_control_total
    ALTER COLUMN control_total_label
        SET DEFAULT 'Total Net Expenditures';

ALTER TABLE cms.medicaid_state_control_total
    ALTER COLUMN expenditure_time_basis
        SET DEFAULT 'FEDERAL_FISCAL_YEAR';

ALTER TABLE cms.medicaid_state_control_total
    ALTER COLUMN loaded_at
        SET DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_medicaid_control_total_state'
          AND conrelid =
              'cms.medicaid_state_control_total'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_state_control_total
            ADD CONSTRAINT fk_medicaid_control_total_state
            FOREIGN KEY (state_id)
            REFERENCES reference.state_registry (state_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_medicaid_control_total_program'
          AND conrelid =
              'cms.medicaid_state_control_total'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_state_control_total
            ADD CONSTRAINT fk_medicaid_control_total_program
            FOREIGN KEY (federal_program_id)
            REFERENCES reference.federal_program (federal_program_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_medicaid_control_total_raw'
          AND conrelid =
              'cms.medicaid_state_control_total'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_state_control_total
            ADD CONSTRAINT fk_medicaid_control_total_raw
            FOREIGN KEY (source_raw_row_id)
            REFERENCES cms_raw.medicaid_mbes (raw_row_id);
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_control_total_year'
          AND conrelid =
              'cms.medicaid_state_control_total'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_state_control_total
            ADD CONSTRAINT chk_medicaid_control_total_year
            CHECK (fiscal_year BETWEEN 1965 AND 2100);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'chk_medicaid_control_total_reconciliation'
          AND conrelid =
              'cms.medicaid_state_control_total'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_state_control_total
            ADD CONSTRAINT
                chk_medicaid_control_total_reconciliation
            CHECK (
                ABS(
                    total_computable
                    - federal_share
                    - state_share
                ) <= 1.00
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_control_total_time_basis'
          AND conrelid =
              'cms.medicaid_state_control_total'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_state_control_total
            ADD CONSTRAINT chk_medicaid_control_total_time_basis
            CHECK (
                expenditure_time_basis = 'FEDERAL_FISCAL_YEAR'
            );
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_medicaid_control_total_year_state_program
ON cms.medicaid_state_control_total (
    fiscal_year,
    state_id,
    federal_program_id
);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_medicaid_control_total_raw
ON cms.medicaid_state_control_total (
    source_raw_row_id
);

CREATE INDEX IF NOT EXISTS
    idx_medicaid_control_total_year_state
ON cms.medicaid_state_control_total (
    fiscal_year,
    state_id
);

COMMIT;