-- ETL-202B.9E: additive provenance schema. REVIEW ONLY; do not execute yet.
-- One raw source observation links to at most one canonical transaction.
-- Many raw observations may link to the same canonical transaction.
BEGIN;
CREATE TABLE IF NOT EXISTS procurement.award_transaction_observation (
    raw_award_transaction_id BIGINT PRIMARY KEY
        REFERENCES procurement.raw_award_transaction(raw_award_transaction_id)
        ON DELETE RESTRICT,
    award_transaction_id BIGINT NOT NULL
        REFERENCES procurement.award_transaction(award_transaction_id)
        ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_procurement_tx_observation_canonical
    ON procurement.award_transaction_observation(award_transaction_id);
COMMENT ON TABLE procurement.award_transaction_observation IS
    'Non-additive source-to-canonical provenance; never sum amounts from this table.';
COMMIT;
