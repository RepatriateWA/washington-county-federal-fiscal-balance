BEGIN;

ALTER TABLE va.gdx_county_expenditure
    ALTER COLUMN source_amount
    TYPE NUMERIC(30,15);

ALTER TABLE va.gdx_county_metric
    ALTER COLUMN source_value
    TYPE NUMERIC(30,15);

COMMENT ON COLUMN va.gdx_county_expenditure.source_amount IS
'Source numeric value as represented by the VA GDX workbook, retained at high precision before unit normalization to dollars.';

COMMENT ON COLUMN va.gdx_county_metric.source_value IS
'Source non-expenditure metric value from the VA GDX workbook, retained at high precision.';

COMMIT;