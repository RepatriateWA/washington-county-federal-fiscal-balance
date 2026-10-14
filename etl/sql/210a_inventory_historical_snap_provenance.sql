-- ============================================================
-- WCFFBP ETL-210A
-- HISTORICAL SNAP SOURCE-PROVENANCE INVENTORY
-- FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210A - HISTORICAL SNAP PROVENANCE INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ------------------------------------------------------------
-- 1. Source tables and views
-- ------------------------------------------------------------

\echo ''
\echo '1. ASSISTANCE SOURCE RELATIONS'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'assistance'
ORDER BY table_name;


-- ------------------------------------------------------------
-- 2. Raw transaction table schema
-- ------------------------------------------------------------

\echo ''
\echo '2. RAW TRANSACTION TABLE COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'raw_award_transaction'
ORDER BY ordinal_position;


-- ------------------------------------------------------------
-- 3. Normalized transaction table schema
-- ------------------------------------------------------------

\echo ''
\echo '3. NORMALIZED TRANSACTION TABLE COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'award_transaction'
ORDER BY ordinal_position;


-- ------------------------------------------------------------
-- 4. Award and recipient table schemas
-- ------------------------------------------------------------

\echo ''
\echo '4. AWARD AND RECIPIENT TABLE COLUMNS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name IN (
      'award',
      'award_recipient_history',
      'recipient_parent_history'
  )
ORDER BY table_name, ordinal_position;


-- ------------------------------------------------------------
-- 5. Certified ledger provenance fields
-- ------------------------------------------------------------

\echo ''
\echo '5. CERTIFIED LEDGER PROVENANCE COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name = 'v_certified_assistance_ledger'
ORDER BY ordinal_position;


-- ------------------------------------------------------------
-- 6. FY2018-FY2019 raw and normalized row inventory
-- Uses table statistics only; no assumed column names.
-- ------------------------------------------------------------

\echo ''
\echo '6. SOURCE RELATION SIZE ESTIMATES'

SELECT
    schemaname,
    relname,
    n_live_tup AS estimated_live_rows,
    last_analyze
FROM pg_stat_user_tables
WHERE schemaname = 'assistance'
  AND relname IN (
      'raw_award_transaction',
      'award_transaction',
      'award',
      'award_recipient_history'
  )
ORDER BY relname;


-- ------------------------------------------------------------
-- 7. Historical certified SNAP control
-- ------------------------------------------------------------

\echo ''
\echo '7. HISTORICAL SNAP CONTROL'

SELECT
    load_batch_id,
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE recipient_name IS NOT NULL
          AND BTRIM(recipient_name) <> ''
    ) AS recipient_names_present,
    COUNT(*) FILTER (
        WHERE performance_state_code IS NOT NULL
          AND BTRIM(performance_state_code) <> ''
    ) AS performance_states_present,
    COUNT(*) FILTER (
        WHERE performance_county_fips IS NOT NULL
          AND BTRIM(performance_county_fips) <> ''
    ) AS performance_counties_present,
    COUNT(*) FILTER (
        WHERE recipient_id IS NOT NULL
    ) AS recipient_ids_present,
    COUNT(*) FILTER (
        WHERE place_of_performance_id IS NOT NULL
    ) AS performance_ids_present,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
GROUP BY load_batch_id, action_date_fiscal_year
ORDER BY fiscal_year;


-- ------------------------------------------------------------
-- 8. Source control assertion
-- ------------------------------------------------------------

\echo ''
\echo '8. SOURCE CONTROL ASSERTION'

DO $$
DECLARE
    v_count bigint;
    v_net numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_net
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    IF v_count <> 27
       OR ROUND(v_net, 2) <> 2461253053.11
    THEN
        RAISE EXCEPTION
            'ETL-210A control failure: rows %, net %',
            v_count, v_net;
    END IF;

    RAISE NOTICE
        'ETL-210A PASS: 27 historical SNAP transactions, $2461253053.11 net';
END $$;

COMMIT;

\echo 'ETL-210A COMPLETE - READ ONLY'