-- Migration 113
-- Add canonical place linkage to procurement.place_of_performance.
--
-- This migration is intentionally non-destructive. Existing geographic
-- columns remain available for reconciliation until the new place_id
-- relationship has been fully validated.

BEGIN;

ALTER TABLE procurement.place_of_performance
    ADD COLUMN IF NOT EXISTS place_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_procurement_place_of_performance_place'
          AND conrelid =
              'procurement.place_of_performance'::regclass
    ) THEN
        ALTER TABLE procurement.place_of_performance
            ADD CONSTRAINT fk_procurement_place_of_performance_place
            FOREIGN KEY (place_id)
            REFERENCES procurement.place(place_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS
    idx_procurement_place_of_performance_place_id
ON procurement.place_of_performance(place_id);

COMMIT;