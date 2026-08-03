-- Creates an auditable record of source-data anomalies encountered
-- during procurement normalization.

CREATE TABLE IF NOT EXISTS procurement.normalization_exception (
    normalization_exception_id BIGSERIAL PRIMARY KEY,

    load_batch_id BIGINT NOT NULL
        REFERENCES procurement.load_batch(load_batch_id),

    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,

    anomaly_code TEXT NOT NULL,
    severity TEXT NOT NULL,

    source_row_numbers BIGINT[] NOT NULL DEFAULT '{}',

    raw_values JSONB NOT NULL,
    normalized_action JSONB NOT NULL,

    message TEXT NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_procurement_normalization_exception_severity
        CHECK (severity IN ('WARNING', 'ERROR')),

    CONSTRAINT uq_procurement_normalization_exception
        UNIQUE (
            load_batch_id,
            entity_type,
            entity_key,
            anomaly_code
        )
);

CREATE INDEX IF NOT EXISTS
    idx_procurement_normalization_exception_batch
ON procurement.normalization_exception (load_batch_id);

CREATE INDEX IF NOT EXISTS
    idx_procurement_normalization_exception_entity
ON procurement.normalization_exception (
    entity_type,
    entity_key
);

COMMENT ON TABLE procurement.normalization_exception IS
    'Auditable source-data anomalies encountered during procurement normalization.';

COMMENT ON COLUMN procurement.normalization_exception.raw_values IS
    'Original source values relevant to the anomaly.';

COMMENT ON COLUMN procurement.normalization_exception.normalized_action IS
    'Explicit description of how normalization handled the anomaly.';