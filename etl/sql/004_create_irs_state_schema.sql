CREATE TABLE IF NOT EXISTS irs.state_collections (
    state_collections_id BIGSERIAL PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    state_id BIGINT REFERENCES reference.state_registry(state_id),
    state_name TEXT NOT NULL,
    tax_category TEXT NOT NULL,

    returns_filed BIGINT,
    returns_filed_electronically BIGINT,
    gross_collections_thousands BIGINT,
    refunds_issued BIGINT,
    refund_amount_thousands BIGINT,

    source_file TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (fiscal_year, state_id, tax_category)
);