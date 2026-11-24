
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223J - HISTORICAL PROGRAM EVIDENCE'
\echo 'FY2018-FY2019 / READ ONLY'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. PROGRAM, AGENCY AND ASSISTANCE TYPE PROFILE'

WITH target AS (
    SELECT
        t.load_batch_id,
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(al.cfda_number) AS program_code,
        al.cfda_title AS program_title,
        t.federal_action_obligation AS amount,
        a.award_id_fain,
        NULLIF(BTRIM(r.raw_record ->> 'awarding_agency_name'), '')
            AS raw_awarding_agency,
        NULLIF(BTRIM(r.raw_record ->> 'funding_agency_name'), '')
            AS raw_funding_agency,
        NULLIF(BTRIM(r.raw_record ->> 'recipient_state_code'), '')
            AS raw_recipient_state,
        NULLIF(BTRIM(r.raw_record ->> 'primary_place_of_performance_state_code'), '')
            AS raw_performance_state,
        aty.assistance_type_description
    FROM assistance.award_transaction t
    JOIN assistance.award a
      ON a.assistance_award_id = t.assistance_award_id
    JOIN assistance.assistance_listing al
      ON al.assistance_listing_id = t.assistance_listing_id
    LEFT JOIN assistance.assistance_type aty
      ON aty.assistance_type_id = t.assistance_type_id
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = t.load_batch_id
     AND r.source_row_number = t.source_row_number
    WHERE (t.load_batch_id = 20 AND t.action_date_fiscal_year = 2018
        OR t.load_batch_id = 21 AND t.action_date_fiscal_year = 2019)
      AND BTRIM(al.cfda_number) IN (
          '93.527','10.557','10.561','93.563','10.924'
      )
)
SELECT
    program_code,
    fiscal_year,
    program_title,
    raw_awarding_agency,
    raw_funding_agency,
    assistance_type_description,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_id_fain) AS distinct_fains,
    ROUND(SUM(COALESCE(amount, 0)), 2) AS net_obligations,
    ROUND(SUM(ABS(COALESCE(amount, 0))), 2) AS absolute_activity,
    COUNT(*) FILTER (
        WHERE raw_recipient_state = 'WA'
    ) AS wa_recipient_transactions,
    COUNT(*) FILTER (
        WHERE raw_performance_state = 'WA'
    ) AS wa_performance_transactions,
    COUNT(*) FILTER (
        WHERE raw_recipient_state IS NULL
    ) AS recipient_state_missing,
    COUNT(*) FILTER (
        WHERE raw_performance_state IS NULL
    ) AS performance_state_missing
FROM target
GROUP BY
    program_code,
    fiscal_year,
    program_title,
    raw_awarding_agency,
    raw_funding_agency,
    assistance_type_description
ORDER BY
    program_code, fiscal_year,
    ABS(SUM(COALESCE(amount, 0))) DESC;

\echo ''
\echo '2. RAW GEOGRAPHY FIELD INVENTORY'

SELECT
    r.load_batch_id,
    k.key AS raw_field_name,
    COUNT(*) AS records_with_field,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(r.raw_record ->> k.key), '')
              IS NOT NULL
    ) AS records_populated
FROM assistance.raw_award_transaction r
CROSS JOIN LATERAL jsonb_object_keys(r.raw_record) AS k(key)
WHERE r.load_batch_id IN (20, 21)
  AND (
      k.key ILIKE '%place_of_performance%state%'
      OR k.key ILIKE '%recipient%state%'
  )
GROUP BY r.load_batch_id, k.key
ORDER BY r.load_batch_id, k.key;

COMMIT;

\echo 'ETL-223J COMPLETE - NO DATABASE WRITES'
