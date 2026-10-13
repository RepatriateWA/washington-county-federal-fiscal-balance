
\set ON_ERROR_STOP on
\pset pager off

\echo '===================================================================='
\echo 'ETL-201Q STAGE E.1A - HISTORICAL TRANSACTION PRESERVATION BASELINE'
\echo 'READ ONLY - NO DATABASE WRITES OR SEQUENCE ADVANCEMENT'
\echo '===================================================================='

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET LOCAL statement_timeout = '600s';

\echo ''
\echo 'SECTION 1 - BASELINE IDENTIFICATION'

SELECT
    CURRENT_TIMESTAMP AS baseline_timestamp,
    CURRENT_DATABASE() AS database_name,
    CURRENT_USER AS database_user,
    current_setting('transaction_isolation') AS isolation_level,
    current_setting('transaction_read_only') AS read_only;

\echo ''
\echo 'SECTION 2 - CANONICAL TRANSACTION BASELINE'

SELECT
    COUNT(*) AS canonical_transaction_rows,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(*) FILTER (
        WHERE assistance_award_id IS NULL
    ) AS null_award_references,
    COUNT(*) FILTER (
        WHERE load_batch_id IN (20, 21)
    ) AS historical_batch_transactions
FROM assistance.award_transaction;

\echo ''
\echo 'SECTION 3 - OBSERVATION PROVENANCE BASELINE'

SELECT
    COUNT(*) AS observation_link_rows,
    COUNT(DISTINCT raw_assistance_transaction_id)
        AS distinct_raw_observations,
    COUNT(DISTINCT assistance_transaction_id)
        AS linked_canonical_transactions
FROM assistance.award_transaction_observation;

\echo ''
\echo 'SECTION 4 - HISTORICAL RAW POPULATION'

SELECT
    load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_award_keys
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo 'SECTION 5 - HISTORICAL ELIGIBILITY AND HELD POPULATION'

WITH eligibility AS (
    SELECT
        raw.load_batch_id,
        raw.raw_assistance_transaction_id,
        raw.assistance_award_unique_key,
        (
            EXISTS (
                SELECT 1
                FROM assistance.award award
                WHERE award.assistance_award_unique_key =
                      raw.assistance_award_unique_key
            )
            AND EXISTS (
                SELECT 1
                FROM assistance.assistance_listing listing
                WHERE listing.cfda_number =
                      BTRIM(raw.raw_record ->> 'cfda_number')
            )
            AND EXISTS (
                SELECT 1
                FROM assistance.assistance_type typ
                WHERE typ.assistance_type_code =
                      BTRIM(
                          raw.raw_record ->> 'assistance_type_code'
                      )
            )
        ) AS is_eligible
    FROM assistance.raw_award_transaction raw
    WHERE raw.load_batch_id IN (20, 21)
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(*) FILTER (WHERE is_eligible)
        AS eligible_observations,
    COUNT(*) FILTER (WHERE NOT is_eligible)
        AS held_observations,
    COUNT(DISTINCT assistance_award_unique_key)
        FILTER (WHERE NOT is_eligible)
        AS held_distinct_award_keys
FROM eligibility
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo 'SECTION 6 - HISTORICAL CANONICAL COLLISION BASELINE'

SELECT
    raw.load_batch_id,
    COUNT(*) AS existing_canonical_key_matches
FROM assistance.raw_award_transaction raw
JOIN assistance.award_transaction transaction
  ON transaction.assistance_transaction_unique_key =
     raw.assistance_transaction_unique_key
WHERE raw.load_batch_id IN (20, 21)
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

\echo ''
\echo 'SECTION 7 - HISTORICAL OBSERVATION-LINK BASELINE'

SELECT
    raw.load_batch_id,
    COUNT(*) AS existing_observation_links
FROM assistance.raw_award_transaction raw
JOIN assistance.award_transaction_observation observation
  ON observation.raw_assistance_transaction_id =
     raw.raw_assistance_transaction_id
WHERE raw.load_batch_id IN (20, 21)
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

\echo ''
\echo 'SECTION 8 - PRODUCTION TABLE CONSTRAINT INVENTORY'

SELECT
    cls.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS constraint_definition
FROM pg_constraint con
JOIN pg_class cls
  ON cls.oid = con.conrelid
JOIN pg_namespace ns
  ON ns.oid = cls.relnamespace
WHERE ns.nspname = 'assistance'
  AND cls.relname IN (
      'award_transaction',
      'award_transaction_observation'
  )
ORDER BY
    cls.relname,
    con.contype,
    con.conname;

\echo ''
\echo 'SECTION 9 - PRODUCTION INDEX INVENTORY'

SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'assistance'
  AND tablename IN (
      'award_transaction',
      'award_transaction_observation'
  )
ORDER BY tablename, indexname;

\echo ''
\echo 'SECTION 10 - PRODUCTION IDENTITY AND SEQUENCE METADATA'

SELECT
    ns.nspname AS schema_name,
    cls.relname AS table_name,
    att.attname AS column_name,
    att.attidentity AS identity_mode,
    pg_get_serial_sequence(
        format('%I.%I', ns.nspname, cls.relname),
        att.attname
    ) AS associated_sequence
FROM pg_class cls
JOIN pg_namespace ns
  ON ns.oid = cls.relnamespace
JOIN pg_attribute att
  ON att.attrelid = cls.oid
WHERE ns.nspname = 'assistance'
  AND cls.relname IN (
      'award_transaction',
      'award_transaction_observation'
  )
  AND att.attnum > 0
  AND NOT att.attisdropped
  AND (
      att.attidentity <> ''
      OR pg_get_serial_sequence(
          format('%I.%I', ns.nspname, cls.relname),
          att.attname
      ) IS NOT NULL
  )
ORDER BY cls.relname, att.attname;

\echo ''
\echo 'SECTION 11 - SEQUENCE STATE SNAPSHOT'

SELECT
    'assistance.award_transaction_assistance_transaction_id_seq'
        AS sequence_name,
    last_value,
    is_called
FROM assistance.award_transaction_assistance_transaction_id_seq;

SELECT
    'assistance.award_transaction_observation_award_transaction_observation_seq'
        AS sequence_name,
    last_value,
    is_called
FROM assistance.award_transaction_observation_award_transaction_observation_seq;

\echo ''
\echo 'SECTION 12 - FIELD POLICY BASELINE'

SELECT
    policy_version,
    field_class,
    COUNT(*) AS classified_fields
FROM assistance.transaction_field_policy
WHERE policy_version = 'ANALYSIS-162-v1'
GROUP BY policy_version, field_class
ORDER BY field_class;

\echo ''
\echo 'SECTION 13 - HISTORICAL BATCH REGISTRY'

SELECT *
FROM procurement.load_batch
WHERE load_batch_id IN (20, 21)
ORDER BY load_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE E.1A COMPLETE - READ ONLY'
