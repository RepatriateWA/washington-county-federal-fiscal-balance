-- Preserves every recipient-to-parent relationship observed in each
-- USAspending source batch while procurement.recipient retains one
-- deterministic canonical parent relationship.

CREATE TABLE IF NOT EXISTS
    procurement.recipient_parent_relationship (
        load_batch_id BIGINT NOT NULL
            REFERENCES procurement.load_batch(load_batch_id),

        recipient_uei TEXT NOT NULL,

        parent_uei TEXT NOT NULL,

        observed_parent_name TEXT,

        occurrence_count BIGINT NOT NULL,

        first_action_date DATE,
        last_action_date DATE,

        first_source_row_number BIGINT NOT NULL,
        last_source_row_number BIGINT NOT NULL,

        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
            DEFAULT CURRENT_TIMESTAMP,

        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
            DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT pk_procurement_recipient_parent_relationship
            PRIMARY KEY (
                load_batch_id,
                recipient_uei,
                parent_uei
            ),

        CONSTRAINT
            ck_procurement_recipient_parent_relationship_count
            CHECK (occurrence_count > 0),

        CONSTRAINT
            ck_procurement_recipient_parent_relationship_dates
            CHECK (
                first_action_date IS NULL
                OR last_action_date IS NULL
                OR first_action_date <= last_action_date
            ),

        CONSTRAINT
            ck_procurement_recipient_parent_relationship_rows
            CHECK (
                first_source_row_number > 0
                AND last_source_row_number
                    >= first_source_row_number
            )
    );


CREATE INDEX IF NOT EXISTS
    idx_procurement_recipient_parent_relationship_recipient
ON procurement.recipient_parent_relationship (
    recipient_uei
);


CREATE INDEX IF NOT EXISTS
    idx_procurement_recipient_parent_relationship_parent
ON procurement.recipient_parent_relationship (
    parent_uei
);


CREATE INDEX IF NOT EXISTS
    idx_procurement_recipient_parent_relationship_dates
ON procurement.recipient_parent_relationship (
    first_action_date,
    last_action_date
);


COMMENT ON TABLE
    procurement.recipient_parent_relationship IS
    'Recipient-to-parent UEI relationships observed in individual '
    'USAspending source batches.';


COMMENT ON COLUMN
    procurement.recipient_parent_relationship.occurrence_count IS
    'Number of source rows in the load batch containing this exact '
    'recipient-to-parent UEI relationship.';


COMMENT ON COLUMN
    procurement.recipient_parent_relationship.observed_parent_name IS
    'Most recent nonblank parent name observed for this relationship '
    'within the source batch.';