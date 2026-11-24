
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213R v0.1 - VA MEDICAL IMAGING GEOGRAPHY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. PSC 6525 controls by year and recorded county'

WITH imaging AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.federal_action_obligation AS obligation,
        c.full_fips AS county_fips,
        c.county_name
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    LEFT JOIN procurement.place_of_performance pop
      ON pop.award_transaction_id = t.award_transaction_id
    LEFT JOIN reference.county_registry c
      ON c.county_id = pop.county_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
      AND t.psc_code = '6525'
)
SELECT
    fiscal_year,
    county_fips,
    county_name,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS net_obligations,
    ROUND(SUM(ABS(obligation)), 2)
        AS gross_absolute_obligations
FROM imaging
GROUP BY fiscal_year, county_fips, county_name
ORDER BY fiscal_year, gross_absolute_obligations DESC;

\echo ''
\echo '2. Largest PSC 6525 transactions and destinations'

WITH imaging AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        a.piid,
        t.federal_action_obligation AS obligation,
        c.full_fips AS county_fips,
        c.county_name,
        COALESCE(t.transaction_description, '')
            AS transaction_description,
        COALESCE(a.award_description, '')
            AS award_description
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    LEFT JOIN procurement.place_of_performance pop
      ON pop.award_transaction_id = t.award_transaction_id
    LEFT JOIN reference.county_registry c
      ON c.county_id = pop.county_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
      AND t.psc_code = '6525'
)
SELECT
    fiscal_year,
    award_transaction_id,
    piid,
    ROUND(obligation, 2) AS obligation,
    county_fips,
    county_name,
    LEFT(transaction_description, 500)
        AS transaction_description,
    LEFT(award_description, 300)
        AS award_description
FROM imaging
ORDER BY ABS(obligation) DESC
LIMIT 35;

\echo ''
\echo '3. Named out-of-state destination indicators'

WITH imaging AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        a.piid,
        t.federal_action_obligation AS obligation,
        c.county_name,
        COALESCE(t.transaction_description, '') || ' ' ||
        COALESCE(a.award_description, '') AS evidence_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    LEFT JOIN procurement.place_of_performance pop
      ON pop.award_transaction_id = t.award_transaction_id
    LEFT JOIN reference.county_registry c
      ON c.county_id = pop.county_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
      AND t.psc_code = '6525'
)
SELECT
    fiscal_year,
    award_transaction_id,
    piid,
    county_name AS recorded_wa_county,
    ROUND(obligation, 2) AS obligation,
    LEFT(evidence_text, 500) AS evidence_text
FROM imaging
WHERE evidence_text ~* (
    'baltimore|maryland|white city|oregon|' ||
    'california|florida|texas|new york|' ||
    'philadelphia|chicago|cleveland|' ||
    'atlanta|denver|phoenix'
)
ORDER BY ABS(obligation) DESC
LIMIT 35;

ROLLBACK;

\echo ''
\echo 'ETL-213R v0.1 COMPLETE - NO DATABASE WRITES'
