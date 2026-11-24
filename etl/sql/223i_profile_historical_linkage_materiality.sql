
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223I - HISTORICAL LINKAGE MATERIALITY'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

WITH target AS (
    SELECT
        t.load_batch_id,
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(al.cfda_number) AS program_code,
        t.federal_action_obligation AS amount,

        a.recipient_id AS award_recipient_id,
        a.awarding_agency_id AS award_awarding_agency_id,
        a.funding_agency_id AS award_funding_agency_id,

        pr.recipient_name AS canonical_recipient_name,
        pr.recipient_uei AS canonical_recipient_uei,

        aa.agency_code AS canonical_awarding_code,
        fa.agency_code AS canonical_funding_code,

        NULLIF(BTRIM(r.raw_record ->> 'recipient_name'), '')
            AS raw_recipient_name,
        NULLIF(BTRIM(r.raw_record ->> 'recipient_uei'), '')
            AS raw_recipient_uei,
        NULLIF(BTRIM(r.raw_record ->> 'awarding_agency_code'), '')
            AS raw_awarding_code,
        NULLIF(BTRIM(r.raw_record ->> 'funding_agency_code'), '')
            AS raw_funding_code

    FROM assistance.award_transaction t
    JOIN assistance.award a
      ON a.assistance_award_id = t.assistance_award_id
    JOIN assistance.assistance_listing al
      ON al.assistance_listing_id = t.assistance_listing_id
    LEFT JOIN procurement.recipient pr
      ON pr.recipient_id = a.recipient_id
    LEFT JOIN procurement.agency aa
      ON aa.agency_id = a.awarding_agency_id
    LEFT JOIN procurement.agency fa
      ON fa.agency_id = a.funding_agency_id
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = t.load_batch_id
     AND r.source_row_number = t.source_row_number

    WHERE (t.load_batch_id = 20 AND t.action_date_fiscal_year = 2018
        OR t.load_batch_id = 21 AND t.action_date_fiscal_year = 2019)
      AND BTRIM(al.cfda_number) IN (
          '93.527','10.557','10.561','93.563','10.924'
      )
),
classified AS (
    SELECT *,
        CASE
            WHEN award_recipient_id IS NULL
                THEN 'NO_AWARD_RECIPIENT_LINK'
            WHEN raw_recipient_uei IS NOT NULL
             AND canonical_recipient_uei IS NOT NULL
             AND UPPER(raw_recipient_uei)
                 <> UPPER(BTRIM(canonical_recipient_uei))
                THEN 'UEI_CONFLICT'
            WHEN raw_recipient_uei IS NOT NULL
             AND canonical_recipient_uei IS NOT NULL
             AND UPPER(raw_recipient_uei)
                 = UPPER(BTRIM(canonical_recipient_uei))
                THEN 'UEI_AGREEMENT'
            WHEN raw_recipient_name IS NOT NULL
             AND canonical_recipient_name IS NOT NULL
             AND LOWER(raw_recipient_name)
                 = LOWER(BTRIM(canonical_recipient_name))
                THEN 'NAME_AGREEMENT_ONLY'
            ELSE 'UNRESOLVED_IDENTITY'
        END AS recipient_evidence,

        CASE
            WHEN award_awarding_agency_id IS NULL
                THEN 'NO_AWARD_AGENCY_LINK'
            WHEN raw_awarding_code = canonical_awarding_code
                THEN 'AWARDING_CODE_AGREEMENT'
            ELSE 'AWARDING_CODE_DIFFERENCE'
        END AS awarding_evidence,

        CASE
            WHEN raw_funding_code IS NULL
                THEN 'RAW_FUNDING_NOT_REPORTED'
            WHEN award_funding_agency_id IS NULL
                THEN 'NO_AWARD_FUNDING_LINK'
            WHEN raw_funding_code = canonical_funding_code
                THEN 'FUNDING_CODE_AGREEMENT'
            ELSE 'FUNDING_CODE_DIFFERENCE'
        END AS funding_evidence
    FROM target
)
SELECT
    program_code,
    fiscal_year,
    recipient_evidence,
    COUNT(*) AS transactions,
    ROUND(SUM(COALESCE(amount, 0)), 2) AS net_obligations,
    ROUND(SUM(ABS(COALESCE(amount, 0))), 2) AS absolute_activity,
    COUNT(*) FILTER (WHERE amount > 0) AS positive_transactions,
    COUNT(*) FILTER (WHERE amount < 0) AS negative_transactions,
    COUNT(*) FILTER (WHERE amount = 0) AS zero_transactions
FROM classified
GROUP BY program_code, fiscal_year, recipient_evidence
ORDER BY program_code, fiscal_year, recipient_evidence;

\echo ''
\echo '2. AGENCY EVIDENCE MATERIALITY'

WITH target AS (
    SELECT
        t.load_batch_id,
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(al.cfda_number) AS program_code,
        t.federal_action_obligation AS amount,
        a.awarding_agency_id,
        a.funding_agency_id,
        aa.agency_code AS canonical_awarding_code,
        fa.agency_code AS canonical_funding_code,
        NULLIF(BTRIM(r.raw_record ->> 'awarding_agency_code'), '')
            AS raw_awarding_code,
        NULLIF(BTRIM(r.raw_record ->> 'funding_agency_code'), '')
            AS raw_funding_code
    FROM assistance.award_transaction t
    JOIN assistance.award a
      ON a.assistance_award_id = t.assistance_award_id
    JOIN assistance.assistance_listing al
      ON al.assistance_listing_id = t.assistance_listing_id
    LEFT JOIN procurement.agency aa
      ON aa.agency_id = a.awarding_agency_id
    LEFT JOIN procurement.agency fa
      ON fa.agency_id = a.funding_agency_id
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = t.load_batch_id
     AND r.source_row_number = t.source_row_number
    WHERE (t.load_batch_id = 20 AND t.action_date_fiscal_year = 2018
        OR t.load_batch_id = 21 AND t.action_date_fiscal_year = 2019)
      AND BTRIM(al.cfda_number) IN (
          '93.527','10.557','10.561','93.563','10.924'
      )
),
classified AS (
    SELECT *,
        CASE
            WHEN awarding_agency_id IS NULL
                THEN 'NO_AWARD_LINK'
            WHEN raw_awarding_code = canonical_awarding_code
                THEN 'CODE_AGREEMENT'
            ELSE 'CODE_DIFFERENCE'
        END AS awarding_evidence,
        CASE
            WHEN raw_funding_code IS NULL
                THEN 'NOT_REPORTED_IN_RAW'
            WHEN funding_agency_id IS NULL
                THEN 'NO_AWARD_LINK'
            WHEN raw_funding_code = canonical_funding_code
                THEN 'CODE_AGREEMENT'
            ELSE 'CODE_DIFFERENCE'
        END AS funding_evidence
    FROM target
)
SELECT
    program_code,
    fiscal_year,
    awarding_evidence,
    funding_evidence,
    COUNT(*) AS transactions,
    ROUND(SUM(COALESCE(amount, 0)), 2) AS net_obligations,
    ROUND(SUM(ABS(COALESCE(amount, 0))), 2) AS absolute_activity
FROM classified
GROUP BY
    program_code, fiscal_year,
    awarding_evidence, funding_evidence
ORDER BY
    program_code, fiscal_year,
    awarding_evidence, funding_evidence;

COMMIT;

\echo 'ETL-223I COMPLETE - NO DATABASE WRITES'
