
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213N v0.1 - VA EVIDENCE AND DATE QUALITY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Geographic evidence indicators by fiscal year'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(t.transaction_description), ''),
            NULLIF(BTRIM(a.award_description), ''),
            ''
        ) AS description
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
),
flags AS (
    SELECT *,
        description ~* 
            '(nationwide|nationally|fifty \(50\) states|all 50 states|throughout the united states)'
            AS nationwide_text,
        description ~*
            '(white city|oregon|multistate|multi-state)'
            AS multistate_text,
        description ~*
            '(seattle|spokane|walla walla|vancouver, wa|tacoma|american lake|mann-grandstaff)'
            AS named_wa_text
    FROM va
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE nationwide_text)
        AS nationwide_keyword_count,
    ROUND(COALESCE(SUM(obligation)
        FILTER (WHERE nationwide_text), 0), 2)
        AS nationwide_keyword_net,
    COUNT(*) FILTER (WHERE multistate_text)
        AS multistate_keyword_count,
    ROUND(COALESCE(SUM(obligation)
        FILTER (WHERE multistate_text), 0), 2)
        AS multistate_keyword_net,
    COUNT(*) FILTER (WHERE named_wa_text)
        AS named_wa_keyword_count,
    ROUND(COALESCE(SUM(obligation)
        FILTER (WHERE named_wa_text), 0), 2)
        AS named_wa_keyword_net
FROM flags
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. Performance date completeness and anomalies'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
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
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
),
dates AS (
    SELECT *,
        CASE WHEN start_text ~ '^\d{4}-\d{2}-\d{2}$'
             THEN start_text::date END AS start_date,
        CASE WHEN end_text ~ '^\d{4}-\d{2}-\d{2}$'
             THEN end_text::date END AS end_date
    FROM va
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE start_date IS NULL OR end_date IS NULL
    ) AS missing_or_unparsed_dates,
    COUNT(*) FILTER (
        WHERE start_date > end_date
    ) AS inverted_intervals,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE start_date > end_date
    ), 0), 2) AS inverted_interval_net,
    COUNT(*) FILTER (
        WHERE start_date <= end_date
    ) AS valid_intervals
FROM dates
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. Largest inverted performance intervals'

WITH va AS (
    SELECT
        t.fiscal_year,
        t.award_transaction_id,
        a.piid,
        t.federal_action_obligation AS obligation,
        r.raw_record->>'period_of_performance_start_date'
            AS start_text,
        r.raw_record->>'period_of_performance_current_end_date'
            AS end_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
)
SELECT
    fiscal_year,
    award_transaction_id,
    piid,
    start_text,
    end_text,
    ROUND(obligation, 2) AS obligation
FROM va
WHERE start_text ~ '^\d{4}-\d{2}-\d{2}$'
  AND end_text ~ '^\d{4}-\d{2}-\d{2}$'
  AND start_text > end_text
ORDER BY ABS(obligation) DESC
LIMIT 25;

ROLLBACK;

\echo ''
\echo 'ETL-213N v0.1 COMPLETE - NO DATABASE WRITES'
