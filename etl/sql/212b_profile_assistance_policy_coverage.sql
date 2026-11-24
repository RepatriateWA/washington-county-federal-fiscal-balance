
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212B - ASSISTANCE POLICY ACCOUNTING COVERAGE'
\echo 'FY2018-FY2025'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. ANNUAL COVERAGE BY ACCOUNTING DISPOSITION'

WITH program_year AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS net_obligations,
        COUNT(*) FILTER (
            WHERE is_covid IS TRUE
        ) AS covid_transactions,
        COALESCE(SUM(federal_action_obligation) FILTER (
            WHERE is_covid IS TRUE
        ), 0) AS covid_obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2025
    GROUP BY
        action_date_fiscal_year,
        NULLIF(BTRIM(cfda_number), '')
),
resolved AS (
    SELECT
        p.*,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS matching_mappings,
        MIN(m.resolved_accounting_disposition)
            AS single_disposition
    FROM program_year p
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = p.program_code
     AND p.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, 2018)
         AND COALESCE(m.valid_through_fiscal_year, 2025)
    GROUP BY
        p.fiscal_year,
        p.program_code,
        p.transactions,
        p.net_obligations,
        p.covid_transactions,
        p.covid_obligations
),
classified AS (
    SELECT
        *,
        CASE
            WHEN program_code IS NULL
                THEN 'MISSING_PROGRAM_CODE'
            WHEN matching_mappings = 0
                THEN 'UNMAPPED'
            WHEN matching_mappings > 1
                THEN 'MULTIPLE_MAPPINGS'
            ELSE COALESCE(
                single_disposition,
                'NULL_DISPOSITION'
            )
        END AS accounting_status
    FROM resolved
)
SELECT
    fiscal_year,
    accounting_status,
    COUNT(*) AS program_years,
    SUM(transactions) AS transactions,
    ROUND(SUM(net_obligations)::numeric, 2)
        AS net_obligations,
    SUM(covid_transactions) AS covid_transactions,
    ROUND(SUM(covid_obligations)::numeric, 2)
        AS covid_net_obligations
FROM classified
GROUP BY fiscal_year, accounting_status
ORDER BY fiscal_year, accounting_status;

\echo ''
\echo '2. UNRESOLVED PROGRAMS RANKED BY ABSOLUTE OBLIGATIONS'

WITH program_year AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        NULLIF(BTRIM(cfda_number), '') AS program_code,
        MAX(cfda_title) AS program_title,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS net_obligations,
        SUM(ABS(federal_action_obligation))
            AS absolute_obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2025
    GROUP BY
        action_date_fiscal_year,
        NULLIF(BTRIM(cfda_number), '')
),
mapping_counts AS (
    SELECT
        p.*,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS matching_mappings
    FROM program_year p
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = p.program_code
     AND p.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, 2018)
         AND COALESCE(m.valid_through_fiscal_year, 2025)
    GROUP BY
        p.fiscal_year,
        p.program_code,
        p.program_title,
        p.transactions,
        p.net_obligations,
        p.absolute_obligations
)
SELECT
    fiscal_year,
    COALESCE(program_code, '[MISSING]') AS program_code,
    program_title,
    transactions,
    ROUND(net_obligations::numeric, 2)
        AS net_obligations,
    ROUND(absolute_obligations::numeric, 2)
        AS absolute_obligations,
    matching_mappings
FROM mapping_counts
WHERE matching_mappings = 0
ORDER BY absolute_obligations DESC
LIMIT 50;

\echo ''
\echo '3. MULTIPLE OR INVALID POLICY RESOLUTIONS'

WITH program_year AS (
    SELECT DISTINCT
        action_date_fiscal_year AS fiscal_year,
        NULLIF(BTRIM(cfda_number), '') AS program_code
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2025
),
matches AS (
    SELECT
        p.fiscal_year,
        p.program_code,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS mapping_count,
        STRING_AGG(
            m.methodology_version || ':' ||
            COALESCE(
                m.resolved_accounting_disposition,
                '[NULL]'
            ),
            ' | '
            ORDER BY m.methodology_version
        ) AS matching_policies
    FROM program_year p
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = p.program_code
     AND p.fiscal_year BETWEEN
         COALESCE(m.valid_from_fiscal_year, 2018)
         AND COALESCE(m.valid_through_fiscal_year, 2025)
    GROUP BY p.fiscal_year, p.program_code
)
SELECT *
FROM matches
WHERE mapping_count > 1
   OR (
       mapping_count = 1
       AND matching_policies LIKE '%[NULL]%'
   )
ORDER BY fiscal_year, program_code;

\echo ''
\echo '4. PROCUREMENT ACQUISITION BATCH STATUS'

SELECT
    load_batch_id,
    fiscal_year_start,
    fiscal_year_end,
    load_status
FROM procurement.load_batch
WHERE fiscal_year_start <= 2025
  AND fiscal_year_end >= 2018
ORDER BY fiscal_year_start, load_batch_id;

\echo ''
\echo '5. CANONICAL PROCUREMENT TRANSACTIONS BY YEAR'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT load_batch_id)
        AS load_batches,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2018 AND 2025
GROUP BY fiscal_year
ORDER BY fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-212B COMPLETE - NO DATABASE WRITES'
