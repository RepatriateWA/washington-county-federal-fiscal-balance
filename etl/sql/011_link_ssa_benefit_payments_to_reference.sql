ALTER TABLE ssa.benefit_payments
    ADD COLUMN IF NOT EXISTS ssa_benefit_type_id BIGINT;

ALTER TABLE ssa.benefit_payments
    ADD CONSTRAINT fk_ssa_benefit_type
    FOREIGN KEY (ssa_benefit_type_id)
    REFERENCES reference.ssa_benefit_type(ssa_benefit_type_id);

CREATE INDEX IF NOT EXISTS idx_ssa_benefit_payments_type_id
    ON ssa.benefit_payments(ssa_benefit_type_id);