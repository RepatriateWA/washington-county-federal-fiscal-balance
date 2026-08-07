BEGIN;

ALTER TABLE procurement.recipient
    ADD COLUMN IF NOT EXISTS recipient_identity_key TEXT;

ALTER TABLE procurement.recipient
    ADD COLUMN IF NOT EXISTS recipient_identity_type TEXT;

ALTER TABLE procurement.recipient
    ADD COLUMN IF NOT EXISTS recipient_source_condition TEXT;

ALTER TABLE procurement.recipient
    ADD CONSTRAINT ck_recipient_identity_type
    CHECK (
        recipient_identity_type IS NULL
        OR recipient_identity_type IN (
            'UEI',
            'NAME_FINGERPRINT',
            'SOURCE_CONDITION'
        )
    );

ALTER TABLE procurement.recipient
    ADD CONSTRAINT ck_recipient_source_condition
    CHECK (
        recipient_source_condition IS NULL
        OR recipient_source_condition IN (
            'PII_REDACTED',
            'MULTIPLE_RECIPIENTS'
        )
    );

ALTER TABLE procurement.recipient
    ADD CONSTRAINT ck_recipient_source_condition_type
    CHECK (
        recipient_source_condition IS NULL
        OR recipient_identity_type = 'SOURCE_CONDITION'
    );

ALTER TABLE procurement.recipient
    ADD CONSTRAINT ck_recipient_identity_key_nonblank
    CHECK (
        recipient_identity_key IS NULL
        OR BTRIM(recipient_identity_key) <> ''
    );

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_recipient_identity_key
    ON procurement.recipient (
        recipient_identity_key
    )
    WHERE recipient_identity_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS
    idx_recipient_identity_type
    ON procurement.recipient (
        recipient_identity_type
    )
    WHERE recipient_identity_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS
    idx_recipient_source_condition
    ON procurement.recipient (
        recipient_source_condition
    )
    WHERE recipient_source_condition IS NOT NULL;

COMMENT ON COLUMN procurement.recipient.recipient_identity_key IS
    'Deterministic canonical recipient identity. Uses UEI when present, a source-derived fingerprint for named no-UEI recipients, or a special source-condition key.';

COMMENT ON COLUMN procurement.recipient.recipient_identity_type IS
    'Identity method: UEI, NAME_FINGERPRINT, or SOURCE_CONDITION.';

COMMENT ON COLUMN procurement.recipient.recipient_source_condition IS
    'Special source condition such as PII_REDACTED or MULTIPLE_RECIPIENTS; not an asserted legal entity identity.';

COMMIT;