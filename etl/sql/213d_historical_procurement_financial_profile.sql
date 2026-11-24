
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '========================================================'
\echo 'ETL-213D v0.1 - HISTORICAL PROCUREMENT FINANCIAL PROFILE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '========================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Annual obligation controls'

SELECT
    t.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT t.award_id) AS awards,
    COUNT(*) FILTER (
        WHERE t.federal_action_obligation > 0
    ) AS positive_transactions,
    COUNT(*) FILTER (
        WHERE t.federal_action_obligation < 0
    ) AS negative_transactions,
    COUNT(*) FILTER (
        WHERE t.federal_action_obligation = 0
    ) AS zero_transactions,
    ROUND(SUM(t.federal_action_obligation)
        FILTER (WHERE t.federal_action_obligation > 0), 2)
        AS positive_obligations,
    ROUND(SUM(t.federal_action_obligation)
        FILTER (WHERE t.federal_action_obligation < 0), 2)
        AS deobligations,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS net_obligations
FROM procurement.award_transaction t
WHERE t.fiscal_year IN (2018, 2019)
GROUP BY t.fiscal_year
ORDER BY t.fiscal_year;

\echo ''
\echo '2. Funding agency obligation concentration'

SELECT
    t.fiscal_year,
    COALESCE(ag.agency_name, '[UNRESOLVED]') AS funding_agency,
    COUNT(*) AS transactions,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS net_obligations
FROM procurement.award_transaction t
JOIN procurement.award a
  ON a.award_id = t.award_id
LEFT JOIN procurement.agency ag
  ON ag.agency_id = a.funding_agency_id
WHERE t.fiscal_year IN (2018, 2019)
GROUP BY t.fiscal_year, ag.agency_name
ORDER BY t.fiscal_year, net_obligations DESC;

\echo ''
\echo '3. VA exposure: funding OR awarding agency'

SELECT
    t.fiscal_year,
    COUNT(*) AS va_candidate_transactions,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS va_candidate_net_obligations
FROM procurement.award_transaction t
JOIN procurement.award a
  ON a.award_id = t.award_id
LEFT JOIN procurement.agency fa
  ON fa.agency_id = a.funding_agency_id
LEFT JOIN procurement.agency aa
  ON aa.agency_id = a.awarding_agency_id
WHERE t.fiscal_year IN (2018, 2019)
  AND (
      fa.agency_name ILIKE '%Veterans Affairs%'
      OR aa.agency_name ILIKE '%Veterans Affairs%'
  )
GROUP BY t.fiscal_year
ORDER BY t.fiscal_year;

\echo ''
\echo '4. Geography and financial coverage'

SELECT
    t.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE p.award_transaction_id IS NOT NULL
    ) AS geographically_linked,
    COUNT(*) FILTER (
        WHERE p.county_id IS NOT NULL
    ) AS county_linked,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS net_obligations,
    ROUND(SUM(t.federal_action_obligation)
        FILTER (WHERE p.county_id IS NULL), 2)
        AS missing_county_obligations
FROM procurement.award_transaction t
LEFT JOIN procurement.place_of_performance p
  ON p.award_transaction_id = t.award_transaction_id
WHERE t.fiscal_year IN (2018, 2019)
GROUP BY t.fiscal_year
ORDER BY t.fiscal_year;

\echo ''
\echo '5. PSC functional concentration (top 20 per year)'

WITH ranked AS (
    SELECT
        t.fiscal_year,
        COALESCE(t.psc_code, '[NULL]') AS psc_code,
        COUNT(*) AS transactions,
        ROUND(SUM(t.federal_action_obligation), 2)
            AS net_obligations,
        ROW_NUMBER() OVER (
            PARTITION BY t.fiscal_year
            ORDER BY SUM(t.federal_action_obligation) DESC
        ) AS rank_number
    FROM procurement.award_transaction t
    WHERE t.fiscal_year IN (2018, 2019)
    GROUP BY t.fiscal_year, t.psc_code
)
SELECT fiscal_year, psc_code, transactions, net_obligations
FROM ranked
WHERE rank_number <= 20
ORDER BY fiscal_year, rank_number;

ROLLBACK;

\echo ''
\echo 'ETL-213D v0.1 COMPLETE - NO DATABASE WRITES'
