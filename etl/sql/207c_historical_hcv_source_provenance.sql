\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-207C - HISTORICAL HCV SOURCE PROVENANCE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo '=== 1. HISTORICAL HCV LINKAGE COMPLETENESS ==='

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE assistance_award_id IS NOT NULL
    ) AS linked_awards,
    COUNT(*) FILTER (
        WHERE recipient_id IS NOT NULL
    ) AS linked_recipients,
    COUNT(*) FILTER (
        WHERE place_of_performance_id IS NOT NULL
    ) AS linked_places,
    COUNT(*) FILTER (
        WHERE awarding_agency_id IS NOT NULL
    ) AS linked_awarding_agencies,
    COUNT(*) FILTER (
        WHERE funding_agency_id IS NOT NULL
    ) AS linked_funding_agencies,
    COUNT(*) FILTER (
        WHERE assistance_listing_id IS NOT NULL
    ) AS linked_listings
FROM analysis.v_certified_assistance_ledger
WHERE TRIM(cfda_number) = '14.871'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY 1
ORDER BY 1;

\echo '=== 2. SOURCE BATCH METADATA TABLE DISCOVERY ==='

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
AND (
       table_name ILIKE '%load_batch%'
    OR table_name ILIKE '%raw_award%'
    OR table_name ILIKE '%raw_transaction%'
    OR table_name ILIKE '%assistance%'
)
ORDER BY table_schema, table_name;

\echo '=== 3. HISTORICAL SOURCE GEOGRAPHY FIELDS ==='

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
AND (
       column_name ILIKE '%state%'
    OR column_name ILIKE '%recipient%'
    OR column_name ILIKE '%place_of_performance%'
    OR column_name ILIKE '%source_file%'
    OR column_name ILIKE '%archive%'
)
AND (
       table_name ILIKE '%assistance%'
    OR table_name ILIKE '%load_batch%'
)
ORDER BY table_schema, table_name, ordinal_position;

COMMIT;

\echo 'ETL-207C READ-ONLY PROFILE COMPLETE'