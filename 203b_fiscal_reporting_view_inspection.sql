BEGIN TRANSACTION READ ONLY;

SELECT
    table_name AS view_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reporting'
  AND table_name IN (
      'v_federal_receipts_by_state_year',
      'v_federal_expenditures_by_state_year',
      'v_washington_partial_fiscal_balance',
      'v_washington_tracked_expenditures'
  )
ORDER BY table_name, ordinal_position;

SELECT
    c.relname AS view_name,
    pg_get_viewdef(c.oid, true) AS view_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'reporting'
  AND c.relname IN (
      'v_federal_receipts_by_state_year',
      'v_federal_expenditures_by_state_year',
      'v_washington_partial_fiscal_balance',
      'v_washington_tracked_expenditures'
  )
  AND c.relkind = 'v'
ORDER BY c.relname;

COMMIT;