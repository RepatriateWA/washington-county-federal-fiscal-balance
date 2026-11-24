
-- ============================================================
-- WCFFBP ETL-204C-2B.5
-- HISTORICAL RAILROAD GEOGRAPHY PROVENANCE
-- READ ONLY
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT '1. RAW ASSISTANCE TABLE INVENTORY' AS section;

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'assistance'
  AND table_type = 'BASE TABLE'
  AND (
      table_name ILIKE '%raw%'
      OR table_name ILIKE '%source%'
      OR table_name ILIKE '%batch%'
  )
ORDER BY table_name;


SELECT '2. RAW AND OBSERVATION LINK COLUMNS'
    AS section;

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND (
      table_name ILIKE '%raw%'
      OR table_name = 'award_transaction_observation'
  )
ORDER BY table_name, ordinal_position;


SELECT '3. CANONICAL GEOGRAPHIC LINKAGE' AS section;

SELECT
    t.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE t.place_of_performance_id IS NOT NULL
    ) AS with_place_id,
    COUNT(*) FILTER (
        WHERE t.place_of_performance_id IS NULL
    ) AS without_place_id,
    COUNT(DISTINCT t.place_of_performance_id)
        AS distinct_place_ids,
    SUM(t.federal_action_obligation)
        AS net_obligations
FROM assistance.award_transaction t
JOIN assistance.assistance_listing al
    ON al.assistance_listing_id =
       t.assistance_listing_id
WHERE t.load_batch_id IN (20, 21)
  AND TRIM(al.cfda_number) = '57.001'
GROUP BY t.action_date_fiscal_year
ORDER BY t.action_date_fiscal_year;


SELECT '4. RECIPIENT AND SOURCE IDENTIFIERS'
    AS section;

SELECT
    v.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE v.recipient_id IS NOT NULL
    ) AS with_recipient_id,
    COUNT(*) FILTER (
        WHERE v.recipient_name IS NOT NULL
    ) AS with_recipient_name,
    COUNT(*) FILTER (
        WHERE v.usaspending_permalink IS NOT NULL
    ) AS with_permalink,
    COUNT(*) FILTER (
        WHERE v.award_id_fain IS NOT NULL
    ) AS with_fain
FROM analysis.v_certified_assistance_ledger v
WHERE v.load_batch_id IN (20, 21)
  AND TRIM(v.cfda_number) = '57.001'
GROUP BY v.action_date_fiscal_year
ORDER BY v.action_date_fiscal_year;


SELECT '5. REPRESENTATIVE SOURCE RECORDS' AS section;

SELECT
    v.action_date_fiscal_year,
    v.load_batch_id,
    v.source_row_number,
    v.assistance_transaction_id,
    v.assistance_award_unique_key,
    v.recipient_name,
    v.place_of_performance_id,
    v.performance_state_code,
    v.federal_action_obligation,
    v.usaspending_permalink
FROM analysis.v_certified_assistance_ledger v
WHERE v.load_batch_id IN (20, 21)
  AND TRIM(v.cfda_number) = '57.001'
ORDER BY
    v.action_date_fiscal_year,
    v.source_row_number
LIMIT 12;

COMMIT;

SELECT 'ETL-204C-2B.5 COMPLETE - NO DATABASE WRITES';
