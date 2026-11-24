
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213H v0.1 - HISTORICAL AGENCY CONFLICT PROFILE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Raw versus canonical agency agreement'

WITH historical AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        a.funding_agency_id,
        a.awarding_agency_id,
        NULLIF(BTRIM(r.raw_record->>'funding_agency_code'), '')
            AS funding_code,
        NULLIF(BTRIM(r.raw_record->>'awarding_agency_code'), '')
            AS awarding_code
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    h.fiscal_year,
    COUNT(*) AS observations,
    COUNT(*) FILTER (
        WHERE h.funding_agency_id IS NOT NULL
          AND h.funding_code IS DISTINCT FROM fa.agency_code
    ) AS funding_disagreements,
    COUNT(*) FILTER (
        WHERE h.awarding_agency_id IS NOT NULL
          AND h.awarding_code IS DISTINCT FROM aa.agency_code
    ) AS awarding_disagreements,
    ROUND(COALESCE(SUM(h.obligation) FILTER (
        WHERE h.funding_agency_id IS NOT NULL
          AND h.funding_code IS DISTINCT FROM fa.agency_code
    ), 0), 2) AS funding_disagreement_net
FROM historical h
LEFT JOIN procurement.agency fa
  ON fa.agency_id = h.funding_agency_id
LEFT JOIN procurement.agency aa
  ON aa.agency_id = h.awarding_agency_id
GROUP BY h.fiscal_year
ORDER BY h.fiscal_year;

\echo ''
\echo '2. Conflicting historical funding awards'

WITH historical AS (
    SELECT
        t.award_id,
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        NULLIF(BTRIM(r.raw_record->>'funding_agency_code'), '')
            AS funding_code
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
),
conflicts AS (
    SELECT award_id
    FROM historical
    GROUP BY award_id
    HAVING COUNT(DISTINCT funding_code) > 1
)
SELECT
    h.award_id,
    COUNT(*) AS observations,
    STRING_AGG(DISTINCT h.funding_code, ', '
        ORDER BY h.funding_code) AS funding_codes,
    ROUND(SUM(h.obligation), 2) AS net_obligations
FROM historical h
JOIN conflicts c ON c.award_id = h.award_id
GROUP BY h.award_id
ORDER BY ABS(SUM(h.obligation)) DESC, h.award_id
LIMIT 25;

\echo ''
\echo '3. Unmatched agency codes: financial exposure'

WITH raw_agencies AS (
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
    h.fiscal_year,
    COUNT(*) FILTER (
        WHERE h.funding_code IS NOT NULL
          AND fa.agency_id IS NULL
    ) AS unmatched_funding_observations,
    COUNT(*) FILTER (
        WHERE h.awarding_code IS NOT NULL
          AND aa.agency_id IS NULL
    ) AS unmatched_awarding_observations,
    ROUND(COALESCE(SUM(h.obligation) FILTER (
        WHERE h.funding_code IS NOT NULL
          AND fa.agency_id IS NULL
    ), 0), 2) AS unmatched_funding_net
FROM raw_agencies h
LEFT JOIN procurement.agency fa
  ON fa.agency_code = h.funding_code
LEFT JOIN procurement.agency aa
  ON aa.agency_code = h.awarding_code
GROUP BY h.fiscal_year
ORDER BY h.fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-213H v0.1 COMPLETE - NO DATABASE WRITES'
