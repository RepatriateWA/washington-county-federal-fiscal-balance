
\set ON_ERROR_STOP on
\pset pager off

\echo '=============================================================='
\echo 'ETL-201Q STAGE D.6 - PRODUCTION CONSTRAINT EQUIVALENCE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '600s';

\echo ''
\echo 'SECTION 1 - ELIGIBLE HISTORICAL POPULATION'

WITH eligible AS (
    SELECT
        raw.raw_assistance_transaction_id,
        raw.load_batch_id,
        raw.source_row_number,
        raw.assistance_transaction_unique_key,
        award.assistance_award_id,
        listing.assistance_listing_id,
        typ.assistance_type_id,
        opportunity.funding_opportunity_id,
        raw.raw_record
    FROM assistance.raw_award_transaction raw
    JOIN assistance.award award
      ON award.assistance_award_unique_key =
         raw.assistance_award_unique_key
    JOIN assistance.assistance_listing listing
      ON listing.cfda_number =
         BTRIM(raw.raw_record ->> 'cfda_number')
    JOIN assistance.assistance_type typ
      ON typ.assistance_type_code =
         BTRIM(raw.raw_record ->> 'assistance_type_code')
    LEFT JOIN assistance.funding_opportunity opportunity
      ON opportunity.funding_opportunity_number =
         NULLIF(
             BTRIM(
                 raw.raw_record ->> 'funding_opportunity_number'
             ),
             ''
         )
    WHERE raw.load_batch_id IN (20, 21)
)
SELECT
    load_batch_id,
    COUNT(*) AS eligible_rows,
    COUNT(DISTINCT raw_assistance_transaction_id)
        AS distinct_raw_ids,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(*) FILTER (
        WHERE assistance_award_id IS NULL
           OR assistance_listing_id IS NULL
           OR assistance_type_id IS NULL
    ) AS missing_required_references,
    COUNT(*) FILTER (
        WHERE assistance_transaction_unique_key IS NULL
           OR BTRIM(assistance_transaction_unique_key) = ''
    ) AS blank_transaction_keys,
    COUNT(*) FILTER (
        WHERE NULLIF(
            BTRIM(raw_record ->> 'action_date_fiscal_year'),
            ''
        )::integer NOT BETWEEN 1900 AND 2200
    ) AS fiscal_year_check_failures
FROM eligible
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo 'SECTION 2 - EXISTING BATCH/ROW COLLISIONS'

SELECT
    raw.load_batch_id,
    COUNT(*) AS existing_batch_row_collisions
FROM assistance.raw_award_transaction raw
JOIN assistance.award_transaction transaction
  ON transaction.load_batch_id = raw.load_batch_id
 AND transaction.source_row_number = raw.source_row_number
WHERE raw.load_batch_id IN (20, 21)
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

\echo ''
\echo 'SECTION 3 - RAW SOURCE ROW UNIQUENESS'

SELECT
    load_batch_id,
    source_row_number,
    COUNT(*) AS duplicate_count
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id, source_row_number
HAVING COUNT(*) > 1
ORDER BY load_batch_id, source_row_number
LIMIT 20;

\echo ''
\echo 'SECTION 4 - HISTORICAL REFERENCE INTEGRITY'

WITH eligible AS (
    SELECT
        raw.load_batch_id,
        award.assistance_award_id,
        listing.assistance_listing_id,
        typ.assistance_type_id,
        opportunity.funding_opportunity_id
    FROM assistance.raw_award_transaction raw
    JOIN assistance.award award
      ON award.assistance_award_unique_key =
         raw.assistance_award_unique_key
    JOIN assistance.assistance_listing listing
      ON listing.cfda_number =
         BTRIM(raw.raw_record ->> 'cfda_number')
    JOIN assistance.assistance_type typ
      ON typ.assistance_type_code =
         BTRIM(raw.raw_record ->> 'assistance_type_code')
    LEFT JOIN assistance.funding_opportunity opportunity
      ON opportunity.funding_opportunity_number =
         NULLIF(
             BTRIM(
                 raw.raw_record ->> 'funding_opportunity_number'
             ),
             ''
         )
    WHERE raw.load_batch_id IN (20, 21)
)
SELECT
    e.load_batch_id,
    COUNT(*) FILTER (
        WHERE a.assistance_award_id IS NULL
    ) AS orphan_awards,
    COUNT(*) FILTER (
        WHERE l.assistance_listing_id IS NULL
    ) AS orphan_listings,
    COUNT(*) FILTER (
        WHERE t.assistance_type_id IS NULL
    ) AS orphan_types,
    COUNT(*) FILTER (
        WHERE e.funding_opportunity_id IS NOT NULL
          AND o.funding_opportunity_id IS NULL
    ) AS orphan_funding_opportunities
FROM eligible e
LEFT JOIN assistance.award a
  ON a.assistance_award_id = e.assistance_award_id
LEFT JOIN assistance.assistance_listing l
  ON l.assistance_listing_id = e.assistance_listing_id
LEFT JOIN assistance.assistance_type t
  ON t.assistance_type_id = e.assistance_type_id
LEFT JOIN assistance.funding_opportunity o
  ON o.funding_opportunity_id = e.funding_opportunity_id
GROUP BY e.load_batch_id
ORDER BY e.load_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE D.6 COMPLETE - READ ONLY'
