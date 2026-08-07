BEGIN;

CREATE TABLE IF NOT EXISTS reference.extraordinary_funding_code (
    extraordinary_funding_code_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    defc_code TEXT NOT NULL,

    official_description TEXT NOT NULL,
    public_law_reference TEXT,

    funding_family TEXT NOT NULL,

    extraordinary_flag BOOLEAN,
    covid_flag BOOLEAN NOT NULL,
    iija_flag BOOLEAN NOT NULL,

    confidence TEXT NOT NULL,

    classification_source TEXT NOT NULL,
    citation TEXT NOT NULL,
    notes TEXT,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_extraordinary_funding_code_defc
        UNIQUE (defc_code),

    CONSTRAINT ck_extraordinary_funding_code_family
        CHECK (
            funding_family IN (
                'COVID',
                'IIJA',
                'OTHER_DISASTER',
                'WILDFIRE_SUPPRESSION',
                'OTHER_EMERGENCY',
                'NOT_DESIGNATED',
                'UNSPECIFIED_NON_COVID',
                'ORDINARY',
                'UNRESOLVED'
            )
        ),

    CONSTRAINT ck_extraordinary_funding_code_confidence
        CHECK (
            confidence IN (
                'HIGH',
                'MEDIUM',
                'LOW',
                'UNRESOLVED',
                'HIGH_NON_COVID'
            )
        ),

    CONSTRAINT ck_extraordinary_funding_code_covid_family
        CHECK (
            covid_flag = FALSE
            OR funding_family = 'COVID'
        ),

    CONSTRAINT ck_extraordinary_funding_code_iija_family
        CHECK (
            iija_flag = FALSE
            OR funding_family = 'IIJA'
        ),

    CONSTRAINT ck_extraordinary_funding_code_not_both
        CHECK (
            NOT (
                covid_flag = TRUE
                AND iija_flag = TRUE
            )
        ),

    CONSTRAINT ck_extraordinary_funding_code_citation
        CHECK (
            BTRIM(citation) <> ''
        )
);

COMMENT ON TABLE reference.extraordinary_funding_code IS
    'Citation-backed classification of Disaster Emergency Fund Codes used across federal expenditure domains.';

COMMENT ON COLUMN reference.extraordinary_funding_code.defc_code IS
    'Official Disaster Emergency Fund Code.';

COMMENT ON COLUMN reference.extraordinary_funding_code.funding_family IS
    'Project analytical family such as COVID, IIJA, disaster, emergency, or not designated.';

COMMENT ON COLUMN reference.extraordinary_funding_code.extraordinary_flag IS
    'TRUE when classified as extraordinary funding, FALSE when not extraordinary, and NULL when unresolved.';

COMMENT ON COLUMN reference.extraordinary_funding_code.classification_source IS
    'Authoritative federal source supporting the classification.';

COMMENT ON COLUMN reference.extraordinary_funding_code.citation IS
    'Citation or source locator supporting the classification decision.';

CREATE INDEX IF NOT EXISTS idx_extraordinary_funding_code_family
    ON reference.extraordinary_funding_code (
        funding_family
    );

CREATE INDEX IF NOT EXISTS idx_extraordinary_funding_code_covid
    ON reference.extraordinary_funding_code (
        covid_flag
    )
    WHERE covid_flag = TRUE;

CREATE INDEX IF NOT EXISTS idx_extraordinary_funding_code_iija
    ON reference.extraordinary_funding_code (
        iija_flag
    )
    WHERE iija_flag = TRUE;

COMMIT;