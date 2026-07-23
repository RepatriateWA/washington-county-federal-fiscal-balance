-- ETL-004A.3E
-- Create canonical procurement agency dimension.

BEGIN;

CREATE TABLE IF NOT EXISTS procurement.agency (
    agency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agency_code VARCHAR(10),
    agency_name VARCHAR(255) NOT NULL,
    agency_name_normalized VARCHAR(255) NOT NULL,
    parent_agency_id BIGINT,
    agency_level VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_agency_level
        CHECK (agency_level IN ('AGENCY', 'SUBAGENCY')),

    CONSTRAINT fk_agency_parent
        FOREIGN KEY (parent_agency_id)
        REFERENCES procurement.agency(agency_id),

    CONSTRAINT ck_subagency_parent
        CHECK (
            (agency_level = 'AGENCY' AND parent_agency_id IS NULL)
            OR
            (agency_level = 'SUBAGENCY' AND parent_agency_id IS NOT NULL)
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_agency_code
    ON procurement.agency (agency_code)
    WHERE agency_code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_agency_name_only
    ON procurement.agency (agency_name_normalized, agency_level)
    WHERE agency_code IS NULL;

CREATE INDEX IF NOT EXISTS ix_agency_parent
    ON procurement.agency (parent_agency_id);

COMMIT;