
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '===================================================='
\echo 'ETL-213M v0.1 - VA GEOGRAPHIC EVIDENCE TRIAGE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '===================================================='

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Top 30 VA-funded transactions with source evidence'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.award_id,
        a.piid,
        t.action_date,
        t.psc_code,
        psc.psc_description,
        t.federal_action_obligation AS obligation,
        c.full_fips AS county_fips,
        c.county_name,
        r.raw_record->>'funding_agency_name'
            AS funding_agency,
        r.raw_record->>'awarding_agency_name'
            AS awarding_agency,
        r.raw_record->>'period_of_performance_start_date'
            AS performance_start,
        r.raw_record->>'period_of_performance_current_end_date'
            AS performance_end,
        COALESCE(
            NULLIF(BTRIM(t.transaction_description), ''),
            NULLIF(BTRIM(a.award_description), '')
        ) AS description
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    LEFT JOIN procurement.psc psc
      ON psc.psc_code = t.psc_code
    LEFT JOIN procurement.place_of_performance pop
      ON pop.award_transaction_id = t.award_transaction_id
    LEFT JOIN reference.county_registry c
      ON c.county_id = pop.county_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
)
SELECT
    fiscal_year,
    award_transaction_id,
    award_id,
    piid,
    action_date,
    psc_code,
    psc_description,
    ROUND(obligation, 2) AS obligation,
    county_fips,
    county_name,
    funding_agency,
    awarding_agency,
    performance_start,
    performance_end,
    LEFT(description, 600) AS description
FROM va
ORDER BY ABS(obligation) DESC
LIMIT 30;

ROLLBACK;

\echo ''
\echo 'ETL-213M v0.1 COMPLETE - NO DATABASE WRITES'
