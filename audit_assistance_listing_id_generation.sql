BEGIN;
SET TRANSACTION READ ONLY;

SELECT
    column_name,
    identity_generation,
    is_generated,
    column_default
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'assistance_listing'
ORDER BY ordinal_position;

SELECT
    pg_get_serial_sequence(
        'assistance.assistance_listing',
        'assistance_listing_id'
    ) AS associated_sequence;

SELECT
    tgname AS trigger_name,
    pg_get_triggerdef(oid) AS trigger_definition
FROM pg_trigger
WHERE tgrelid = 'assistance.assistance_listing'::regclass
  AND NOT tgisinternal
ORDER BY tgname;

ROLLBACK;
