
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '========================================================'
\echo 'ETL-213I v0.1 - TRANSACTION-LEVEL AGENCY CONTROLS'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '========================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Reconstructed funding-agency controls'

WITH historical AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.federal_action_obligation AS obligation,
        NULLIF(BTRIM(r.raw_record->>'funding_agency_code'), '')
            AS funding_code,
        NULLIF(BTRIM(r.raw_record->>'funding_agency_name'), '')
            AS funding_name
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    fiscal_year,
    funding_code,
    MIN(funding_name) AS observed_agency_name,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS net_obligations
FROM historical
GROUP BY fiscal_year, funding_code
ORDER BY fiscal_year, net_obligations DESC;

\echo ''
\echo '2. VA, Defense and Energy: funding versus awarding'

WITH historical AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
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
    agency_code,
    COUNT(*) FILTER (
        WHERE funding_code = agency_code
    ) AS funding_transactions,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE funding_code = agency_code
    ), 0), 2) AS funding_net,
    COUNT(*) FILTER (
        WHERE awarding_code = agency_code
    ) AS awarding_transactions,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE awarding_code = agency_code
    ), 0), 2) AS awarding_net,
    COUNT(*) FILTER (
        WHERE funding_code = agency_code
           OR awarding_code = agency_code
    ) AS either_role_transactions,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE funding_code = agency_code
           OR awarding_code = agency_code
    ), 0), 2) AS either_role_net
FROM historical
CROSS JOIN (
    VALUES
        ('036'),
        ('097'),
        ('089')
) AS target(agency_code)
GROUP BY fiscal_year, agency_code
ORDER BY fiscal_year, agency_code;

\echo ''
\echo '3. Reconstructed annual totals and code coverage'

WITH historical AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        t.federal_action_obligation AS obligation,
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
    h.fiscal_year,
    COUNT(*) AS observations,
    COUNT(DISTINCT h.award_transaction_id)
        AS distinct_transactions,
    COUNT(*) FILTER (
        WHERE h.funding_code IS NULL
    ) AS missing_funding_codes,
    COUNT(*) FILTER (
        WHERE h.awarding_code IS NULL
    ) AS missing_awarding_codes,
    COUNT(*) FILTER (
        WHERE fa.agency_id IS NULL
          AND h.funding_code IS NOT NULL
    ) AS unmatched_funding_codes,
    COUNT(*) FILTER (
        WHERE aa.agency_id IS NULL
          AND h.awarding_code IS NOT NULL
    ) AS unmatched_awarding_codes,
    ROUND(SUM(h.obligation), 2) AS net_obligations
FROM historical h
LEFT JOIN procurement.agency fa
  ON fa.agency_code = h.funding_code
LEFT JOIN procurement.agency aa
  ON aa.agency_code = h.awarding_code
GROUP BY h.fiscal_year
ORDER BY h.fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-213I v0.1 COMPLETE - NO DATABASE WRITES'
