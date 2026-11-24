
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223H - AWARD TO TRANSACTION LINKAGE PROFILE'
\echo 'FY2018-FY2019 / TARGET FIVE PROGRAMS / READ ONLY'

BEGIN TRANSACTION READ ONLY;

WITH target AS (
    SELECT
        t.load_batch_id,
        t.source_row_number,
        BTRIM(al.cfda_number) AS program_code,

        t.recipient_id AS transaction_recipient_id,
        t.awarding_agency_id AS transaction_awarding_agency_id,
        t.funding_agency_id AS transaction_funding_agency_id,

        a.recipient_id AS award_recipient_id,
        a.awarding_agency_id AS award_awarding_agency_id,
        a.funding_agency_id AS award_funding_agency_id,

        r.recipient_name AS award_recipient_name,
        r.recipient_uei AS award_recipient_uei,

        aa.agency_code AS award_awarding_agency_code,
        fa.agency_code AS award_funding_agency_code,

        NULLIF(BTRIM(raw.raw_record ->> 'recipient_name'), '')
            AS raw_recipient_name,
        NULLIF(BTRIM(raw.raw_record ->> 'recipient_uei'), '')
            AS raw_recipient_uei,

        NULLIF(BTRIM(raw.raw_record ->> 'awarding_agency_code'), '')
            AS raw_awarding_agency_code,
        NULLIF(BTRIM(raw.raw_record ->> 'funding_agency_code'), '')
            AS raw_funding_agency_code

    FROM assistance.award_transaction t
    JOIN assistance.award a
      ON a.assistance_award_id = t.assistance_award_id
    JOIN assistance.assistance_listing al
      ON al.assistance_listing_id = t.assistance_listing_id
    LEFT JOIN procurement.recipient r
      ON r.recipient_id = a.recipient_id
    LEFT JOIN procurement.agency aa
      ON aa.agency_id = a.awarding_agency_id
    LEFT JOIN procurement.agency fa
      ON fa.agency_id = a.funding_agency_id
    LEFT JOIN assistance.raw_award_transaction raw
      ON raw.load_batch_id = t.load_batch_id
     AND raw.source_row_number = t.source_row_number

    WHERE t.load_batch_id IN (20, 21)
      AND BTRIM(al.cfda_number) IN (
          '93.527','10.557','10.561','93.563','10.924'
      )
)
SELECT
    program_code,
    load_batch_id,
    COUNT(*) AS target_transactions,

    COUNT(*) FILTER (
        WHERE transaction_recipient_id IS NULL
    ) AS recipient_link_missing,

    COUNT(*) FILTER (
        WHERE transaction_recipient_id IS NULL
          AND award_recipient_id IS NOT NULL
    ) AS recipient_award_link_available,

    COUNT(*) FILTER (
        WHERE transaction_recipient_id IS NULL
          AND award_recipient_id IS NOT NULL
          AND raw_recipient_name IS NOT NULL
          AND LOWER(BTRIM(raw_recipient_name))
              = LOWER(BTRIM(award_recipient_name))
    ) AS recipient_name_agrees,

    COUNT(*) FILTER (
        WHERE transaction_recipient_id IS NULL
          AND award_recipient_id IS NOT NULL
          AND raw_recipient_uei IS NOT NULL
          AND award_recipient_uei IS NOT NULL
          AND UPPER(BTRIM(raw_recipient_uei))
              = UPPER(BTRIM(award_recipient_uei))
    ) AS recipient_uei_agrees,

    COUNT(*) FILTER (
        WHERE transaction_recipient_id IS NULL
          AND award_recipient_id IS NOT NULL
          AND raw_recipient_uei IS NOT NULL
          AND award_recipient_uei IS NOT NULL
          AND UPPER(BTRIM(raw_recipient_uei))
              <> UPPER(BTRIM(award_recipient_uei))
    ) AS recipient_uei_conflicts,

    COUNT(*) FILTER (
        WHERE transaction_awarding_agency_id IS NULL
          AND award_awarding_agency_id IS NOT NULL
          AND raw_awarding_agency_code IS NOT NULL
          AND award_awarding_agency_code IS NOT NULL
          AND BTRIM(raw_awarding_agency_code)
              = BTRIM(award_awarding_agency_code)
    ) AS awarding_agency_code_agrees,

    COUNT(*) FILTER (
        WHERE transaction_funding_agency_id IS NULL
          AND award_funding_agency_id IS NOT NULL
          AND raw_funding_agency_code IS NOT NULL
          AND award_funding_agency_code IS NOT NULL
          AND BTRIM(raw_funding_agency_code)
              = BTRIM(award_funding_agency_code)
    ) AS funding_agency_code_agrees

FROM target
GROUP BY program_code, load_batch_id
ORDER BY program_code, load_batch_id;

COMMIT;

\echo 'ETL-223H COMPLETE - NO DATABASE WRITES'
