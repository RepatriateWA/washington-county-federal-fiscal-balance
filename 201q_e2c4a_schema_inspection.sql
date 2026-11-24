\pset pager off

\echo === CANONICAL TRANSACTION TABLE ===
\d+ assistance.award_transaction

\echo === PROVENANCE LINK TABLE ===
\d+ assistance.award_transaction_observation

\echo === CANONICAL TRANSACTION CONSTRAINTS ===
SELECT
    con.conname,
    con.contype,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.conrelid =
    'assistance.award_transaction'::regclass
ORDER BY con.conname;

\echo === PROVENANCE LINK CONSTRAINTS ===
SELECT
    con.conname,
    con.contype,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.conrelid =
    'assistance.award_transaction_observation'::regclass
ORDER BY con.conname;

\echo === IDENTITY AND DEFAULT DEFINITIONS ===
SELECT
    c.table_name,
    c.column_name,
    c.data_type,
    c.is_identity,
    c.identity_generation,
    c.column_default
FROM information_schema.columns AS c
WHERE c.table_schema = 'assistance'
  AND c.table_name IN (
      'award_transaction',
      'award_transaction_observation'
  )
ORDER BY c.table_name, c.ordinal_position;
