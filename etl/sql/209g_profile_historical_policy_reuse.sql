
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209G - HISTORICAL POLICY REUSE ASSESSMENT'
\echo 'FY2018-FY2019 / EXISTING LATER-YEAR POLICIES'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '900s';

\echo ''
\echo '1. HISTORICAL SOURCE TOTALS BY FISCAL YEAR'

WITH historical AS MATERIALIZED (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM historical
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. LATER-YEAR POLICY COVERAGE FOR HISTORICAL PROGRAMS'

WITH historical AS MATERIALIZED (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
),
programs AS (
    SELECT
        program_code,
        COUNT(*) AS transactions,
        SUM(obligation) AS net_obligations
    FROM historical
    WHERE program_code NOT IN ('14.871', '57.001')
    GROUP BY program_code
),
later_policy AS (
    SELECT DISTINCT
        source_program_code AS program_code
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND (
          valid_from_fiscal_year >= 2020
          OR (
              valid_from_fiscal_year IS NULL
              AND valid_through_fiscal_year >= 2020
          )
      )
)
SELECT
    CASE
        WHEN l.program_code IS NOT NULL
            THEN 'LATER_POLICY_EXISTS'
        ELSE 'NO_LATER_PROGRAM_MAPPING'
    END AS reuse_category,
    COUNT(*) AS historical_programs,
    SUM(p.transactions) AS historical_transactions,
    ROUND(SUM(p.net_obligations)::numeric, 2)
        AS historical_net_obligations
FROM programs p
LEFT JOIN later_policy l USING (program_code)
GROUP BY 1
ORDER BY 1;

\echo ''
\echo '3. TOP 40 HISTORICAL PROGRAMS WITH LATER-YEAR POLICIES'

WITH historical AS MATERIALIZED (
    SELECT
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        MAX(cfda_title) OVER (
            PARTITION BY NULLIF(BTRIM(cfda_number), '')
        ) AS program_title,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
),
programs AS (
    SELECT
        program_code,
        MAX(program_title) AS program_title,
        COUNT(*) AS transactions,
        SUM(obligation) AS net_obligations
    FROM historical
    WHERE program_code NOT IN ('14.871', '57.001')
    GROUP BY program_code
),
policy_summary AS (
    SELECT
        source_program_code AS program_code,
        COUNT(*) AS policy_rows,
        MIN(valid_from_fiscal_year) AS earliest_policy_year,
        MAX(valid_through_fiscal_year) AS latest_policy_year,
        STRING_AGG(
            DISTINCT resolved_accounting_disposition,
            ', '
        ) AS later_dispositions,
        STRING_AGG(
            DISTINCT methodology_version,
            ', '
        ) AS methodology_versions
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND (
          valid_from_fiscal_year >= 2020
          OR (
              valid_from_fiscal_year IS NULL
              AND valid_through_fiscal_year >= 2020
          )
      )
    GROUP BY source_program_code
)
SELECT
    p.program_code,
    p.program_title,
    p.transactions,
    ROUND(p.net_obligations::numeric, 2) AS net_obligations,
    q.policy_rows,
    q.earliest_policy_year,
    q.latest_policy_year,
    q.later_dispositions,
    q.methodology_versions
FROM programs p
JOIN policy_summary q USING (program_code)
ORDER BY ABS(p.net_obligations) DESC, p.program_code
LIMIT 40;

\echo ''
\echo '4. TOP 25 HISTORICAL PROGRAMS WITHOUT LATER MAPPINGS'

WITH historical AS MATERIALIZED (
    SELECT
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        cfda_title AS program_title,
        federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
),
programs AS (
    SELECT
        program_code,
        MAX(program_title) AS program_title,
        COUNT(*) AS transactions,
        SUM(obligation) AS net_obligations
    FROM historical
    WHERE program_code NOT IN ('14.871', '57.001')
    GROUP BY program_code
)
SELECT
    p.program_code,
    p.program_title,
    p.transactions,
    ROUND(p.net_obligations::numeric, 2) AS net_obligations
FROM programs p
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_program_policy_mapping m
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = p.program_code
      AND (
          m.valid_from_fiscal_year >= 2020
          OR (
              m.valid_from_fiscal_year IS NULL
              AND m.valid_through_fiscal_year >= 2020
          )
      )
)
ORDER BY ABS(p.net_obligations) DESC, p.program_code
LIMIT 25;

\echo ''
\echo '5. PRIORITY OVERLAP FAMILIES - EXISTING POLICIES'

SELECT
    source_program_code AS program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN (
      '96.001', '96.002', '96.004', '96.006',
      '93.778', '93.773', '93.774', '93.770',
      '64.109', '64.028', '64.041',
      '10.551', '20.205', '93.600'
  )
ORDER BY
    source_program_code,
    valid_from_fiscal_year,
    methodology_version;

\echo ''
\echo '6. HISTORICAL OASDI OBLIGATION CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND BTRIM(cfda_number) IN ('96.001', '96.002', '96.004')
GROUP BY 1, 2
ORDER BY 1, 2;

ROLLBACK;

\echo 'ETL-209G COMPLETE - READ ONLY'
