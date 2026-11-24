
\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-223F - HISTORICAL RAW NAME RECOVERY'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

WITH target AS (
    SELECT
        t.load_batch_id,
        t.source_row_number,
        BTRIM(al.cfda_number) AS program_code,
        t.recipient_id,
        t.funding_agency_id,
        t.awarding_agency_id,
        r.raw_assistance_transaction_id,
        NULLIF(BTRIM(r.raw_record ->> 'recipient_name'), '')
            AS raw_recipient_name,
        NULLIF(BTRIM(r.raw_record ->> 'funding_agency_name'), '')
            AS raw_funding_agency_name,
        NULLIF(BTRIM(r.raw_record ->> 'awarding_agency_name'), '')
            AS raw_awarding_agency_name
    FROM assistance.award_transaction t
    JOIN assistance.assistance_listing al
      ON al.assistance_listing_id = t.assistance_listing_id
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = t.load_batch_id
     AND r.source_row_number = t.source_row_number
    WHERE t.load_batch_id IN (20, 21)
      AND BTRIM(al.cfda_number) IN (
          '93.527','10.557','10.561','93.563','10.924'
      )
)
SELECT
    program_code,
    load_batch_id,
    COUNT(*) AS normalized_transactions,
    COUNT(raw_assistance_transaction_id) AS raw_matches,
    COUNT(*) FILTER (
        WHERE raw_assistance_transaction_id IS NULL
    ) AS missing_raw_matches,
    COUNT(*) FILTER (
        WHERE recipient_id IS NULL
          AND raw_recipient_name IS NOT NULL
    ) AS recoverable_recipient_names,
    COUNT(*) FILTER (
        WHERE funding_agency_id IS NULL
          AND raw_funding_agency_name IS NOT NULL
    ) AS recoverable_funding_agencies,
    COUNT(*) FILTER (
        WHERE awarding_agency_id IS NULL
          AND raw_awarding_agency_name IS NOT NULL
    ) AS recoverable_awarding_agencies,
    COUNT(*) FILTER (
        WHERE raw_recipient_name IS NULL
    ) AS missing_raw_recipient_names
FROM target
GROUP BY program_code, load_batch_id
ORDER BY program_code, load_batch_id;

COMMIT;

\echo 'ETL-223F COMPLETE - NO DATABASE WRITES'
