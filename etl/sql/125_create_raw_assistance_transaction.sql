BEGIN;

CREATE TABLE IF NOT EXISTS assistance.raw_award_transaction (
    raw_assistance_transaction_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    load_batch_id BIGINT NOT NULL,
    source_row_number BIGINT NOT NULL,

    assistance_transaction_unique_key TEXT NOT NULL,
    assistance_award_unique_key TEXT NOT NULL,

    raw_record JSONB NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_raw_assistance_batch_row
        UNIQUE (
            load_batch_id,
            source_row_number
        ),

    CONSTRAINT uq_raw_assistance_batch_transaction
        UNIQUE (
            load_batch_id,
            assistance_transaction_unique_key
        ),

    CONSTRAINT fk_raw_assistance_load_batch
        FOREIGN KEY (load_batch_id)
        REFERENCES procurement.load_batch (
            load_batch_id
        )
        ON DELETE RESTRICT,

    CONSTRAINT ck_raw_assistance_source_row_positive
        CHECK (
            source_row_number > 0
        ),

    CONSTRAINT ck_raw_assistance_transaction_key_nonblank
        CHECK (
            BTRIM(assistance_transaction_unique_key) <> ''
        ),

    CONSTRAINT ck_raw_assistance_award_key_nonblank
        CHECK (
            BTRIM(assistance_award_unique_key) <> ''
        )
);

COMMENT ON TABLE assistance.raw_award_transaction IS
    'Immutable raw USAspending assistance prime-transaction observations.';

COMMENT ON COLUMN assistance.raw_award_transaction.load_batch_id IS
    'Source-ingestion batch registered in procurement.load_batch.';

COMMENT ON COLUMN assistance.raw_award_transaction.source_row_number IS
    'One-based physical data-row number after the CSV header.';

COMMENT ON COLUMN assistance.raw_award_transaction.assistance_transaction_unique_key IS
    'USAspending assistance transaction source identity.';

COMMENT ON COLUMN assistance.raw_award_transaction.assistance_award_unique_key IS
    'USAspending assistance award source identity.';

COMMENT ON COLUMN assistance.raw_award_transaction.raw_record IS
    'Complete source row preserved as JSONB without normalization.';

CREATE INDEX IF NOT EXISTS idx_raw_assistance_load_batch
    ON assistance.raw_award_transaction (
        load_batch_id
    );

CREATE INDEX IF NOT EXISTS idx_raw_assistance_award_key
    ON assistance.raw_award_transaction (
        assistance_award_unique_key
    );

CREATE INDEX IF NOT EXISTS idx_raw_assistance_transaction_key
    ON assistance.raw_award_transaction (
        assistance_transaction_unique_key
    );

CREATE INDEX IF NOT EXISTS idx_raw_assistance_raw_record_gin
    ON assistance.raw_award_transaction
    USING GIN (
        raw_record
    );

COMMIT;