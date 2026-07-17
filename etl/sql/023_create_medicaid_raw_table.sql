CREATE SCHEMA IF NOT EXISTS cms_raw;

CREATE TABLE IF NOT EXISTS cms_raw.medicaid_mbes (
    raw_row_id BIGSERIAL PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    state_name TEXT NOT NULL,
    service_category TEXT NOT NULL,
    total_computable NUMERIC(20, 2),
    federal_share NUMERIC(20, 2),
    federal_share_medicaid NUMERIC(20, 2),
    federal_share_arra NUMERIC(20, 2),
    federal_share_covid NUMERIC(20, 2),
    state_share NUMERIC(20, 2),
    source_file TEXT NOT NULL,
    imported_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Upgrade the earlier table definition without deleting any existing data.

ALTER TABLE cms_raw.medicaid_mbes
    ADD COLUMN IF NOT EXISTS worksheet_name TEXT;

ALTER TABLE cms_raw.medicaid_mbes
    ADD COLUMN IF NOT EXISTS source_row_number INTEGER;

ALTER TABLE cms_raw.medicaid_mbes
    ADD COLUMN IF NOT EXISTS section_code TEXT;

ALTER TABLE cms_raw.medicaid_mbes
    ADD COLUMN IF NOT EXISTS row_type TEXT;

ALTER TABLE cms_raw.medicaid_mbes
    ADD COLUMN IF NOT EXISTS include_in_detail_reporting BOOLEAN;

-- Supply safe values if rows were previously loaded.

UPDATE cms_raw.medicaid_mbes
SET worksheet_name = 'MAP - Washington'
WHERE worksheet_name IS NULL;

UPDATE cms_raw.medicaid_mbes
SET source_row_number = raw_row_id::INTEGER
WHERE source_row_number IS NULL;

UPDATE cms_raw.medicaid_mbes
SET section_code =
    CASE
        WHEN service_category LIKE 'Created On:%' THEN 'FOOTER'
        WHEN service_category LIKE 'C-%' THEN 'C'
        WHEN service_category LIKE 'T-%' THEN 'T'
        ELSE 'PRIMARY'
    END
WHERE section_code IS NULL;

UPDATE cms_raw.medicaid_mbes
SET row_type =
    CASE
        WHEN service_category LIKE 'Created On:%'
            THEN 'FOOTER'

        WHEN service_category IN (
            'Total Net Expenditures',
            'C-Total Net',
            'T-Total Net Expenditures'
        )
            THEN 'CONTROL_TOTAL'

        WHEN service_category ILIKE 'Total %'
            THEN 'SUBTOTAL'

        WHEN service_category ILIKE '%rebate%'
          OR service_category ILIKE '%offset%'
          OR service_category ILIKE '%collection%'
          OR COALESCE(federal_share, 0) < 0
            THEN 'ADJUSTMENT'

        ELSE 'DETAIL'
    END
WHERE row_type IS NULL;

UPDATE cms_raw.medicaid_mbes
SET include_in_detail_reporting =
    CASE
        WHEN section_code = 'PRIMARY'
         AND row_type IN ('DETAIL', 'ADJUSTMENT')
            THEN TRUE
        ELSE FALSE
    END
WHERE include_in_detail_reporting IS NULL;

ALTER TABLE cms_raw.medicaid_mbes
    ALTER COLUMN worksheet_name SET NOT NULL;

ALTER TABLE cms_raw.medicaid_mbes
    ALTER COLUMN source_row_number SET NOT NULL;

ALTER TABLE cms_raw.medicaid_mbes
    ALTER COLUMN section_code SET NOT NULL;

ALTER TABLE cms_raw.medicaid_mbes
    ALTER COLUMN row_type SET NOT NULL;

ALTER TABLE cms_raw.medicaid_mbes
    ALTER COLUMN include_in_detail_reporting
        SET DEFAULT FALSE;

ALTER TABLE cms_raw.medicaid_mbes
    ALTER COLUMN include_in_detail_reporting SET NOT NULL;

-- Add validation constraints only if they do not already exist.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_mbes_section'
          AND conrelid = 'cms_raw.medicaid_mbes'::regclass
    ) THEN
        ALTER TABLE cms_raw.medicaid_mbes
            ADD CONSTRAINT chk_medicaid_mbes_section
            CHECK (
                section_code IN (
                    'PRIMARY',
                    'C',
                    'T',
                    'FOOTER'
                )
            );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_mbes_row_type'
          AND conrelid = 'cms_raw.medicaid_mbes'::regclass
    ) THEN
        ALTER TABLE cms_raw.medicaid_mbes
            ADD CONSTRAINT chk_medicaid_mbes_row_type
            CHECK (
                row_type IN (
                    'DETAIL',
                    'ADJUSTMENT',
                    'CONTROL_TOTAL',
                    'SUBTOTAL',
                    'FOOTER'
                )
            );
    END IF;
END
$$;

-- A unique index provides the same duplicate protection while remaining
-- easy to create idempotently.

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_medicaid_mbes_source_row
ON cms_raw.medicaid_mbes (
    fiscal_year,
    state_name,
    worksheet_name,
    source_row_number,
    source_file
);

CREATE INDEX IF NOT EXISTS idx_medicaid_mbes_year_state
ON cms_raw.medicaid_mbes (
    fiscal_year,
    state_name
);

CREATE INDEX IF NOT EXISTS idx_medicaid_mbes_service_category
ON cms_raw.medicaid_mbes (
    service_category
);

CREATE INDEX IF NOT EXISTS idx_medicaid_mbes_section
ON cms_raw.medicaid_mbes (
    fiscal_year,
    state_name,
    section_code
);

CREATE INDEX IF NOT EXISTS idx_medicaid_mbes_reporting_rows
ON cms_raw.medicaid_mbes (
    fiscal_year,
    state_name,
    include_in_detail_reporting
);