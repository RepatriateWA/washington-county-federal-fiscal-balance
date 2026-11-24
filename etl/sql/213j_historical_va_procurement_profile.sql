
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '===================================================='
\echo 'ETL-213J v0.1 - HISTORICAL VA PROCUREMENT PROFILE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '===================================================='

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. VA-funded procurement: annual controls'

WITH historical AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.award_id,
        t.federal_action_obligation AS obligation,
        t.psc_code,
        t.naics_code,
        NULLIF(BTRIM(r.raw_record->>'funding_agency_code'), '')
            AS funding_code,
        NULLIF(BTRIM(r.raw_record->>'awarding_agency_code'), '')
            AS awarding_code
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_id) AS awards,
    COUNT(*) FILTER (WHERE obligation > 0) AS positive_count,
    COUNT(*) FILTER (WHERE obligation < 0) AS negative_count,
    ROUND(COALESCE(SUM(obligation)
        FILTER (WHERE obligation > 0), 0), 2) AS positive_total,
    ROUND(COALESCE(SUM(obligation)
        FILTER (WHERE obligation < 0), 0), 2) AS negative_total,
    ROUND(SUM(obligation), 2) AS net_obligations,
    COUNT(*) FILTER (
        WHERE awarding_code <> '036'
    ) AS other_awarding_agency_count
FROM historical
WHERE funding_code = '036'
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. VA-funded procurement by PSC'

WITH historical AS (
    SELECT
        t.fiscal_year,
        t.psc_code,
        t.federal_action_obligation AS obligation
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND NULLIF(BTRIM(
          r.raw_record->>'funding_agency_code'
      ), '') = '036'
),
ranked AS (
    SELECT
        fiscal_year,
        COALESCE(psc_code, '[NULL]') AS psc_code,
        COUNT(*) AS transactions,
        ROUND(SUM(obligation), 2) AS net_obligations,
        ROW_NUMBER() OVER (
            PARTITION BY fiscal_year
            ORDER BY SUM(obligation) DESC
        ) AS rn
    FROM historical
    GROUP BY fiscal_year, psc_code
)
SELECT
    fiscal_year,
    psc_code,
    transactions,
    net_obligations
FROM ranked
WHERE rn <= 25
ORDER BY fiscal_year, rn;

\echo ''
\echo '3. VA-funded procurement by WA county FIPS'

SELECT
    t.fiscal_year,
    p.county_id,
    COUNT(*) AS transactions,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS net_obligations
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
LEFT JOIN procurement.place_of_performance p
  ON p.award_transaction_id = t.award_transaction_id
WHERE r.load_batch_id IN (22, 23)
  AND NULLIF(BTRIM(
      r.raw_record->>'funding_agency_code'
  ), '') = '036'
GROUP BY t.fiscal_year, p.county_id
ORDER BY t.fiscal_year, net_obligations DESC;

ROLLBACK;

\echo ''
\echo 'ETL-213J v0.1 COMPLETE - NO DATABASE WRITES'
