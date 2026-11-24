
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '========================================================'
\echo 'ETL-213G v0.1 - HISTORICAL AGENCY RECOVERY PREFLIGHT'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '========================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Raw agency completeness by fiscal year'

WITH historical AS (
    SELECT
        t.fiscal_year,
        t.award_id,
        t.federal_action_obligation AS obligation,
        a.funding_agency_id,
        a.awarding_agency_id,
        NULLIF(BTRIM(r.raw_record->>'funding_agency_code'), '')
            AS raw_funding_code,
        NULLIF(BTRIM(r.raw_record->>'awarding_agency_code'), '')
            AS raw_awarding_code,
        NULLIF(BTRIM(r.raw_record->>'funding_agency_name'), '')
            AS raw_funding_name,
        NULLIF(BTRIM(r.raw_record->>'awarding_agency_name'), '')
            AS raw_awarding_name
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
    fiscal_year,
    COUNT(*) AS observations,
    COUNT(*) FILTER (
        WHERE funding_agency_id IS NULL
    ) AS missing_canonical_funding,
    COUNT(*) FILTER (
        WHERE funding_agency_id IS NULL
          AND raw_funding_code IS NOT NULL
    ) AS recoverable_funding_code,
    COUNT(*) FILTER (
        WHERE funding_agency_id IS NULL
          AND raw_funding_code IS NULL
          AND raw_funding_name IS NOT NULL
    ) AS name_only_funding,
    COUNT(*) FILTER (
        WHERE awarding_agency_id IS NULL
          AND raw_awarding_code IS NOT NULL
    ) AS recoverable_awarding_code,
    COUNT(*) FILTER (
        WHERE raw_funding_code IS DISTINCT FROM raw_awarding_code
    ) AS different_raw_agency_codes,
    ROUND(SUM(obligation) FILTER (
        WHERE funding_agency_id IS NULL
          AND raw_funding_code IS NOT NULL
    ), 2) AS recoverable_funding_obligations
FROM historical
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. Existing agency code match coverage'

WITH raw_codes AS (
    SELECT DISTINCT
        NULLIF(BTRIM(raw_record->>'funding_agency_code'), '')
            AS agency_code
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)

    UNION

    SELECT DISTINCT
        NULLIF(BTRIM(raw_record->>'awarding_agency_code'), '')
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    COUNT(*) AS distinct_nonblank_codes,
    COUNT(*) FILTER (
        WHERE ag.agency_id IS NOT NULL
    ) AS matched_existing_agencies,
    COUNT(*) FILTER (
        WHERE ag.agency_id IS NULL
    ) AS unmatched_codes
FROM raw_codes rc
LEFT JOIN procurement.agency ag
  ON ag.agency_code = rc.agency_code
WHERE rc.agency_code IS NOT NULL;

\echo ''
\echo '3. Unmatched agency codes and observed names'

WITH raw_agencies AS (
    SELECT
        NULLIF(BTRIM(raw_record->>'funding_agency_code'), '')
            AS agency_code,
        NULLIF(BTRIM(raw_record->>'funding_agency_name'), '')
            AS agency_name
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)

    UNION ALL

    SELECT
        NULLIF(BTRIM(raw_record->>'awarding_agency_code'), ''),
        NULLIF(BTRIM(raw_record->>'awarding_agency_name'), '')
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    ra.agency_code,
    ra.agency_name,
    COUNT(*) AS observations
FROM raw_agencies ra
LEFT JOIN procurement.agency ag
  ON ag.agency_code = ra.agency_code
WHERE ra.agency_code IS NOT NULL
  AND ag.agency_id IS NULL
GROUP BY ra.agency_code, ra.agency_name
ORDER BY observations DESC, ra.agency_code
LIMIT 50;

\echo ''
\echo '4. Historical agency conflicts within shared awards'

WITH historical AS (
    SELECT
        t.award_id,
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
),
award_profile AS (
    SELECT
        award_id,
        COUNT(*) AS observations,
        COUNT(DISTINCT funding_code) AS distinct_funding_codes,
        COUNT(DISTINCT awarding_code) AS distinct_awarding_codes
    FROM historical
    GROUP BY award_id
)
SELECT
    COUNT(*) AS historical_awards,
    COUNT(*) FILTER (
        WHERE distinct_funding_codes > 1
    ) AS conflicting_funding_awards,
    COUNT(*) FILTER (
        WHERE distinct_awarding_codes > 1
    ) AS conflicting_awarding_awards,
    SUM(observations) FILTER (
        WHERE distinct_funding_codes > 1
           OR distinct_awarding_codes > 1
    ) AS observations_on_conflicting_awards
FROM award_profile;

ROLLBACK;

\echo ''
\echo 'ETL-213G v0.1 COMPLETE - NO DATABASE WRITES'
