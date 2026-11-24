
\set ON_ERROR_STOP on
\pset pager off

\echo '=============================================================='
\echo 'ETL-214M2A - HISTORICAL AGENCY / RECIPIENT EVIDENCE'
\echo 'FY2018-FY2024 / SIX ADDITIVE ASSISTANCE PROGRAMS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. AVAILABLE SOURCE AND RECIPIENT COLUMNS'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (
        table_schema = 'analysis'
        AND table_name IN (
            'v_certified_assistance_ledger',
            'v_assistance_transaction_observation_ledger'
        )
    )
    AND (
        column_name ILIKE '%agency%'
        OR column_name ILIKE '%recipient%'
        OR column_name ILIKE '%award%'
        OR column_name ILIKE '%fund%'
        OR column_name ILIKE '%assistance%'
    )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '2. CERTIFIED-VIEW AGENCY AND RECIPIENT KEY DISCOVERY'

WITH sample AS (
    SELECT TO_JSONB(l) AS record
    FROM analysis.v_certified_assistance_ledger l
    WHERE l.action_date_fiscal_year = 2018
      AND l.load_batch_id = 20
      AND TRIM(l.cfda_number) IN (
          '10.555', '84.010', '84.027',
          '84.063', '93.558', '93.600'
      )
    LIMIT 10
)
SELECT DISTINCT k.key AS available_column
FROM sample s
CROSS JOIN LATERAL JSONB_OBJECT_KEYS(s.record) AS k(key)
WHERE k.key ILIKE '%agency%'
   OR k.key ILIKE '%recipient%'
   OR k.key ILIKE '%award%'
   OR k.key ILIKE '%fund%'
ORDER BY available_column;

\echo ''
\echo '3. HISTORICAL AND RECENT SOURCE POPULATION PROFILE'

WITH source_rows AS MATERIALIZED (
    SELECT
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        l.assistance_transaction_id,
        l.federal_action_obligation AS obligation,
        TO_JSONB(l) AS record
    FROM analysis.v_certified_assistance_ledger l
    WHERE TRIM(l.cfda_number) IN (
        '10.555', '84.010', '84.027',
        '84.063', '93.558', '93.600'
    )
    AND (
        (l.action_date_fiscal_year = 2018
         AND l.load_batch_id = 20)
        OR
        (l.action_date_fiscal_year = 2019
         AND l.load_batch_id = 21)
        OR
        (l.action_date_fiscal_year BETWEEN 2020 AND 2024
         AND l.reference_state_abbreviation = 'WA')
    )
),
profile AS (
    SELECT
        fiscal_year,
        program_code,
        COUNT(*) AS transactions,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_transactions,
        ROUND(SUM(obligation), 2) AS net_obligations,
        COUNT(DISTINCT NULLIF(
            record ->> 'funding_agency_name', ''
        )) AS funding_agency_name_count,
        COUNT(DISTINCT NULLIF(
            record ->> 'awarding_agency_name', ''
        )) AS awarding_agency_name_count,
        COUNT(DISTINCT NULLIF(
            record ->> 'recipient_name', ''
        )) AS recipient_name_count,
        COUNT(*) FILTER (
            WHERE NULLIF(
                record ->> 'funding_agency_name', ''
            ) IS NOT NULL
        ) AS funding_agency_name_populated,
        COUNT(*) FILTER (
            WHERE NULLIF(
                record ->> 'awarding_agency_name', ''
            ) IS NOT NULL
        ) AS awarding_agency_name_populated,
        COUNT(*) FILTER (
            WHERE NULLIF(
                record ->> 'recipient_name', ''
            ) IS NOT NULL
        ) AS recipient_name_populated
    FROM source_rows
    GROUP BY fiscal_year, program_code
)
SELECT *
FROM profile
ORDER BY program_code, fiscal_year;

\echo ''
\echo '4. HISTORICAL POLICY SCOPE'

SELECT
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version,
    s.valid_from_fiscal_year AS source_policy_from,
    s.valid_through_fiscal_year AS source_policy_through,
    s.accounting_measure,
    s.preferred_source
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code IN (
      '10.555', '84.010', '84.027',
      '84.063', '93.558', '93.600'
  )
ORDER BY p.source_program_code;

ROLLBACK;

\echo 'ETL-214M2A COMPLETE - NO DATABASE WRITES'
