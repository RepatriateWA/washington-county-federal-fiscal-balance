BEGIN;

CREATE INDEX IF NOT EXISTS
    idx_procurement_transaction_batch_row
ON procurement.award_transaction (
    load_batch_id,
    source_row_number
);

CREATE INDEX IF NOT EXISTS
    idx_procurement_raw_batch_row
ON procurement.raw_award_transaction (
    load_batch_id,
    source_row_number
);

COMMIT;