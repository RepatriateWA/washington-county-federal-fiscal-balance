BEGIN;

CREATE TABLE IF NOT EXISTS assistance.award_transaction_defc (
    assistance_transaction_id BIGINT NOT NULL,
    extraordinary_funding_code_id BIGINT NOT NULL,

    observed_description TEXT NOT NULL,
    raw_defc_value TEXT NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_assistance_transaction_defc
        PRIMARY KEY (
            assistance_transaction_id,
            extraordinary_funding_code_id
        ),

    CONSTRAINT fk_assistance_transaction_defc_transaction
        FOREIGN KEY (assistance_transaction_id)
        REFERENCES assistance.award_transaction (
            assistance_transaction_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fk_assistance_transaction_defc_code
        FOREIGN KEY (extraordinary_funding_code_id)
        REFERENCES reference.extraordinary_funding_code (
            extraordinary_funding_code_id
        )
);

COMMENT ON TABLE assistance.award_transaction_defc IS
    'Observed DEFC relationships for normalized assistance transactions.';

COMMENT ON COLUMN assistance.award_transaction_defc.observed_description IS
    'Description observed in the source row for this DEFC code.';

COMMENT ON COLUMN assistance.award_transaction_defc.raw_defc_value IS
    'Complete unmodified DEFC source value from the transaction row.';

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_defc_code
    ON assistance.award_transaction_defc (
        extraordinary_funding_code_id
    );

COMMIT;