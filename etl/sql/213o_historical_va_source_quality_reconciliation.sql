
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213O v0.1 - VA SOURCE QUALITY RECONCILIATION'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Raw description field inventory'

WITH sample AS (
    SELECT raw_record
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
    ORDER BY raw_award_transaction_id
    LIMIT 200
)
SELECT
    k.key,
    COUNT(*) AS occurrences,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(s.raw_record->>k.key), '')
              IS NOT NULL
    ) AS populated
FROM sample s
CROSS JOIN LATERAL
    JSONB_OBJECT_KEYS(s.raw_record) AS k(key)
WHERE k.key ~* 'description|narrative|requirement'
GROUP BY k.key
ORDER BY k.key;

\echo ''
\echo '2. Nationwide contract: raw and canonical descriptions'

SELECT
    t.fiscal_year,
    t.award_transaction_id,
    a.piid,
    t.federal_action_obligation,
    LEFT(t.transaction_description, 1200)
        AS canonical_transaction_description,
    LEFT(a.award_description, 1200)
        AS canonical_award_description,
    LEFT(
        r.raw_record->>'transaction_description',
        1200
    ) AS raw_transaction_description,
    LEFT(
        r.raw_record->>'award_description',
        1200
    ) AS raw_award_description
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
JOIN procurement.award a
  ON a.award_id = t.award_id
WHERE r.load_batch_id IN (22, 23)
  AND a.piid = '36C10B18F2811'
ORDER BY t.fiscal_year, ABS(t.federal_action_obligation) DESC
LIMIT 15;

\echo ''
\echo '3. Date anomalies by obligation sign'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        NULLIF(BTRIM(
            r.raw_record->>'period_of_performance_start_date'
        ), '') AS start_text,
        NULLIF(BTRIM(
            r.raw_record->>'period_of_performance_current_end_date'
        ), '') AS end_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(
          r.raw_record->>'funding_agency_code'
      ) = '036'
),
classified AS (
    SELECT
        fiscal_year,
        obligation,
        CASE
            WHEN obligation > 0 THEN 'POSITIVE'
            WHEN obligation < 0 THEN 'NEGATIVE'
            ELSE 'ZERO'
        END AS obligation_sign,
        CASE
            WHEN start_text ~ '^\d{4}-\d{2}-\d{2}$'
             AND end_text ~ '^\d{4}-\d{2}-\d{2}$'
            THEN start_text > end_text
            ELSE NULL
        END AS inverted_interval
    FROM va
)
SELECT
    fiscal_year,
    obligation_sign,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE inverted_interval
    ) AS inverted_count,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE inverted_interval
    ), 0), 2) AS inverted_net_obligations,
    ROUND(SUM(obligation), 2) AS total_net_obligations
FROM classified
GROUP BY fiscal_year, obligation_sign
ORDER BY fiscal_year, obligation_sign;

ROLLBACK;

\echo ''
\echo 'ETL-213O v0.1 COMPLETE - NO DATABASE WRITES'
