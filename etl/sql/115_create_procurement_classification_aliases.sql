-- Preserves classification descriptions exactly as observed in each
-- USAspending source batch while retaining one canonical description
-- in procurement.naics and procurement.psc.

CREATE TABLE IF NOT EXISTS procurement.naics_alias (
    load_batch_id BIGINT NOT NULL
        REFERENCES procurement.load_batch(load_batch_id),

    naics_code TEXT NOT NULL
        REFERENCES procurement.naics(naics_code),

    observed_description TEXT NOT NULL,

    occurrence_count BIGINT NOT NULL,

    first_source_row_number BIGINT,
    last_source_row_number BIGINT,

    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_procurement_naics_alias
        PRIMARY KEY (
            load_batch_id,
            naics_code,
            observed_description
        ),

    CONSTRAINT ck_procurement_naics_alias_occurrence_count
        CHECK (occurrence_count > 0),

    CONSTRAINT ck_procurement_naics_alias_source_rows
        CHECK (
            (
                first_source_row_number IS NULL
                AND last_source_row_number IS NULL
            )
            OR (
                first_source_row_number IS NOT NULL
                AND last_source_row_number IS NOT NULL
                AND first_source_row_number > 0
                AND first_source_row_number
                    <= last_source_row_number
            )
        )
);


CREATE TABLE IF NOT EXISTS procurement.psc_alias (
    load_batch_id BIGINT NOT NULL
        REFERENCES procurement.load_batch(load_batch_id),

    psc_code TEXT NOT NULL
        REFERENCES procurement.psc(psc_code),

    observed_description TEXT NOT NULL,

    occurrence_count BIGINT NOT NULL,

    first_source_row_number BIGINT,
    last_source_row_number BIGINT,

    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_procurement_psc_alias
        PRIMARY KEY (
            load_batch_id,
            psc_code,
            observed_description
        ),

    CONSTRAINT ck_procurement_psc_alias_occurrence_count
        CHECK (occurrence_count > 0),

    CONSTRAINT ck_procurement_psc_alias_source_rows
        CHECK (
            (
                first_source_row_number IS NULL
                AND last_source_row_number IS NULL
            )
            OR (
                first_source_row_number IS NOT NULL
                AND last_source_row_number IS NOT NULL
                AND first_source_row_number > 0
                AND first_source_row_number
                    <= last_source_row_number
            )
        )
);


CREATE INDEX IF NOT EXISTS
    idx_procurement_naics_alias_code
ON procurement.naics_alias (naics_code);


CREATE INDEX IF NOT EXISTS
    idx_procurement_psc_alias_code
ON procurement.psc_alias (psc_code);


COMMENT ON TABLE procurement.naics_alias IS
    'NAICS descriptions observed in individual USAspending source batches.';


COMMENT ON TABLE procurement.psc_alias IS
    'PSC descriptions observed in individual USAspending source batches.';


COMMENT ON COLUMN procurement.naics_alias.occurrence_count IS
    'Number of source rows in this load batch containing this exact code-description pair.';


COMMENT ON COLUMN procurement.psc_alias.occurrence_count IS
    'Number of source rows in this load batch containing this exact code-description pair.';