SELECT
    schemaname,
    viewname,
    pg_get_viewdef(
        format('%I.%I', schemaname, viewname)::regclass,
        true
    ) AS view_definition
FROM pg_views
WHERE schemaname = 'analysis'
  AND viewname IN (
      'v_assistance_transaction_observation_ledger',
      'v_certified_assistance_ledger'
  )
ORDER BY viewname;