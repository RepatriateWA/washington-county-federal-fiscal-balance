\pset pager off
\echo 'ETL-240A2H9: SNAP administration view profile'

BEGIN TRANSACTION READ ONLY;

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (table_schema, table_name) IN (
        ('analysis', 'v_assistance_geographic_attribution'),
        ('analysis', 'v_certified_assistance_ledger'),
        ('assistance', 'assistance_listing')
    )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;

ROLLBACK;
