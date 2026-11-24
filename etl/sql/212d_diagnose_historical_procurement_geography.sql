
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212D - HISTORICAL PROCUREMENT GEOGRAPHY DIAGNOSTIC'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. CANONICAL TRANSACTIONS BY BATCH'

SELECT
    fiscal_year,
    load_batch_id,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation), 2)
        AS net_obligations
FROM procurement.award_transaction
WHERE fiscal_year IN (2018, 2019)
GROUP BY fiscal_year, load_batch_id
ORDER BY fiscal_year, load_batch_id;

\echo ''
\echo '2. GEOGRAPHIC LINKAGE BY BATCH'

SELECT
    t.fiscal_year,
    t.load_batch_id,
    COUNT(*) AS transactions,
    COUNT(p.award_transaction_id)
        AS place_link_rows,
    COUNT(*) FILTER (
        WHERE p.award_transaction_id IS NULL
    ) AS missing_place_links,
    ROUND(
        COALESCE(
            SUM(t.federal_action_obligation) FILTER (
                WHERE p.award_transaction_id IS NULL
            ), 0
        ), 2
    ) AS unlinked_net_obligations
FROM procurement.award_transaction t
LEFT JOIN procurement.place_of_performance p
  ON p.award_transaction_id = t.award_transaction_id
WHERE t.fiscal_year IN (2018, 2019)
GROUP BY t.fiscal_year, t.load_batch_id
ORDER BY t.fiscal_year, t.load_batch_id;

\echo ''
\echo '3. RAW AND OBSERVATION COUNTS BY BATCH'

SELECT
    r.load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(o.award_transaction_id)
        AS observation_links,
    COUNT(DISTINCT o.award_transaction_id)
        AS distinct_canonical_transactions
FROM procurement.raw_award_transaction r
LEFT JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id =
     r.raw_award_transaction_id
WHERE r.load_batch_id IN (20, 21, 22, 23)
GROUP BY r.load_batch_id
ORDER BY r.load_batch_id;

\echo ''
\echo '4. RAW GEOGRAPHIC SOURCE COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'raw_award_transaction'
  AND (
      column_name ILIKE '%place%'
      OR column_name ILIKE '%state%'
      OR column_name ILIKE '%county%'
      OR column_name ILIKE '%city%'
      OR column_name ILIKE '%zip%'
      OR column_name ILIKE '%location%'
      OR column_name ILIKE '%performance%'
      OR column_name ILIKE '%payload%'
      OR column_name ILIKE '%raw%'
  )
ORDER BY ordinal_position;

\echo ''
\echo '5. PROCUREMENT BATCH METADATA COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'load_batch'
ORDER BY ordinal_position;

\echo ''
\echo '6. EXISTING GEOGRAPHY LINKAGE TABLE COUNTS'

SELECT
    'place' AS table_name,
    COUNT(*) AS rows
FROM procurement.place

UNION ALL

SELECT
    'place_of_performance',
    COUNT(*)
FROM procurement.place_of_performance;

ROLLBACK;

\echo ''
\echo 'ETL-212D COMPLETE - NO DATABASE WRITES'
