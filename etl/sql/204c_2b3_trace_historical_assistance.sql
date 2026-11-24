
-- ============================================================
-- ETL-204C-2B.3
-- FY2018-FY2019 Historical Assistance Trace
-- READ ONLY
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT '1. HISTORICAL BATCH COVERAGE' AS section;

SELECT
    load_batch_id,
    action_date_fiscal_year,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM assistance.award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id, action_date_fiscal_year
ORDER BY load_batch_id, action_date_fiscal_year;


SELECT '2. PROVENANCE AND AWARD LINKAGE' AS section;

WITH observation_counts AS (
    SELECT
        assistance_transaction_id,
        COUNT(*) AS observation_count
    FROM assistance.award_transaction_observation
    GROUP BY assistance_transaction_id
)
SELECT
    t.load_batch_id,
    COUNT(*) AS canonical_transactions,
    COUNT(*) FILTER (
        WHERE COALESCE(o.observation_count, 0) > 0
    ) AS with_observations,
    COUNT(*) FILTER (
        WHERE COALESCE(o.observation_count, 0) = 0
    ) AS without_observations,
    COUNT(*) FILTER (
        WHERE a.assistance_award_id IS NOT NULL
    ) AS with_award,
    COUNT(*) FILTER (
        WHERE a.assistance_award_id IS NULL
    ) AS without_award
FROM assistance.award_transaction t
LEFT JOIN observation_counts o
    ON o.assistance_transaction_id =
       t.assistance_transaction_id
LEFT JOIN assistance.award a
    ON a.assistance_award_id = t.assistance_award_id
WHERE t.load_batch_id IN (20, 21)
GROUP BY t.load_batch_id
ORDER BY t.load_batch_id;


SELECT '3. CERTIFIED VIEW COVERAGE' AS section;

SELECT
    t.load_batch_id,
    COUNT(*) AS canonical_transactions,
    COUNT(v.assistance_transaction_id) AS certified_transactions,
    COUNT(*) - COUNT(v.assistance_transaction_id)
        AS not_in_certified_view
FROM assistance.award_transaction t
LEFT JOIN analysis.v_certified_assistance_ledger v
    ON v.assistance_transaction_id =
       t.assistance_transaction_id
WHERE t.load_batch_id IN (20, 21)
GROUP BY t.load_batch_id
ORDER BY t.load_batch_id;


SELECT '4. RAILROAD RETIREMENT AL 57.001' AS section;

SELECT
    action_date_fiscal_year,
    load_batch_id,
    cfda_number,
    cfda_title,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
  AND TRIM(cfda_number) = '57.001'
GROUP BY
    action_date_fiscal_year,
    load_batch_id,
    cfda_number,
    cfda_title
ORDER BY action_date_fiscal_year;


SELECT '5. CERTIFIED HISTORICAL FISCAL-YEAR COVERAGE'
    AS section;

SELECT
    action_date_fiscal_year,
    load_batch_id,
    COUNT(*) AS certified_transactions,
    SUM(federal_action_obligation) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
GROUP BY action_date_fiscal_year, load_batch_id
ORDER BY action_date_fiscal_year, load_batch_id;

COMMIT;

SELECT 'ETL-204C-2B.3 COMPLETE - NO DATABASE WRITES';
