BEGIN;

-- =========================================================================
-- ETL-005D.3
-- Assistance recipient relationship history.
--
-- These tables preserve observed relationships independently from the
-- current canonical recipient selected on assistance.award.
-- =========================================================================


-- -------------------------------------------------------------------------
-- Award-recipient observation history
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assistance.award_recipient_history (
    award_recipient_history_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    load_batch_id BIGINT NOT NULL,
    source_row_number BIGINT NOT NULL,

    assistance_award_id BIGINT NOT NULL,
    assistance_transaction_id BIGINT NOT NULL,
    recipient_id BIGINT NOT NULL,

    action_date DATE,

    recipient_identity_key TEXT NOT NULL,

    selected_as_canonical_award_recipient BOOLEAN
        NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_assistance_award_recipient_history_source
        UNIQUE (
            load_batch_id,
            source_row_number
        ),

    CONSTRAINT fk_assistance_award_recipient_history_batch
        FOREIGN KEY (load_batch_id)
        REFERENCES procurement.load_batch (
            load_batch_id
        )
        ON DELETE RESTRICT,

    CONSTRAINT fk_assistance_award_recipient_history_award
        FOREIGN KEY (assistance_award_id)
        REFERENCES assistance.award (
            assistance_award_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fk_assistance_award_recipient_history_transaction
        FOREIGN KEY (assistance_transaction_id)
        REFERENCES assistance.award_transaction (
            assistance_transaction_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fk_assistance_award_recipient_history_recipient
        FOREIGN KEY (recipient_id)
        REFERENCES procurement.recipient (
            recipient_id
        )
        ON DELETE RESTRICT,

    CONSTRAINT ck_assistance_award_recipient_history_row_positive
        CHECK (
            source_row_number > 0
        ),

    CONSTRAINT ck_assistance_award_recipient_history_identity_nonblank
        CHECK (
            BTRIM(recipient_identity_key) <> ''
        )
);

COMMENT ON TABLE assistance.award_recipient_history IS
    'One preserved recipient observation per raw Assistance transaction row.';

COMMENT ON COLUMN assistance.award_recipient_history.selected_as_canonical_award_recipient IS
    'TRUE when this observation supplied the deterministic current recipient selected on assistance.award.';

CREATE INDEX IF NOT EXISTS
    idx_assistance_award_recipient_history_award
    ON assistance.award_recipient_history (
        assistance_award_id
    );

CREATE INDEX IF NOT EXISTS
    idx_assistance_award_recipient_history_transaction
    ON assistance.award_recipient_history (
        assistance_transaction_id
    );

CREATE INDEX IF NOT EXISTS
    idx_assistance_award_recipient_history_recipient
    ON assistance.award_recipient_history (
        recipient_id
    );

CREATE INDEX IF NOT EXISTS
    idx_assistance_award_recipient_history_canonical
    ON assistance.award_recipient_history (
        assistance_award_id
    )
    WHERE selected_as_canonical_award_recipient = TRUE;


-- -------------------------------------------------------------------------
-- Recipient-parent observation history
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assistance.recipient_parent_history (
    recipient_parent_history_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    load_batch_id BIGINT NOT NULL,
    source_row_number BIGINT NOT NULL,

    child_recipient_id BIGINT NOT NULL,

    parent_recipient_id BIGINT,
    observed_parent_uei TEXT,
    observed_parent_name TEXT,

    action_date DATE,

    is_self_parent BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_assistance_recipient_parent_history_source
        UNIQUE (
            load_batch_id,
            source_row_number
        ),

    CONSTRAINT fk_assistance_recipient_parent_history_batch
        FOREIGN KEY (load_batch_id)
        REFERENCES procurement.load_batch (
            load_batch_id
        )
        ON DELETE RESTRICT,

    CONSTRAINT fk_assistance_recipient_parent_history_child
        FOREIGN KEY (child_recipient_id)
        REFERENCES procurement.recipient (
            recipient_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fk_assistance_recipient_parent_history_parent
        FOREIGN KEY (parent_recipient_id)
        REFERENCES procurement.recipient (
            recipient_id
        )
        ON DELETE RESTRICT,

    CONSTRAINT ck_assistance_recipient_parent_history_row_positive
        CHECK (
            source_row_number > 0
        ),

    CONSTRAINT ck_assistance_recipient_parent_history_parent_observed
        CHECK (
            observed_parent_uei IS NOT NULL
            OR observed_parent_name IS NOT NULL
        ),

    CONSTRAINT ck_assistance_recipient_parent_history_self_consistent
        CHECK (
            is_self_parent = FALSE
            OR parent_recipient_id = child_recipient_id
        )
);

COMMENT ON TABLE assistance.recipient_parent_history IS
    'Observed Assistance recipient-parent relationships preserved by source row.';

COMMENT ON COLUMN assistance.recipient_parent_history.parent_recipient_id IS
    'Resolved canonical parent recipient when the parent can be identified safely; otherwise null while source values remain preserved.';

COMMENT ON COLUMN assistance.recipient_parent_history.is_self_parent IS
    'TRUE when the source reports the child recipient UEI as its own parent UEI.';

CREATE INDEX IF NOT EXISTS
    idx_assistance_recipient_parent_history_child
    ON assistance.recipient_parent_history (
        child_recipient_id
    );

CREATE INDEX IF NOT EXISTS
    idx_assistance_recipient_parent_history_parent
    ON assistance.recipient_parent_history (
        parent_recipient_id
    )
    WHERE parent_recipient_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS
    idx_assistance_recipient_parent_history_parent_uei
    ON assistance.recipient_parent_history (
        observed_parent_uei
    )
    WHERE observed_parent_uei IS NOT NULL;

COMMIT;