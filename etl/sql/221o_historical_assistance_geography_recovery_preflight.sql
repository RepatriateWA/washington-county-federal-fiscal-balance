\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '===================================================='
\echo 'ETL-221O - HISTORICAL GEOGRAPHY RECOVERY PREFLIGHT'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '===================================================='

\echo ''
\echo '1. CANONICAL TRANSACTIONS WITH RAW SOURCE GEOGRAPHY'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.assistance_transaction_id,
        t.federal_action_obligation,
        NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_state_fips_code'), '')
            AS performance_state_fips,
        NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_recipient_state_fips_code'), '')
            AS recipient_state_fips,
        NULLIF(BTRIM(r.raw_record ->> 'recipient_state_code'), '')
            AS recipient_state_code,
        NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_county_fips_code'), '')
            AS performance_county_fips,
        NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_recipient_county_fips_code'), '')
            AS recipient_county_fips
    FROM assistance.award_transaction t
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = t.load_batch_id
     AND r.source_row_number = t.source_row_number
    WHERE t.load_batch_id IN (20, 21)
),
classified AS (
    SELECT
        *,
        CASE
            WHEN performance_state_fips = '53'
                THEN 'WA_PERFORMANCE'
            WHEN performance_state_fips IS NOT NULL
                 AND performance_state_fips <> '53'
                THEN 'NON_WA_PERFORMANCE'
            WHEN recipient_state_fips = '53'
                OR recipient_state_code = 'WA'
                THEN 'WA_RECIPIENT_ONLY'
            WHEN recipient_state_fips IS NOT NULL
                THEN 'NON_WA_RECIPIENT_ONLY'
            ELSE 'GEOGRAPHY_UNRESOLVED'
        END AS evidence_class
    FROM historical
)
SELECT
    fiscal_year,
    evidence_class,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars,
    COUNT(*) FILTER (
        WHERE performance_county_fips ~ '^53[0-9]{3}$'
    ) AS wa_performance_county_rows,
    COUNT(*) FILTER (
        WHERE recipient_county_fips ~ '^53[0-9]{3}$'
    ) AS wa_recipient_county_rows
FROM classified
GROUP BY fiscal_year, evidence_class
ORDER BY fiscal_year, evidence_class;

\echo ''
\echo '2. CONFLICTING STATE EVIDENCE'

SELECT
    t.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS conflicting_rows,
    SUM(t.federal_action_obligation) AS obligations_dollars
FROM assistance.award_transaction t
JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = t.load_batch_id
 AND r.source_row_number = t.source_row_number
WHERE t.load_batch_id IN (20, 21)
  AND NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_state_fips_code'), '')
      IS NOT NULL
  AND NULLIF(BTRIM(r.raw_record ->> 'prime_award_transaction_recipient_state_fips_code'), '')
      IS NOT NULL
  AND BTRIM(r.raw_record ->> 'prime_award_transaction_place_of_performance_state_fips_code')
      <> BTRIM(r.raw_record ->> 'prime_award_transaction_recipient_state_fips_code')
GROUP BY t.action_date_fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. HISTORICAL RAW TO CANONICAL LINKAGE COVERAGE'

SELECT
    r.load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(t.assistance_transaction_id) AS directly_linked_rows,
    COUNT(*) - COUNT(t.assistance_transaction_id)
        AS raw_rows_without_direct_canonical_match
FROM assistance.raw_award_transaction r
LEFT JOIN assistance.award_transaction t
  ON t.load_batch_id = r.load_batch_id
 AND t.source_row_number = r.source_row_number
WHERE r.load_batch_id IN (20, 21)
GROUP BY r.load_batch_id
ORDER BY r.load_batch_id;

ROLLBACK;