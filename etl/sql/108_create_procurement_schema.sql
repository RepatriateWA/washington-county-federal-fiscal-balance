BEGIN;

CREATE SCHEMA IF NOT EXISTS procurement;

COMMENT ON SCHEMA procurement IS
    'Award-level federal contracts and procurement data, primarily sourced from USAspending.';


-- ============================================================================
-- LOAD BATCH
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.load_batch (
    load_batch_id           BIGSERIAL PRIMARY KEY,
    source_file             TEXT NOT NULL,
    source_url              TEXT,
    file_sha256             TEXT,
    fiscal_year_start       INTEGER,
    fiscal_year_end         INTEGER,
    downloaded_at           TIMESTAMP WITHOUT TIME ZONE,
    load_started_at         TIMESTAMP WITHOUT TIME ZONE NOT NULL
                            DEFAULT CURRENT_TIMESTAMP,
    load_completed_at       TIMESTAMP WITHOUT TIME ZONE,
    source_record_count     BIGINT,
    loaded_record_count     BIGINT,
    rejected_record_count   BIGINT,
    load_status             TEXT NOT NULL DEFAULT 'STARTED',
    notes                   TEXT,

    CONSTRAINT ck_procurement_load_batch_years
        CHECK (
            fiscal_year_start IS NULL
            OR fiscal_year_end IS NULL
            OR fiscal_year_start <= fiscal_year_end
        ),

    CONSTRAINT ck_procurement_load_batch_counts
        CHECK (
            COALESCE(source_record_count, 0) >= 0
            AND COALESCE(loaded_record_count, 0) >= 0
            AND COALESCE(rejected_record_count, 0) >= 0
        ),

    CONSTRAINT ck_procurement_load_batch_status
        CHECK (
            load_status IN (
                'STARTED',
                'COMPLETED',
                'COMPLETED_WITH_REJECTIONS',
                'FAILED'
            )
        )
);

COMMENT ON TABLE procurement.load_batch IS
    'Provenance and audit information for each procurement source-file load.';


