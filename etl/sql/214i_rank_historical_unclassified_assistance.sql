
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214I - HISTORICAL UNCLASSIFIED ASSISTANCE PRIORITIES'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

WITH source_rows AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        cfda_title AS program_title,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(award_id_fain), ''),
            NULLIF(TRIM(award_id_uri), '')
        ) AS award_identifier,
        is_covid,
        is_iija
    FROM analysis.v_certified_assistance_ledger
    WHERE (load_batch_id = 20
           AND action_date_fiscal_year = 2018)
       OR (load_batch_id = 21
           AND action_date_fiscal_year = 2019)
),
unclassified AS MATERIALIZED (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (
              a.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= a.valid_from_fiscal_year
          )
          AND (
              a.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= a.valid_through_fiscal_year
          )
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (
              p.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= p.valid_from_fiscal_year
          )
          AND (
              p.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= p.valid_through_fiscal_year
          )
    )
),
program_totals AS (
    SELECT
        program_code,
        MAX(program_title) AS program_title,
        COUNT(*) AS transactions,
        COUNT(*) FILTER (
            WHERE fiscal_year = 2018
        ) AS fy2018_transactions,
        COUNT(*) FILTER (
            WHERE fiscal_year = 2019
        ) AS fy2019_transactions,
        COALESCE(SUM(obligation), 0) AS net_obligations,
        COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2018
        ), 0) AS fy2018_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2019
        ), 0) AS fy2019_net,
        COUNT(*) FILTER (
            WHERE is_covid IS TRUE
        ) AS covid_flagged,
        COUNT(*) FILTER (
            WHERE is_iija IS TRUE
        ) AS iija_flagged
    FROM unclassified
    GROUP BY program_code
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY ABS(net_obligations) DESC, program_code
    ) AS priority_rank,
    program_code,
    program_title,
    transactions,
    fy2018_transactions,
    fy2019_transactions,
    ROUND(net_obligations, 2) AS combined_net_dollars,
    ROUND(fy2018_net, 2) AS fy2018_net_dollars,
    ROUND(fy2019_net, 2) AS fy2019_net_dollars,
    covid_flagged,
    iija_flagged
FROM program_totals
ORDER BY priority_rank
LIMIT 40;

\echo ''
\echo '2. UNCLASSIFIED CONTROL TOTALS'

WITH source_rows AS (
    SELECT
        l.assistance_transaction_id,
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        COALESCE(
            NULLIF(TRIM(l.award_id_fain), ''),
            NULLIF(TRIM(l.award_id_uri), '')
        ) AS award_identifier,
        l.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger l
    WHERE (l.load_batch_id = 20
           AND l.action_date_fiscal_year = 2018)
       OR (l.load_batch_id = 21
           AND l.action_date_fiscal_year = 2019)
)
SELECT
    s.fiscal_year,
    COUNT(*) AS unclassified_transactions,
    COUNT(DISTINCT s.program_code) AS unclassified_programs,
    ROUND(SUM(s.obligation), 2) AS unclassified_net_dollars
FROM source_rows s
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_award_classification a
    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = s.program_code
      AND a.source_award_identifier = s.award_identifier
      AND (a.valid_from_fiscal_year IS NULL
           OR s.fiscal_year >= a.valid_from_fiscal_year)
      AND (a.valid_through_fiscal_year IS NULL
           OR s.fiscal_year <= a.valid_through_fiscal_year)
)
AND NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_program_policy_mapping p
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.source_program_code = s.program_code
      AND (p.valid_from_fiscal_year IS NULL
           OR s.fiscal_year >= p.valid_from_fiscal_year)
      AND (p.valid_through_fiscal_year IS NULL
           OR s.fiscal_year <= p.valid_through_fiscal_year)
)
GROUP BY s.fiscal_year
ORDER BY s.fiscal_year;

ROLLBACK;

\echo 'ETL-214I COMPLETE - NO DATABASE WRITES'
