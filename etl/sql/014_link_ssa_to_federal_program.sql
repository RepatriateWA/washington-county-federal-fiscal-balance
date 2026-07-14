ALTER TABLE reference.ssa_benefit_type
    ADD COLUMN IF NOT EXISTS federal_program_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_ssa_benefit_type_federal_program'
    ) THEN
        ALTER TABLE reference.ssa_benefit_type
            ADD CONSTRAINT fk_ssa_benefit_type_federal_program
            FOREIGN KEY (federal_program_id)
            REFERENCES reference.federal_program(federal_program_id);
    END IF;
END
$$;

UPDATE reference.ssa_benefit_type sbt
SET federal_program_id = fp.federal_program_id
FROM reference.federal_program fp
WHERE
    (
        sbt.benefit_type_code IN (
            'RETIRED_WORKERS',
            'RETIRED_SPOUSES',
            'RETIRED_CHILDREN'
        )
        AND fp.program_code = 'OASDI_RETIREMENT'
    )
    OR
    (
        sbt.benefit_type_code IN (
            'SURVIVOR_WIDOWERS_PARENTS',
            'SURVIVOR_CHILDREN'
        )
        AND fp.program_code = 'OASDI_SURVIVORS'
    )
    OR
    (
        sbt.benefit_type_code IN (
            'DISABLED_WORKERS',
            'DISABLED_SPOUSES',
            'DISABLED_CHILDREN'
        )
        AND fp.program_code = 'OASDI_DISABILITY'
    );

-- TOTAL intentionally remains NULL because it combines several OASDI programs
-- and must not be double-counted with the detailed program rows.

CREATE INDEX IF NOT EXISTS idx_ssa_benefit_type_program
    ON reference.ssa_benefit_type(federal_program_id);


ALTER TABLE ssa.benefit_payments
    ADD COLUMN IF NOT EXISTS federal_program_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_ssa_benefit_payments_federal_program'
    ) THEN
        ALTER TABLE ssa.benefit_payments
            ADD CONSTRAINT fk_ssa_benefit_payments_federal_program
            FOREIGN KEY (federal_program_id)
            REFERENCES reference.federal_program(federal_program_id);
    END IF;
END
$$;

UPDATE ssa.benefit_payments bp
SET federal_program_id = sbt.federal_program_id
FROM reference.ssa_benefit_type sbt
WHERE bp.ssa_benefit_type_id = sbt.ssa_benefit_type_id;

CREATE INDEX IF NOT EXISTS idx_ssa_benefit_payments_program
    ON ssa.benefit_payments(federal_program_id);