-- ============================================================================
-- RECIPIENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.recipient (
    recipient_id                    BIGSERIAL PRIMARY KEY,
    recipient_uei                   TEXT,
    recipient_duns                  TEXT,
    recipient_name                  TEXT NOT NULL,
    recipient_name_normalized       TEXT,
    recipient_parent_uei            TEXT,
    recipient_parent_name           TEXT,
    recipient_type_code             TEXT,
    business_categories             TEXT,
    created_at                      TIMESTAMP WITHOUT TIME ZONE NOT NULL
                                    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_procurement_recipient_identifier
        CHECK (
            recipient_uei IS NOT NULL
            OR recipient_duns IS NOT NULL
            OR recipient_name IS NOT NULL
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_procurement_recipient_uei
    ON procurement.recipient (recipient_uei)
    WHERE recipient_uei IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_procurement_recipient_duns
    ON procurement.recipient (recipient_duns);

CREATE INDEX IF NOT EXISTS idx_procurement_recipient_name_normalized
    ON procurement.recipient (recipient_name_normalized);

COMMENT ON TABLE procurement.recipient IS
    'Federal procurement award recipients identified by UEI, legacy DUNS, or normalized name.';


-- ============================================================================
-- NAICS REFERENCE
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.naics (
    naics_code              TEXT PRIMARY KEY,
    naics_description       TEXT NOT NULL,
    naics_year              INTEGER,
    created_at              TIMESTAMP WITHOUT TIME ZONE NOT NULL
                            DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_procurement_naics_code
        CHECK (naics_code ~ '^[0-9]{2,6}$')
);

COMMENT ON TABLE procurement.naics IS
    'North American Industry Classification System codes used by procurement awards.';


-- ============================================================================
-- PRODUCT OR SERVICE CODE REFERENCE
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.psc (
    psc_code                TEXT PRIMARY KEY,
    psc_description         TEXT,
    product_or_service      TEXT,
    created_at              TIMESTAMP WITHOUT TIME ZONE NOT NULL
                            DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE procurement.psc IS
    'Federal Product or Service Classification codes used by procurement awards.';


-- ============================================================================
-- AWARD
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.award (
    award_id                        BIGSERIAL PRIMARY KEY,

    generated_unique_award_id       TEXT NOT NULL,
    piid                            TEXT,
    parent_award_id                 TEXT,
    award_type_code                 TEXT,
    award_type_description          TEXT,

    recipient_id                    BIGINT,

    awarding_agency_id              BIGINT,
    awarding_subagency_id           BIGINT,
    funding_agency_id               BIGINT,
    funding_subagency_id            BIGINT,

    award_description               TEXT,
    period_of_performance_start     DATE,
    period_of_performance_end       DATE,

    first_load_batch_id             BIGINT,
    last_load_batch_id              BIGINT,

    created_at                      TIMESTAMP WITHOUT TIME ZONE NOT NULL
                                    DEFAULT CURRENT_TIMESTAMP,
    updated_at                      TIMESTAMP WITHOUT TIME ZONE NOT NULL
                                    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_procurement_award_generated_id
        UNIQUE (generated_unique_award_id),

    CONSTRAINT fk_procurement_award_recipient
        FOREIGN KEY (recipient_id)
        REFERENCES procurement.recipient(recipient_id),

    CONSTRAINT fk_procurement_award_awarding_agency
        FOREIGN KEY (awarding_agency_id)
        REFERENCES reference.federal_agency(federal_agency_id),

    CONSTRAINT fk_procurement_award_awarding_subagency
        FOREIGN KEY (awarding_subagency_id)
        REFERENCES reference.federal_agency(federal_agency_id),

    CONSTRAINT fk_procurement_award_funding_agency
        FOREIGN KEY (funding_agency_id)
        REFERENCES reference.federal_agency(federal_agency_id),

    CONSTRAINT fk_procurement_award_funding_subagency
        FOREIGN KEY (funding_subagency_id)
        REFERENCES reference.federal_agency(federal_agency_id),

    CONSTRAINT fk_procurement_award_first_load_batch
        FOREIGN KEY (first_load_batch_id)
        REFERENCES procurement.load_batch(load_batch_id),

    CONSTRAINT fk_procurement_award_last_load_batch
        FOREIGN KEY (last_load_batch_id)
        REFERENCES procurement.load_batch(load_batch_id),

    CONSTRAINT ck_procurement_award_performance_dates
        CHECK (
            period_of_performance_start IS NULL
            OR period_of_performance_end IS NULL
            OR period_of_performance_start <= period_of_performance_end
        )
);

CREATE INDEX IF NOT EXISTS idx_procurement_award_piid
    ON procurement.award (piid);

CREATE INDEX IF NOT EXISTS idx_procurement_award_recipient
    ON procurement.award (recipient_id);

CREATE INDEX IF NOT EXISTS idx_procurement_award_awarding_agency
    ON procurement.award (awarding_agency_id);

CREATE INDEX IF NOT EXISTS idx_procurement_award_funding_agency
    ON procurement.award (funding_agency_id);

COMMENT ON TABLE procurement.award IS
    'Stable federal procurement award records. Financial actions are stored separately in award_transaction.';


-- ============================================================================
-- AWARD TRANSACTION
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.award_transaction (
    award_transaction_id            BIGSERIAL PRIMARY KEY,

    usaspending_transaction_id      TEXT NOT NULL,
    award_id                        BIGINT NOT NULL,
    load_batch_id                   BIGINT NOT NULL,

    action_date                     DATE NOT NULL,
    fiscal_year                     INTEGER NOT NULL,
    fiscal_quarter                  INTEGER,
    modification_number             TEXT,

    federal_action_obligation       NUMERIC(20, 2) NOT NULL,
    current_total_value             NUMERIC(20, 2),
    potential_total_value           NUMERIC(20, 2),

    transaction_description         TEXT,

    naics_code                      TEXT,
    psc_code                        TEXT,

    source_file                     TEXT,
    source_row_number               BIGINT,
    created_at                      TIMESTAMP WITHOUT TIME ZONE NOT NULL
                                    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_procurement_transaction_usaspending_id
        UNIQUE (usaspending_transaction_id),

    CONSTRAINT fk_procurement_transaction_award
        FOREIGN KEY (award_id)
        REFERENCES procurement.award(award_id),

    CONSTRAINT fk_procurement_transaction_load_batch
        FOREIGN KEY (load_batch_id)
        REFERENCES procurement.load_batch(load_batch_id),

    CONSTRAINT fk_procurement_transaction_naics
        FOREIGN KEY (naics_code)
        REFERENCES procurement.naics(naics_code),

    CONSTRAINT fk_procurement_transaction_psc
        FOREIGN KEY (psc_code)
        REFERENCES procurement.psc(psc_code),

    CONSTRAINT ck_procurement_transaction_fiscal_year
        CHECK (fiscal_year BETWEEN 1900 AND 2200),

    CONSTRAINT ck_procurement_transaction_fiscal_quarter
        CHECK (
            fiscal_quarter IS NULL
            OR fiscal_quarter BETWEEN 1 AND 4
        ),

    CONSTRAINT ck_procurement_transaction_source_row
        CHECK (
            source_row_number IS NULL
            OR source_row_number > 0
        )
);

CREATE INDEX IF NOT EXISTS idx_procurement_transaction_award
    ON procurement.award_transaction (award_id);

CREATE INDEX IF NOT EXISTS idx_procurement_transaction_fiscal_year
    ON procurement.award_transaction (fiscal_year);

CREATE INDEX IF NOT EXISTS idx_procurement_transaction_action_date
    ON procurement.award_transaction (action_date);

CREATE INDEX IF NOT EXISTS idx_procurement_transaction_naics
    ON procurement.award_transaction (naics_code);

CREATE INDEX IF NOT EXISTS idx_procurement_transaction_psc
    ON procurement.award_transaction (psc_code);

CREATE INDEX IF NOT EXISTS idx_procurement_transaction_load_batch
    ON procurement.award_transaction (load_batch_id);

COMMENT ON TABLE procurement.award_transaction IS
    'USAspending procurement financial actions, including positive obligations and negative deobligations.';

COMMENT ON COLUMN procurement.award_transaction.federal_action_obligation IS
    'Change in obligated amount associated with the transaction. Negative values represent deobligations and must not be discarded.';


-- ============================================================================
-- PLACE OF PERFORMANCE
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.place_of_performance (
    place_of_performance_id          BIGSERIAL PRIMARY KEY,
    award_transaction_id             BIGINT NOT NULL,

    state_id                         BIGINT,
    county_id                        BIGINT,

    country_code                     TEXT,
    state_code                       TEXT,
    county_code                      TEXT,
    city_name                        TEXT,
    congressional_district           TEXT,
    zip_code                         TEXT,

    location_scope                   TEXT NOT NULL DEFAULT 'OBSERVED',
    created_at                       TIMESTAMP WITHOUT TIME ZONE NOT NULL
                                     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_procurement_place_transaction
        UNIQUE (award_transaction_id),

    CONSTRAINT fk_procurement_place_transaction
        FOREIGN KEY (award_transaction_id)
        REFERENCES procurement.award_transaction(award_transaction_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_procurement_place_state
        FOREIGN KEY (state_id)
        REFERENCES reference.state_registry(state_id),

    CONSTRAINT fk_procurement_place_county
        FOREIGN KEY (county_id)
        REFERENCES reference.county_registry(county_id),

    CONSTRAINT ck_procurement_place_scope
        CHECK (
            location_scope IN (
                'OBSERVED',
                'DERIVED_FROM_FIPS',
                'DERIVED_FROM_ZIP',
                'ALLOCATED',
                'UNRESOLVED'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_procurement_place_state
    ON procurement.place_of_performance (state_id);

CREATE INDEX IF NOT EXISTS idx_procurement_place_county
    ON procurement.place_of_performance (county_id);

CREATE INDEX IF NOT EXISTS idx_procurement_place_state_code
    ON procurement.place_of_performance (state_code);

CREATE INDEX IF NOT EXISTS idx_procurement_place_county_code
    ON procurement.place_of_performance (county_code);

COMMENT ON TABLE procurement.place_of_performance IS
    'Geographic place of performance associated with a procurement transaction.';

COMMENT ON COLUMN procurement.place_of_performance.location_scope IS
    'Documents whether geography was observed directly, derived, allocated, or unresolved.';


-- ============================================================================
-- RAW RECORD PRESERVATION
-- ============================================================================

CREATE TABLE IF NOT EXISTS procurement.raw_award_transaction (
    raw_award_transaction_id         BIGSERIAL PRIMARY KEY,
    load_batch_id                    BIGINT NOT NULL,
    source_row_number                BIGINT,
    raw_record                       JSONB NOT NULL,
    record_sha256                    TEXT,
    loaded_at                        TIMESTAMP WITHOUT TIME ZONE NOT NULL
                                     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_procurement_raw_load_batch
        FOREIGN KEY (load_batch_id)
        REFERENCES procurement.load_batch(load_batch_id),

    CONSTRAINT ck_procurement_raw_source_row
        CHECK (
            source_row_number IS NULL
            OR source_row_number > 0
        )
);

CREATE INDEX IF NOT EXISTS idx_procurement_raw_load_batch
    ON procurement.raw_award_transaction (load_batch_id);

CREATE INDEX IF NOT EXISTS idx_procurement_raw_record_gin
    ON procurement.raw_award_transaction
    USING GIN (raw_record);

COMMENT ON TABLE procurement.raw_award_transaction IS
    'Immutable raw USAspending source records preserved before normalization.';


COMMIT;