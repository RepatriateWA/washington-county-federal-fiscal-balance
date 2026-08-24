-- 136_profile_va_procurement_fy2024.sql
--
-- Purpose:
--   Identify candidate USAspending procurement tables and the columns
--   available for FY2024 VA procurement decomposition.
--
-- Methodological status:
--   DISCOVERY ONLY. No ledger inclusion/exclusion decisions are made here.

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE
       lower(column_name) LIKE '%psc%'
    OR lower(column_name) LIKE '%product%service%'
    OR lower(column_name) LIKE '%naics%'
    OR lower(column_name) LIKE '%obligation%'
    OR lower(column_name) LIKE '%outlay%'
    OR lower(column_name) LIKE '%action_date%'
    OR lower(column_name) LIKE '%fiscal_year%'
    OR lower(column_name) LIKE '%awarding_agency%'
    OR lower(column_name) LIKE '%funding_agency%'
    OR lower(column_name) LIKE '%recipient%'
    OR lower(column_name) LIKE '%place_of_performance%'
    OR lower(column_name) LIKE '%description%'
ORDER BY
    table_schema,
    table_name,
    ordinal_position;