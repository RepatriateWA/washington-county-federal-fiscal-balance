BEGIN;

ALTER TABLE procurement.place
    ADD COLUMN IF NOT EXISTS place_identity_type TEXT;

ALTER TABLE procurement.place
    ADD COLUMN IF NOT EXISTS place_source_condition TEXT;

ALTER TABLE procurement.place
    ADD CONSTRAINT ck_place_identity_type
    CHECK (
        place_identity_type IS NULL
        OR place_identity_type IN (
            'GEOGRAPHIC_FINGERPRINT',
            'SOURCE_CONDITION'
        )
    );

ALTER TABLE procurement.place
    ADD CONSTRAINT ck_place_source_condition
    CHECK (
        place_source_condition IS NULL
        OR place_source_condition IN (
            'WASHINGTON_UNSPECIFIED'
        )
    );

ALTER TABLE procurement.place
    ADD CONSTRAINT ck_place_source_condition_type
    CHECK (
        place_source_condition IS NULL
        OR place_identity_type = 'SOURCE_CONDITION'
    );

ALTER TABLE procurement.place
    ADD CONSTRAINT ck_place_identity_key_nonblank
    CHECK (
        place_identity_key IS NULL
        OR BTRIM(place_identity_key) <> ''
    );

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_place_identity_key
    ON procurement.place (
        place_identity_key
    )
    WHERE place_identity_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS
    idx_place_identity_type
    ON procurement.place (
        place_identity_type
    )
    WHERE place_identity_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS
    idx_place_source_condition
    ON procurement.place (
        place_source_condition
    )
    WHERE place_source_condition IS NOT NULL;

COMMENT ON COLUMN procurement.place.place_identity_key IS
    'Deterministic shared place identity key. Uses a geographic fingerprint for resolved source geography or a special source-condition key when geography is not specified.';

COMMENT ON COLUMN procurement.place.place_identity_type IS
    'Identity method: GEOGRAPHIC_FINGERPRINT or SOURCE_CONDITION.';

COMMENT ON COLUMN procurement.place.place_source_condition IS
    'Special source condition such as WASHINGTON_UNSPECIFIED; does not assert statewide geographic scope.';

COMMIT;