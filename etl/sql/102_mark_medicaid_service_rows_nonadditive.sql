BEGIN;

ALTER TABLE cms.medicaid_service_expenditures
    ADD COLUMN IF NOT EXISTS is_additive_to_control_total BOOLEAN;

UPDATE cms.medicaid_service_expenditures
SET is_additive_to_control_total = FALSE
WHERE is_additive_to_control_total IS NULL;

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN is_additive_to_control_total
    SET DEFAULT FALSE;

ALTER TABLE cms.medicaid_service_expenditures
    ALTER COLUMN is_additive_to_control_total
    SET NOT NULL;

COMMENT ON COLUMN
    cms.medicaid_service_expenditures.is_additive_to_control_total IS
    'False unless a future CMS-derived dimensional model proves that the '
    'row belongs to a mutually exclusive, collectively exhaustive set that '
    'reconciles to the official Medicaid state control total.';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medicaid_additive_rows_not_control_totals'
          AND conrelid =
              'cms.medicaid_service_expenditures'::regclass
    ) THEN
        ALTER TABLE cms.medicaid_service_expenditures
            ADD CONSTRAINT
                chk_medicaid_additive_rows_not_control_totals
            CHECK (
                NOT is_additive_to_control_total
                OR row_type IN ('DETAIL', 'ADJUSTMENT')
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS
    idx_medicaid_service_expenditure_additive
ON cms.medicaid_service_expenditures (
    fiscal_year,
    state_id,
    federal_program_id,
    is_additive_to_control_total
);

COMMIT;