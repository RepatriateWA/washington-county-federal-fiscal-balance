-- ============================================================================
-- ETL-133 — Federal Inflow Overlap-Control Framework
-- ============================================================================
--
-- Purpose
-- -------
-- Establish durable reference structures for:
--
--   1. classifying federal inflow programs across source systems; and
--   2. defining which source/accounting pathway may contribute each
--      expenditure family to the final federal fiscal-balance ledger.
--
-- Core invariant
-- --------------
-- Preservation of a source observation does NOT imply inclusion in the
-- fiscal-balance ledger.
--
-- No federal expenditure should contribute to the final Washington federal
-- inflow total more than once, regardless of how many source systems report it.
--
-- This migration creates reference/control structures only.
-- It does not alter existing procurement, assistance, SSA, VA, CMS,
-- Medicaid, CHIP, IRS, or analytical observations.
-- ============================================================================


BEGIN;


-- ============================================================================
-- 1. PROGRAM CLASSIFICATION
-- ============================================================================
--
-- Answers:
--
--     "What kind of federal inflow is this source program?"
--
-- One source-system/program-code combination may be classified differently
-- under a later methodology version without destroying prior methodology.
-- ============================================================================

CREATE TABLE IF NOT EXISTS reference.federal_inflow_program_classification (
    federal_inflow_program_classification_id BIGSERIAL PRIMARY KEY,

    source_system TEXT NOT NULL,
    source_program_code TEXT NOT NULL,
    source_program_title TEXT,

    inflow_family TEXT NOT NULL,
    inflow_subfamily TEXT,

    overlap_risk TEXT NOT NULL,

    covid_relevance BOOLEAN NOT NULL DEFAULT FALSE,
    extraordinary_relevance BOOLEAN NOT NULL DEFAULT FALSE,

    classification_basis TEXT NOT NULL,
    methodology_version TEXT NOT NULL,

    valid_from_fiscal_year INTEGER,
    valid_through_fiscal_year INTEGER,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_federal_inflow_program_overlap_risk
        CHECK (
            overlap_risk IN (
                'NONE',
                'LOW',
                'MODERATE',
                'HIGH',
                'KNOWN_OVERLAP'
            )
        ),

    CONSTRAINT ck_federal_inflow_program_fy_range
        CHECK (
            valid_from_fiscal_year IS NULL
            OR valid_through_fiscal_year IS NULL
            OR valid_from_fiscal_year <= valid_through_fiscal_year
        ),

    CONSTRAINT uq_federal_inflow_program_classification
        UNIQUE (
            source_system,
            source_program_code,
            methodology_version
        )
);


COMMENT ON TABLE
    reference.federal_inflow_program_classification
IS
    'Cross-source classification of federal inflow programs. '
    'Classifies what an expenditure represents without deciding whether '
    'that source is included in the final fiscal-balance ledger.';


COMMENT ON COLUMN
    reference.federal_inflow_program_classification.overlap_risk
IS
    'Risk that this program is represented in another federal expenditure '
    'source and could therefore be double counted.';


COMMENT ON COLUMN
    reference.federal_inflow_program_classification.classification_basis
IS
    'Auditable explanation for the program-family classification.';


-- ============================================================================
-- 2. SOURCE / ACCOUNTING POLICY
-- ============================================================================
--
-- Answers:
--
--     "How is this expenditure family allowed to enter the final ledger?"
--
-- This is intentionally separate from program classification.
-- Classification describes the expenditure.
-- Source policy describes the methodology used to account for it.
-- ============================================================================

CREATE TABLE IF NOT EXISTS reference.federal_inflow_source_policy (
    federal_inflow_source_policy_id BIGSERIAL PRIMARY KEY,

    inflow_family TEXT NOT NULL,
    inflow_subfamily TEXT,

    accounting_measure TEXT NOT NULL,

    preferred_source TEXT,
    allocation_source TEXT,

    overlapping_sources TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],

    ledger_treatment TEXT NOT NULL,

    source_selection_basis TEXT NOT NULL,
    methodology_version TEXT NOT NULL,

    valid_from_fiscal_year INTEGER,
    valid_through_fiscal_year INTEGER,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_federal_inflow_policy_treatment
        CHECK (
            ledger_treatment IN (
                'INCLUDE',
                'INCLUDE_AFTER_RECONCILIATION',
                'EXCLUDE_DUPLICATE',
                'ALLOCATE_ONLY',
                'SEPARATE_CREDIT_MEASURE',
                'SEPARATE_CONTINGENT_MEASURE',
                'REVIEW_REQUIRED'
            )
        ),

    CONSTRAINT ck_federal_inflow_policy_fy_range
        CHECK (
            valid_from_fiscal_year IS NULL
            OR valid_through_fiscal_year IS NULL
            OR valid_from_fiscal_year <= valid_through_fiscal_year
        )
);


COMMENT ON TABLE
    reference.federal_inflow_source_policy
IS
    'Methodological control table defining how each federal inflow family '
    'may contribute to the deduplicated fiscal-balance ledger.';


COMMENT ON COLUMN
    reference.federal_inflow_source_policy.preferred_source
IS
    'Preferred source for the authoritative accounting amount. NULL is '
    'permitted while source-selection methodology remains unresolved.';


COMMENT ON COLUMN
    reference.federal_inflow_source_policy.allocation_source
IS
    'Optional separate source used only to allocate an authoritative amount '
    'geographically; an allocation source does not itself add dollars.';


COMMENT ON COLUMN
    reference.federal_inflow_source_policy.overlapping_sources
IS
    'Other known source systems that may represent the same expenditure family.';


COMMENT ON COLUMN
    reference.federal_inflow_source_policy.ledger_treatment
IS
    'Controls whether and how this expenditure family is permitted to '
    'contribute to the final federal inflow ledger.';


-- ============================================================================
-- 3. INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS
    ix_federal_inflow_program_family
ON reference.federal_inflow_program_classification (
    inflow_family,
    inflow_subfamily
);


CREATE INDEX IF NOT EXISTS
    ix_federal_inflow_program_source
ON reference.federal_inflow_program_classification (
    source_system,
    source_program_code
);


CREATE INDEX IF NOT EXISTS
    ix_federal_inflow_program_overlap
ON reference.federal_inflow_program_classification (
    overlap_risk
);


CREATE INDEX IF NOT EXISTS
    ix_federal_inflow_source_policy_family
ON reference.federal_inflow_source_policy (
    inflow_family,
    inflow_subfamily
);


CREATE INDEX IF NOT EXISTS
    ix_federal_inflow_source_policy_treatment
ON reference.federal_inflow_source_policy (
    ledger_treatment
);


-- ============================================================================
-- 4. BASIC VALIDATION
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'reference'
          AND table_name = 'federal_inflow_program_classification'
    ) THEN
        RAISE EXCEPTION
            'reference.federal_inflow_program_classification was not created.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'reference'
          AND table_name = 'federal_inflow_source_policy'
    ) THEN
        RAISE EXCEPTION
            'reference.federal_inflow_source_policy was not created.';
    END IF;
END
$$;


COMMIT;