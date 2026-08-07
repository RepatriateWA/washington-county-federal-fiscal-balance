BEGIN;

-- =========================================================================
-- ETL-005B
-- Link Assistance awards and transactions to established shared dimensions.
--
-- NOTE:
-- These dimensions currently reside in the procurement schema because they
-- were first created during procurement development. They are reused here
-- as canonical USAspending entities rather than duplicated.
-- =========================================================================


-- -------------------------------------------------------------------------
-- Load-batch provenance
-- -------------------------------------------------------------------------

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_load_batch
    FOREIGN KEY (load_batch_id)
    REFERENCES procurement.load_batch (
        load_batch_id
    );


-- -------------------------------------------------------------------------
-- Canonical recipients
-- -------------------------------------------------------------------------

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_recipient
    FOREIGN KEY (recipient_id)
    REFERENCES procurement.recipient (
        recipient_id
    );

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_recipient
    FOREIGN KEY (recipient_id)
    REFERENCES procurement.recipient (
        recipient_id
    );


-- -------------------------------------------------------------------------
-- Canonical agencies and subagencies
-- -------------------------------------------------------------------------

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_awarding_agency
    FOREIGN KEY (awarding_agency_id)
    REFERENCES procurement.agency (
        agency_id
    );

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_awarding_subagency
    FOREIGN KEY (awarding_subagency_id)
    REFERENCES procurement.agency (
        agency_id
    );

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_funding_agency
    FOREIGN KEY (funding_agency_id)
    REFERENCES procurement.agency (
        agency_id
    );

ALTER TABLE assistance.award
    ADD CONSTRAINT fk_assistance_award_funding_subagency
    FOREIGN KEY (funding_subagency_id)
    REFERENCES procurement.agency (
        agency_id
    );

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_awarding_agency
    FOREIGN KEY (awarding_agency_id)
    REFERENCES procurement.agency (
        agency_id
    );

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_awarding_subagency
    FOREIGN KEY (awarding_subagency_id)
    REFERENCES procurement.agency (
        agency_id
    );

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_funding_agency
    FOREIGN KEY (funding_agency_id)
    REFERENCES procurement.agency (
        agency_id
    );

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_funding_subagency
    FOREIGN KEY (funding_subagency_id)
    REFERENCES procurement.agency (
        agency_id
    );


-- -------------------------------------------------------------------------
-- Canonical place of performance
-- -------------------------------------------------------------------------

ALTER TABLE assistance.award_transaction
    ADD CONSTRAINT fk_assistance_transaction_place
    FOREIGN KEY (place_of_performance_id)
    REFERENCES procurement.place (
        place_id
    );


-- -------------------------------------------------------------------------
-- Supporting indexes for shared relationships
-- -------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_assistance_award_awarding_agency
    ON assistance.award (awarding_agency_id)
    WHERE awarding_agency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_award_awarding_subagency
    ON assistance.award (awarding_subagency_id)
    WHERE awarding_subagency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_award_funding_agency
    ON assistance.award (funding_agency_id)
    WHERE funding_agency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_award_funding_subagency
    ON assistance.award (funding_subagency_id)
    WHERE funding_subagency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_awarding_agency
    ON assistance.award_transaction (awarding_agency_id)
    WHERE awarding_agency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_awarding_subagency
    ON assistance.award_transaction (awarding_subagency_id)
    WHERE awarding_subagency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_funding_agency
    ON assistance.award_transaction (funding_agency_id)
    WHERE funding_agency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assistance_transaction_funding_subagency
    ON assistance.award_transaction (funding_subagency_id)
    WHERE funding_subagency_id IS NOT NULL;


-- -------------------------------------------------------------------------
-- Documentation
-- -------------------------------------------------------------------------

COMMENT ON COLUMN assistance.award.recipient_id IS
    'Canonical USAspending recipient from procurement.recipient.';

COMMENT ON COLUMN assistance.award.awarding_agency_id IS
    'Canonical top-tier awarding agency from procurement.agency.';

COMMENT ON COLUMN assistance.award.awarding_subagency_id IS
    'Canonical awarding subagency from procurement.agency.';

COMMENT ON COLUMN assistance.award.funding_agency_id IS
    'Canonical top-tier funding agency from procurement.agency.';

COMMENT ON COLUMN assistance.award.funding_subagency_id IS
    'Canonical funding subagency from procurement.agency.';

COMMENT ON COLUMN assistance.award_transaction.load_batch_id IS
    'Source-ingestion batch registered in procurement.load_batch.';

COMMENT ON COLUMN assistance.award_transaction.recipient_id IS
    'Canonical USAspending recipient from procurement.recipient.';

COMMENT ON COLUMN assistance.award_transaction.place_of_performance_id IS
    'Canonical place of performance from procurement.place.';

COMMIT;