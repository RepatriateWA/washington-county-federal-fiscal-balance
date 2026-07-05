CREATE SCHEMA IF NOT EXISTS expenditure;

-- ==========================================================
-- Federal programs
-- ==========================================================

CREATE TABLE IF NOT EXISTS expenditure.program (
    program_id          SERIAL PRIMARY KEY,
    program_code        VARCHAR(50) UNIQUE NOT NULL,
    program_name        VARCHAR(200) NOT NULL,
    description         TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================================
-- Data sources
-- ==========================================================

CREATE TABLE IF NOT EXISTS expenditure.data_source (
    data_source_id      SERIAL PRIMARY KEY,
    source_code         VARCHAR(50) UNIQUE NOT NULL,
    source_name         VARCHAR(200) NOT NULL,
    agency_name         VARCHAR(200),
    source_url          TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================================
-- Federal expenditure facts
-- ==========================================================

CREATE TABLE IF NOT EXISTS expenditure.payment (
    payment_id                  BIGSERIAL PRIMARY KEY,

    fiscal_year                 INTEGER NOT NULL,

    state_id                    BIGINT
        REFERENCES reference.state_registry(state_id),

    county_id                   BIGINT
        REFERENCES reference.county_registry(county_id),

    program_id                  INTEGER
        REFERENCES expenditure.program(program_id),

    data_source_id              INTEGER
        REFERENCES expenditure.data_source(data_source_id),

    payment_amount              NUMERIC(18,2),

    source_record_count         INTEGER,

    source_file                 TEXT,

    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payment_year
    ON expenditure.payment(fiscal_year);

CREATE INDEX IF NOT EXISTS idx_payment_county
    ON expenditure.payment(county_id);

CREATE INDEX IF NOT EXISTS idx_payment_program
    ON expenditure.payment(program_id);