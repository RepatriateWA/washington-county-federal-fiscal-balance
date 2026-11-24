BEGIN READ ONLY;

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'reporting'
  AND viewname = 'v_washington_ssa_summary';

SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'ssa'
  AND table_name = 'benefit_payments'
ORDER BY ordinal_position;

SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reporting'
  AND table_name = 'v_washington_ssa_summary'
ORDER BY ordinal_position;

COMMIT;
