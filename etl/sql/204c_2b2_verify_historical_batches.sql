
-- =====================================================================
-- WCFFBP / ETL-204C-2B.2
-- HISTORICAL USASPENDING ASSISTANCE VERIFICATION
--
-- Reconstructed: 2026-10-13
-- Mode: READ ONLY
-- Target: FY2018 and FY2019
--
-- Expected ETL-201Q eligible populations:
--   FY2018 / batch 20: 100426
--   FY2019 / batch 21: 106917
--
-- No persistent database writes.
-- No accounting or inclusion-policy changes.
-- =====================================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT repeat('=', 78);
SELECT 'ETL-204C-2B.2 - HISTORICAL ASSISTANCE VERIFICATION';
SELECT 'READ ONLY - NO DATABASE WRITES';

-- ---------------------------------------------------------------------
-- 1. Database and session identity
-- ---------------------------------------------------------------------

SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('transaction_read_only') AS read_only,
    current_setting('server_version') AS postgres_version;

-- ---------------------------------------------------------------------
-- 2. Expected historical ingestion controls
-- ---------------------------------------------------------------------

SELECT *
FROM (
    VALUES
        (2018, 20, 100426),
        (2019, 21, 106917)
) AS expected(
    fiscal_year,
    load_batch_id,
    expected_eligible_transactions
);

-- ---------------------------------------------------------------------
-- 3. Required relation existence
-- ---------------------------------------------------------------------

WITH required(schema_name, relation_name) AS (
    VALUES
        ('assistance', 'award_transaction'),
        ('assistance', 'award_transaction_observation'),
        ('analysis', 'v_certified_assistance_ledger')
)
SELECT
    schema_name,
    relation_name,
    to_regclass(
        format('%I.%I', schema_name, relation_name)
    ) IS NOT NULL AS exists_in_database
FROM required
ORDER BY schema_name, relation_name;

-- ---------------------------------------------------------------------
-- 4. Discover historical batch metadata tables
-- ---------------------------------------------------------------------

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
AND (
    table_name ILIKE '%batch%'
    OR table_name ILIKE '%load%'
)
ORDER BY table_schema, table_name;

-- ---------------------------------------------------------------------
-- 5. Inspect columns used by historical ETL
-- ---------------------------------------------------------------------

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (
        table_schema = 'assistance'
        AND table_name IN (
            'award_transaction',
            'award_transaction_observation'
        )
    )
    OR (
        table_schema = 'analysis'
        AND table_name = 'v_certified_assistance_ledger'
    )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;

-- ---------------------------------------------------------------------
-- 6. Canonical transaction counts by historical batch
--
-- Execute only when the relation and load_batch_id exist.
-- ---------------------------------------------------------------------

SELECT
    CASE
        WHEN to_regclass(
            'assistance.award_transaction'
        ) IS NULL
        THEN 'MISSING_RELATION'
        WHEN NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'assistance'
              AND table_name = 'award_transaction'
              AND column_name = 'load_batch_id'
        )
        THEN 'MISSING_LOAD_BATCH_ID'
        ELSE 'READY'
    END AS canonical_query_readiness;

SELECT
    CASE
        WHEN to_regclass(
            'assistance.award_transaction_observation'
        ) IS NULL
        THEN 'MISSING_RELATION'
        WHEN NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'assistance'
              AND table_name = 'award_transaction_observation'
              AND column_name = 'load_batch_id'
        )
        THEN 'MISSING_LOAD_BATCH_ID'
        ELSE 'READY'
    END AS observation_query_readiness;

-- The following commands generate and execute queries only
-- when the relevant columns exist.

SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'assistance'
          AND table_name = 'award_transaction'
          AND column_name = 'load_batch_id'
    )
    THEN
        'SELECT load_batch_id, COUNT(*) AS transaction_rows '
        || 'FROM assistance.award_transaction '
        || 'WHERE load_batch_id IN (20,21) '
        || 'GROUP BY load_batch_id '
        || 'ORDER BY load_batch_id;'
    ELSE
        'SELECT ''Canonical batch count unavailable: '
        || 'missing load_batch_id'' AS diagnostic;'
END AS generated_sql
\gexec

-- ---------------------------------------------------------------------
-- 7. Observation provenance by batch
-- ---------------------------------------------------------------------

SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'assistance'
          AND table_name = 'award_transaction_observation'
          AND column_name = 'load_batch_id'
    )
    THEN
        'SELECT load_batch_id, COUNT(*) AS observation_rows '
        || 'FROM assistance.award_transaction_observation '
        || 'WHERE load_batch_id IN (20,21) '
        || 'GROUP BY load_batch_id '
        || 'ORDER BY load_batch_id;'
    ELSE
        'SELECT ''Observation batch count unavailable: '
        || 'missing load_batch_id'' AS diagnostic;'
END AS generated_sql
\gexec

-- ---------------------------------------------------------------------
-- 8. Fiscal-year coverage in canonical transactions
-- ---------------------------------------------------------------------

SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'assistance'
          AND table_name = 'award_transaction'
          AND column_name = 'fiscal_year'
    )
    THEN
        'SELECT fiscal_year, COUNT(*) AS transaction_rows '
        || 'FROM assistance.award_transaction '
        || 'WHERE fiscal_year BETWEEN 2018 AND 2024 '
        || 'GROUP BY fiscal_year '
        || 'ORDER BY fiscal_year;'
    ELSE
        'SELECT ''Canonical fiscal-year column not found'' '
        || 'AS diagnostic;'
END AS generated_sql
\gexec

-- ---------------------------------------------------------------------
-- 9. Certified ledger fiscal-year coverage
-- ---------------------------------------------------------------------

SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'analysis'
          AND table_name = 'v_certified_assistance_ledger'
          AND column_name = 'fiscal_year'
    )
    THEN
        'SELECT fiscal_year, COUNT(*) AS certified_rows '
        || 'FROM analysis.v_certified_assistance_ledger '
        || 'WHERE fiscal_year BETWEEN 2018 AND 2024 '
        || 'GROUP BY fiscal_year '
        || 'ORDER BY fiscal_year;'
    ELSE
        'SELECT ''Certified ledger fiscal-year column '
        || 'not found'' AS diagnostic;'
END AS generated_sql
\gexec

-- ---------------------------------------------------------------------
-- 10. Railroad Retirement column discovery
-- ---------------------------------------------------------------------

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE (
    table_schema = 'assistance'
    AND table_name = 'award_transaction'
)
OR (
    table_schema = 'analysis'
    AND table_name = 'v_certified_assistance_ledger'
)
AND (
    column_name ILIKE '%assistance%'
    OR column_name ILIKE '%listing%'
    OR column_name ILIKE '%cfda%'
    OR column_name ILIKE '%amount%'
)
ORDER BY
    table_schema,
    table_name,
    ordinal_position;

-- ---------------------------------------------------------------------
-- 11. Inspect certified ledger view definition
-- ---------------------------------------------------------------------

SELECT
    pg_get_viewdef(
        'analysis.v_certified_assistance_ledger'::regclass,
        true
    ) AS certified_ledger_definition
WHERE to_regclass(
    'analysis.v_certified_assistance_ledger'
) IS NOT NULL;

-- ---------------------------------------------------------------------
-- 12. Final transaction state
-- ---------------------------------------------------------------------

SELECT
    current_setting('transaction_read_only') AS read_only,
    'Verification completed' AS diagnostic_status;

COMMIT;

SELECT 'ETL-204C-2B.2 COMPLETE - NO DATABASE WRITES';
