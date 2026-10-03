-- ================================================================================================
-- WCFFBP DRAFT 1D
-- MEDICARE ADVANTAGE DATA INVENTORY
-- READ ONLY
-- ================================================================================================

-- 1. Every CMS-related relation currently in PostgreSQL
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE
       table_schema ILIKE '%cms%'
    OR table_schema ILIKE '%medicare%'
    OR table_name ILIKE '%medicare%'
    OR table_name ILIKE '%advantage%'
    OR table_name ILIKE '%trustee%'
    OR table_name ILIKE '%private_health%'
    OR table_name ILIKE '%managed_care%'
ORDER BY
    table_schema,
    table_name;


-- 2. Columns in the raw Medicare Geographic Variation table
SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'cms_raw'
  AND table_name = 'medicare_geographic_variation'
ORDER BY ordinal_position;


-- 3. Columns in the finished Medicare state-year view
SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reporting'
  AND table_name = 'v_medicare_expenditures_by_state_year'
ORDER BY ordinal_position;


-- 4. Raw Washington Medicare observations
-- We first inspect rather than assume the raw table's geography fields.
SELECT *
FROM cms_raw.medicare_geographic_variation
LIMIT 20;