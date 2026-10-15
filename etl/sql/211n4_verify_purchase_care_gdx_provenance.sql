
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211N4 - PURCHASE CARE / GDX PROVENANCE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. HISTORICAL GDX SOURCE BATCHES'

SELECT
    gdx_load_batch_id,
    fiscal_year,
    source_file,
    source_sha256,
    schema_regime,
    methodology_regime,
    methodology_break,
    load_status,
    source_county_rows,
    loaded_expenditure_rows,
    rejected_row_count,
    notes
FROM va.gdx_load_batch
WHERE fiscal_year IN (2018, 2019, 2020)
ORDER BY fiscal_year, gdx_load_batch_id;

\echo ''
\echo '2. MEDICAL CARE CATEGORY DEFINITION'

SELECT
    category_code,
    category_name,
    aggregation_role,
    first_fiscal_year,
    last_fiscal_year,
    description
FROM va.gdx_expenditure_category
WHERE category_code = 'MEDICAL_CARE';

\echo ''
\echo '3. HISTORICAL MEDICAL CARE SOURCE LINEAGE'

SELECT
    e.fiscal_year,
    e.gdx_load_batch_id,
    e.schema_regime,
    e.expenditure_class,
    e.source_category_name,
    e.source_unit,
    COUNT(*) AS rows,
    COUNT(DISTINCT e.county_id) AS counties,
    ROUND(SUM(e.expenditure_amount)::numeric, 2)
        AS expenditure_dollars
FROM va.gdx_county_expenditure e
JOIN va.gdx_expenditure_category k
  ON k.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year IN (2018, 2019)
  AND k.category_code = 'MEDICAL_CARE'
GROUP BY
    e.fiscal_year,
    e.gdx_load_batch_id,
    e.schema_regime,
    e.expenditure_class,
    e.source_category_name,
    e.source_unit
ORDER BY e.fiscal_year, e.gdx_load_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-211N4 COMPLETE - NO DATABASE WRITES'
