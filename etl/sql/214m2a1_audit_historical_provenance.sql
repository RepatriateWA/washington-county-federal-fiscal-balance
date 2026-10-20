
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214M2A-1 - HISTORICAL PROVENANCE AUDIT'
\echo 'FY2018-FY2019 / SIX ASSISTANCE PROGRAMS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. HISTORICAL SOURCE AND OBSERVATION COVERAGE'

WITH target AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        federal_action_obligation AS obligation,
        recipient_id,
        recipient_identity_key,
        recipient_name,
        funding_agency_id,
        funding_agency_name,
        awarding_agency_id,
        awarding_agency_name
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND TRIM(cfda_number) IN (
        '10.555', '84.010', '84.027',
        '84.063', '93.558', '93.600'
    )
),
observation AS (
    SELECT
        t.*,
        o.raw_assistance_transaction_id,
        o.award_transaction_observation_id,
        o.recipient_id AS observed_recipient_id,
        o.recipient_identity_key AS observed_recipient_key,
        o.recipient_name AS observed_recipient_name,
        o.funding_agency_id AS observed_funding_agency_id,
        o.funding_agency_name AS observed_funding_agency_name,
        o.awarding_agency_id AS observed_awarding_agency_id,
        o.awarding_agency_name AS observed_awarding_agency_name
    FROM target t
    LEFT JOIN analysis.v_assistance_transaction_observation_ledger o
      ON o.assistance_transaction_id = t.assistance_transaction_id
)
SELECT
    program_code,
    fiscal_year,
    COUNT(DISTINCT assistance_transaction_id)
        AS certified_transactions,
    COUNT(*) AS joined_rows,
    COUNT(*) FILTER (
        WHERE raw_assistance_transaction_id IS NOT NULL
    ) AS rows_with_raw_observation,
    COUNT(*) FILTER (
        WHERE award_transaction_observation_id IS NOT NULL
    ) AS rows_with_award_observation,
    COUNT(*) FILTER (
        WHERE observed_recipient_id IS NOT NULL
           OR NULLIF(observed_recipient_key, '') IS NOT NULL
           OR NULLIF(observed_recipient_name, '') IS NOT NULL
    ) AS rows_with_recipient_evidence,
    COUNT(*) FILTER (
        WHERE observed_funding_agency_id IS NOT NULL
           OR NULLIF(observed_funding_agency_name, '') IS NOT NULL
    ) AS rows_with_funding_agency_evidence,
    COUNT(*) FILTER (
        WHERE observed_awarding_agency_id IS NOT NULL
           OR NULLIF(observed_awarding_agency_name, '') IS NOT NULL
    ) AS rows_with_awarding_agency_evidence,
    COUNT(*) FILTER (
        WHERE recipient_id IS NOT NULL
    ) AS certified_recipient_links,
    ROUND(SUM(obligation) FILTER (
        WHERE raw_assistance_transaction_id IS NULL
    ), 2) AS obligations_without_observation
FROM observation
GROUP BY program_code, fiscal_year
ORDER BY program_code, fiscal_year;

\echo ''
\echo '2. OBSERVATION-LEVEL LINKAGE DIAGNOSIS'

WITH target AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND TRIM(cfda_number) IN (
        '10.555', '84.010', '84.027',
        '84.063', '93.558', '93.600'
    )
)
SELECT
    t.program_code,
    t.fiscal_year,
    COUNT(*) AS observation_rows,
    COUNT(*) FILTER (
        WHERE o.raw_assistance_transaction_id IS NULL
    ) AS no_raw_observation,
    COUNT(*) FILTER (
        WHERE o.raw_assistance_transaction_id IS NOT NULL
          AND o.recipient_id IS NULL
    ) AS raw_observation_without_recipient_link,
    COUNT(*) FILTER (
        WHERE o.raw_assistance_transaction_id IS NOT NULL
          AND o.funding_agency_id IS NULL
    ) AS raw_observation_without_funding_agency_link,
    COUNT(*) FILTER (
        WHERE o.raw_assistance_transaction_id IS NOT NULL
          AND o.awarding_agency_id IS NULL
    ) AS raw_observation_without_awarding_agency_link,
    COUNT(DISTINCT o.recipient_identity_key)
        AS distinct_recipient_identity_keys,
    COUNT(DISTINCT o.funding_agency_name)
        AS distinct_funding_agencies,
    COUNT(DISTINCT o.awarding_agency_name)
        AS distinct_awarding_agencies
FROM target t
LEFT JOIN analysis.v_assistance_transaction_observation_ledger o
  ON o.assistance_transaction_id = t.assistance_transaction_id
GROUP BY t.program_code, t.fiscal_year
ORDER BY t.program_code, t.fiscal_year;

\echo ''
\echo '3. DATABASE SOURCE TABLE DISCOVERY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'assistance', 'usa'
)
AND (
    table_name ILIKE '%award%'
    OR table_name ILIKE '%transaction%'
    OR table_name ILIKE '%recipient%'
    OR table_name ILIKE '%agency%'
)
ORDER BY table_schema, table_name;

\echo ''
\echo '4. RAW SOURCE COLUMN DISCOVERY'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema IN (
    'assistance', 'usa'
)
AND (
    table_name ILIKE '%transaction%'
    OR table_name ILIKE '%award%'
)
AND (
    column_name ILIKE '%recipient%'
    OR column_name ILIKE '%agency%'
    OR column_name ILIKE '%source%'
    OR column_name ILIKE '%batch%'
    OR column_name ILIKE '%raw%'
)
ORDER BY table_schema, table_name, ordinal_position;

ROLLBACK;

\echo 'ETL-214M2A-1 COMPLETE - NO DATABASE WRITES'
