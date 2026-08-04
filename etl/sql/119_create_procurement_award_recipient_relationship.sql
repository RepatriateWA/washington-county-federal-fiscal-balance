-- Preserves every award-to-recipient relationship observed in each
-- USAspending source batch while procurement.award retains one
-- deterministic canonical recipient.

BEGIN;

CREATE TABLE IF NOT EXISTS
    procurement.award_recipient_relationship (
        load_batch_id BIGINT NOT NULL
            REFERENCES procurement.load_batch(load_batch_id),

        award_id BIGINT NOT NULL
            REFERENCES procurement.award(award_id)
            ON DELETE CASCADE,

        recipient_id BIGINT NOT NULL
            REFERENCES procurement.recipient(recipient_id),

        recipient_uei TEXT,

        observed_recipient_name TEXT,

        occurrence_count BIGINT NOT NULL,

        first_action_date DATE,
        last_action_date DATE,

        first_source_row_number BIGINT NOT NULL,
        last_source_row_number BIGINT NOT NULL,

        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
            DEFAULT CURRENT_TIMESTAMP,

        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
            DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT pk_procurement_award_recipient_relationship
            PRIMARY KEY (
                load_batch_id,
                award_id,
                recipient_id
            ),

        CONSTRAINT
            ck_procurement_award_recipient_relationship_count
            CHECK (occurrence_count > 0),

        CONSTRAINT
            ck_procurement_award_recipient_relationship_dates
            CHECK (
                first_action_date IS NULL
                OR last_action_date IS NULL
                OR first_action_date <= last_action_date
            ),

        CONSTRAINT
            ck_procurement_award_recipient_relationship_rows
            CHECK (
                first_source_row_number > 0
                AND last_source_row_number
                    >= first_source_row_number
            )
    );


CREATE INDEX IF NOT EXISTS
    idx_procurement_award_recipient_relationship_award
ON procurement.award_recipient_relationship (
    award_id
);


CREATE INDEX IF NOT EXISTS
    idx_procurement_award_recipient_relationship_recipient
ON procurement.award_recipient_relationship (
    recipient_id
);


CREATE INDEX IF NOT EXISTS
    idx_procurement_award_recipient_relationship_uei
ON procurement.award_recipient_relationship (
    recipient_uei
);


CREATE INDEX IF NOT EXISTS
    idx_procurement_award_recipient_relationship_dates
ON procurement.award_recipient_relationship (
    first_action_date,
    last_action_date
);


COMMENT ON TABLE
    procurement.award_recipient_relationship IS
    'Award-to-recipient relationships observed in individual '
    'USAspending source batches.';


COMMENT ON COLUMN
    procurement.award_recipient_relationship.occurrence_count IS
    'Number of source transactions in the load batch containing '
    'this exact award-to-recipient relationship.';


COMMENT ON COLUMN
    procurement.award_recipient_relationship.observed_recipient_name IS
    'Most recent nonblank recipient name observed for this '
    'award-to-recipient relationship within the source batch.';


COMMENT ON COLUMN
    procurement.award_recipient_relationship.recipient_uei IS
    'Recipient UEI preserved from the source for audit and '
    'reconciliation, even though recipient_id is the relational key.';

COMMIT;