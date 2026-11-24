
\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-223E - HISTORICAL RECIPIENT AND AGENCY LINEAGE'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. CERTIFIED VIEW: NAME AND KEY COVERAGE'

SELECT
    BTRIM(cfda_number) AS program_code,
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE recipient_id IS NOT NULL)
        AS recipient_fk_present,
    COUNT(*) FILTER (WHERE recipient_name IS NOT NULL)
        AS recipient_name_present,
    COUNT(*) FILTER (WHERE funding_agency_id IS NOT NULL)
        AS funding_agency_fk_present,
    COUNT(*) FILTER (WHERE funding_agency_name IS NOT NULL)
        AS funding_agency_name_present,
    COUNT(*) FILTER (WHERE awarding_agency_name IS NOT NULL)
        AS awarding_agency_name_present
FROM analysis.v_certified_assistance_ledger
WHERE (
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND BTRIM(cfda_number) IN (
    '93.527','10.557','10.561','93.563','10.924'
)
GROUP BY BTRIM(cfda_number), action_date_fiscal_year
ORDER BY program_code, fiscal_year;

\echo ''
\echo '2. RAW JSON: AVAILABLE RECIPIENT/AGENCY FIELD NAMES'

SELECT
    r.load_batch_id,
    k.key AS raw_field_name,
    COUNT(*) AS records_with_field,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> k.key), '') IS NOT NULL
    ) AS records_with_nonblank_value
FROM assistance.raw_award_transaction r
CROSS JOIN LATERAL jsonb_object_keys(r.raw_record) AS k(key)
WHERE r.load_batch_id IN (20, 21)
AND (
    k.key ILIKE '%recipient%'
    OR k.key ILIKE '%agency%'
)
GROUP BY r.load_batch_id, k.key
ORDER BY r.load_batch_id, k.key;

\echo ''
\echo '3. HISTORICAL RAW RECORD COVERAGE'

SELECT
    load_batch_id,
    COUNT(*) AS raw_records,
    COUNT(*) FILTER (
        WHERE jsonb_typeof(raw_record) = 'object'
    ) AS json_objects
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id
ORDER BY load_batch_id;

COMMIT;

\echo 'ETL-223E COMPLETE - NO DATABASE WRITES'
