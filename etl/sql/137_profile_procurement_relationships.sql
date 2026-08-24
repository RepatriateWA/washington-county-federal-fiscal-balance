-- 137_profile_procurement_relationships.sql
--
-- Purpose:
--   Inspect the complete column structure of the core procurement tables
--   required for FY2024 VA procurement decomposition.
--
-- Methodological status:
--   DISCOVERY ONLY.
--   No classification or ledger treatment is performed.

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name IN (
      'award',
      'award_transaction',
      'agency',
      'place_of_performance',
      'psc',
      'naics'
  )
ORDER BY
    table_name,
    ordinal_position;