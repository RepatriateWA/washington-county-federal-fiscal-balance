
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '========================================================'
\echo 'ETL-213L v0.1 - VA GEOGRAPHIC AND TEMPORAL PROFILE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '========================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. VA procurement by county with actual FIPS and names'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.federal_action_obligation AS obligation,
        pop.county_id
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    LEFT JOIN procurement.place_of_performance pop
      ON pop.award_transaction_id = t.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
)
SELECT
    v.fiscal_year,
    c.full_fips AS county_fips,
    c.county_name,
    COUNT(*) AS transactions,
    ROUND(SUM(v.obligation), 2) AS net_obligations
FROM va v
LEFT JOIN reference.county_registry c
  ON c.county_id = v.county_id
GROUP BY v.fiscal_year, c.full_fips, c.county_name
ORDER BY v.fiscal_year, net_obligations DESC;

\echo ''
\echo '2. Performance timing by obligation fiscal year'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        NULLIF(
            BTRIM(r.raw_record->>'period_of_performance_start_date'),
            ''
        ) AS start_text,
        NULLIF(
            BTRIM(r.raw_record->>'period_of_performance_current_end_date'),
            ''
        ) AS end_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
),
parsed AS (
    SELECT
        fiscal_year,
        obligation,
        CASE
            WHEN start_text ~ '^\d{4}-\d{2}-\d{2}'
            THEN LEFT(start_text, 10)::date
        END AS performance_start,
        CASE
            WHEN end_text ~ '^\d{4}-\d{2}-\d{2}'
            THEN LEFT(end_text, 10)::date
        END AS performance_end
    FROM va
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE performance_start IS NULL
           OR performance_end IS NULL
    ) AS incomplete_dates,
    COUNT(*) FILTER (
        WHERE performance_end >
              MAKE_DATE(fiscal_year, 9, 30)
    ) AS ends_after_fiscal_year,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE performance_end >
              MAKE_DATE(fiscal_year, 9, 30)
    ), 0), 2) AS net_obligations_ending_later,
    COUNT(*) FILTER (
        WHERE performance_start >
              MAKE_DATE(fiscal_year, 9, 30)
    ) AS starts_after_fiscal_year
FROM parsed
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. Largest D318 awards: geography and descriptions'

WITH ehrm AS (
    SELECT
        t.fiscal_year,
        t.award_id,
        a.piid,
        t.federal_action_obligation AS obligation,
        c.full_fips AS county_fips,
        c.county_name,
        a.award_description
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
      AND t.psc_code = 'D318'
)
SELECT
    fiscal_year,
    award_id,
    piid,
    COUNT(*) AS transactions,
    STRING_AGG(
        DISTINCT COALESCE(
            county_name || ' (' || county_fips || ')',
            '[UNRESOLVED]'
        ),
        '; '
    ) AS recorded_counties,
    ROUND(SUM(obligation), 2) AS net_obligations,
    LEFT(MAX(award_description), 180) AS description
FROM ehrm
GROUP BY fiscal_year, award_id, piid
ORDER BY ABS(SUM(obligation)) DESC
LIMIT 20;

ROLLBACK;

\echo ''
\echo 'ETL-213L v0.1 COMPLETE - NO DATABASE WRITES'
