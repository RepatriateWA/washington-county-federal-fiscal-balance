
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '========================================================'
\echo 'ETL-213E v0.1 - HISTORICAL AGENCY ATTRIBUTION INVENTORY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '========================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '1. Raw transaction and observation columns'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name IN (
      'raw_award_transaction',
      'award_transaction_observation'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '2. Agency relationship completeness by fiscal year'

SELECT
    t.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE a.funding_agency_id IS NULL
    ) AS missing_funding_agency_id,
    COUNT(*) FILTER (
        WHERE a.awarding_agency_id IS NULL
    ) AS missing_awarding_agency_id,
    COUNT(*) FILTER (
        WHERE a.funding_agency_id IS NOT NULL
          AND a.awarding_agency_id IS NOT NULL
          AND a.funding_agency_id <> a.awarding_agency_id
    ) AS different_funding_awarding_agency,
    ROUND(SUM(t.federal_action_obligation)
        FILTER (WHERE a.funding_agency_id IS NULL), 2)
        AS missing_funding_agency_obligations,
    ROUND(SUM(t.federal_action_obligation)
        FILTER (WHERE a.awarding_agency_id IS NULL), 2)
        AS missing_awarding_agency_obligations
FROM procurement.award_transaction t
JOIN procurement.award a
  ON a.award_id = t.award_id
WHERE t.fiscal_year IN (2018, 2019)
GROUP BY t.fiscal_year
ORDER BY t.fiscal_year;

\echo ''
\echo '3. Agency reference table overview'

SELECT
    COUNT(*) AS agency_records,
    COUNT(*) FILTER (
        WHERE agency_code IS NOT NULL
    ) AS agencies_with_codes,
    COUNT(*) FILTER (
        WHERE parent_agency_id IS NOT NULL
    ) AS agencies_with_parent
FROM procurement.agency;

\echo ''
\echo '4. Raw historical batch structure'

SELECT
    load_batch_id,
    COUNT(*) AS raw_rows
FROM procurement.raw_award_transaction
WHERE load_batch_id IN (22, 23)
GROUP BY load_batch_id
ORDER BY load_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-213E v0.1 COMPLETE - NO DATABASE WRITES'
