BEGIN;

-- =========================================================================
-- ETL-005B
-- Assistance-specific dimensions.
-- =========================================================================


-- -------------------------------------------------------------------------
-- Assistance Listing
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assistance.assistance_listing (
    assistance_listing_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cfda_number TEXT NOT NULL,
    cfda_title TEXT NOT NULL,
    cfda_title_normalized TEXT NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_assistance_listing_cfda_number
        UNIQUE (cfda_number)
);

COMMENT ON TABLE assistance.assistance_listing IS
    'Canonical Assistance Listing, formerly known as a CFDA program.';

COMMENT ON COLUMN assistance.assistance_listing.cfda_number IS
    'Assistance Listing number supplied in USAspending source data.';

COMMENT ON COLUMN assistance.assistance_listing.cfda_title IS
    'Canonical Assistance Listing title selected deterministically.';

COMMENT ON COLUMN assistance.assistance_listing.cfda_title_normalized IS
    'Normalized title used for comparison and alias detection.';


-- -------------------------------------------------------------------------
-- Assistance Type
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assistance.assistance_type (
    assistance_type_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    assistance_type_code TEXT NOT NULL,
    assistance_type_description TEXT NOT NULL,
    assistance_type_description_normalized TEXT NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_assistance_type_code
        UNIQUE (assistance_type_code)
);

COMMENT ON TABLE assistance.assistance_type IS
    'Canonical USAspending assistance type classification.';

COMMENT ON COLUMN assistance.assistance_type.assistance_type_code IS
    'USAspending assistance type code.';

COMMENT ON COLUMN assistance.assistance_type.assistance_type_description IS
    'Canonical assistance type description.';


-- -------------------------------------------------------------------------
-- Funding Opportunity
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assistance.funding_opportunity (
    funding_opportunity_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    funding_opportunity_number TEXT NOT NULL,
    funding_opportunity_goals_text TEXT,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_assistance_funding_opportunity_number
        UNIQUE (funding_opportunity_number)
);

COMMENT ON TABLE assistance.funding_opportunity IS
    'Canonical federal assistance funding opportunity.';

COMMENT ON COLUMN assistance.funding_opportunity.funding_opportunity_number IS
    'Funding opportunity number supplied by USAspending.';

COMMENT ON COLUMN assistance.funding_opportunity.funding_opportunity_goals_text IS
    'Canonical funding opportunity goals text, when supplied.';


-- -------------------------------------------------------------------------
-- Foreign keys from awards
-- -------------------------------------------------------------------------

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_listing
    FOREIGN KEY (assistance_listing_id)
    REFERENCES assistance.assistance_listing (
        assistance_listing_id
    );

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_type
    FOREIGN KEY (assistance_type_id)
    REFERENCES assistance.assistance_type (
        assistance_type_id
    );

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_funding_opportunity
    FOREIGN KEY (funding_opportunity_id)
    REFERENCES assistance.funding_opportunity (
        funding_opportunity_id
    );


-- -------------------------------------------------------------------------
-- Foreign keys from transactions
-- -------------------------------------------------------------------------

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_listing
    FOREIGN KEY (assistance_listing_id)
    REFERENCES assistance.assistance_listing (
        assistance_listing_id
    );

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_type
    FOREIGN KEY (assistance_type_id)
    REFERENCES assistance.assistance_type (
        assistance_type_id
    );

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_funding_opportunity
    FOREIGN KEY (funding_opportunity_id)
    REFERENCES assistance.funding_opportunity (
        funding_opportunity_id
    );


-- -------------------------------------------------------------------------
-- Supporting indexes
-- -------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_assistance_listing_title_normalized
    ON assistance.assistance_listing (
        cfda_title_normalized
    );

CREATE INDEX IF NOT EXISTS idx_assistance_type_description_normalized
    ON assistance.assistance_type (
        assistance_type_description_normalized
    );

CREATE INDEX IF NOT EXISTS idx_assistance_award_listing
    ON assistance.award (
        assistance_listing_id
    )
    WHERE assistance_listing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_award_type
    ON assistance.award (
        assistance_type_id
    )
    WHERE assistance_type_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_award_funding_opportunity
    ON assistance.award (
        funding_opportunity_id
    )
    WHERE funding_opportunity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_listing
    ON assistance.award_transaction (
        assistance_listing_id
    )
    WHERE assistance_listing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_type
    ON assistance.award_transaction (
        assistance_type_id
    )
    WHERE assistance_type_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_funding_opportunity
    ON assistance.award_transaction (
        funding_opportunity_id
    )
    WHERE funding_opportunity_id IS NOT NULL;

COMMIT;