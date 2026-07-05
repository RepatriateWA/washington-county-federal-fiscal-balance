ALTER TABLE irs.county_income_tax
ADD COLUMN IF NOT EXISTS income_tax_amount BIGINT,
ADD COLUMN IF NOT EXISTS total_tax_liability_amount BIGINT,
ADD COLUMN IF NOT EXISTS total_tax_payments_amount BIGINT,
ADD COLUMN IF NOT EXISTS overpayments_refunded_amount BIGINT;