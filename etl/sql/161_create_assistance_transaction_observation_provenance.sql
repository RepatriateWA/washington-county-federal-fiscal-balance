-- ============================================================================
-- ETL-161
-- Create Assistance transaction-observation provenance bridge
--
-- Purpose
-- -------
-- USAspending bulk-download snapshots may contain the same immutable
-- assistance transaction in multiple acquisition batches.
--
-- assistance.award_transaction represents the canonical transaction.
-- assistance.raw_award_transaction represents each immutable source
-- observation.
--
-- A canonical transaction therefore has a one-to-many relationship with
-- raw source observations.
--
-- This migration creates an explicit provenance bridge so repeated
-- observations do not need to overwrite or duplicate the canonical ledger.
--
-- Existing award_transaction.load_batch_id and source_row_number are retained
-- as FIRST-SEEN provenance for backward compatibility.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS assistance.award_transaction_observation (
    award_transaction_observation_id BIGSERIAL PRIMARY KEY,

    raw_assistance_transaction_id BIGINT NOT NULL,

    assistance_transaction_id BIGINT NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_assistance_transaction_observation_raw
        FOREIGN KEY (raw_assistance_transaction_id)
        REFERENCES assistance.raw_award_transaction (
            raw_assistance_transaction_id
        )
        ON DELETE RESTRICT,

    CONSTRAINT fk_assistance_transaction_observation_transaction
        FOREIGN KEY (assistance_transaction_id)
        REFERENCES assistance.award_transaction (
            assistance_transaction_id
        )
        ON DELETE RESTRICT,

    -- One immutable raw observation may describe only one canonical
    -- transaction.
    CONSTRAINT uq_assistance_transaction_observation_raw
        UNIQUE (raw_assistance_transaction_id)
);

CREATE INDEX IF NOT EXISTS
    idx_assistance_transaction_observation_transaction
ON assistance.award_transaction_observation (
    assistance_transaction_id
);

-- --------------------------------------------------------------------------
-- Backfill provenance for canonical transactions already in the database.
--
-- Existing award_transaction.load_batch_id + source_row_number represent the
-- source observation from which the canonical row was first created.
--
-- Include the USAspending transaction key in the join as a defensive
-- validation condition.
-- --------------------------------------------------------------------------

INSERT INTO assistance.award_transaction_observation (
    raw_assistance_transaction_id,
    assistance_transaction_id
)
SELECT
    r.raw_assistance_transaction_id,
    t.assistance_transaction_id
FROM assistance.award_transaction t
JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = t.load_batch_id
 AND r.source_row_number = t.source_row_number
 AND r.assistance_transaction_unique_key =
     t.assistance_transaction_unique_key
ON CONFLICT (raw_assistance_transaction_id) DO NOTHING;

-- --------------------------------------------------------------------------
-- Acceptance gate:
-- every existing canonical transaction must now have its original raw
-- observation represented in the provenance bridge.
-- --------------------------------------------------------------------------

DO $$
DECLARE
    canonical_count BIGINT;
    bridged_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO canonical_count
    FROM assistance.award_transaction;

    SELECT COUNT(DISTINCT o.assistance_transaction_id)
    INTO bridged_count
    FROM assistance.award_transaction_observation o;

    IF bridged_count <> canonical_count THEN
        RAISE EXCEPTION
            'ETL-161 backfill failed: canonical transactions %, bridged transactions %',
            canonical_count,
            bridged_count;
    END IF;
END
$$;

COMMIT;