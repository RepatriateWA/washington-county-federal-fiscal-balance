
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209K - UNRESOLVED HISTORICAL ASSISTANCE PRIORITIES'
\echo 'FY2018-FY2019 / READ ONLY'
\echo '============================================================'

BEGIN READ ONLY;

WITH historical_source AS (
    SELECT
        s.assistance_transaction_id,
        s.action_date_fiscal_year AS fiscal_year,
        BTRIM(s.cfda_number) AS program_code,
        s.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(s.award_id_fain), ''),
            NULLIF(BTRIM(s.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger s
    WHERE (
           (s.load_batch_id = 20
            AND s.action_date_fiscal_year = 2018)
        OR (s.load_batch_id = 21
            AND s.action_date_fiscal_year = 2019)
    )
),
unresolved AS (
    SELECT s.*
    FROM historical_source s
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
ranked AS (
    SELECT
        program_code,
        COUNT(*) AS transactions,
        COUNT(DISTINCT fiscal_year) AS years_present,
        ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
        ROUND(
            SUM(ABS(obligation))::numeric, 2
        ) AS gross_absolute_obligations
    FROM unresolved
    GROUP BY program_code
),
later_policies AS (
    SELECT
        source_program_code AS program_code,
        COUNT(*) AS policy_rows,
        STRING_AGG(
            DISTINCT resolved_accounting_disposition,
            ', '
        ) AS later_dispositions,
        STRING_AGG(
            DISTINCT methodology_version,
            ', '
        ) AS later_methodologies
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND valid_from_fiscal_year <= 2024
      AND valid_through_fiscal_year >= 2020
    GROUP BY source_program_code
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY ABS(r.net_obligations) DESC,
                 r.program_code
    ) AS priority_rank,
    r.program_code,
    r.transactions,
    r.years_present,
    r.net_obligations,
    r.gross_absolute_obligations,
    CASE
        WHEN p.program_code IS NULL
            THEN 'NO LATER POLICY'
        ELSE 'LATER POLICY EXISTS - REVIEW'
    END AS policy_reuse_candidate,
    p.later_dispositions,
    p.later_methodologies
FROM ranked r
LEFT JOIN later_policies p
  ON p.program_code = r.program_code
ORDER BY
    ABS(r.net_obligations) DESC,
    r.program_code
LIMIT 100;

\echo ''
\echo 'CONTROL TOTALS - UNRESOLVED POPULATION'

WITH source AS (
    SELECT
        s.assistance_transaction_id,
        s.action_date_fiscal_year AS fiscal_year,
        BTRIM(s.cfda_number) AS program_code,
        s.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(s.award_id_fain), ''),
            NULLIF(BTRIM(s.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger s
    WHERE (
           (s.load_batch_id = 20 AND s.action_date_fiscal_year = 2018)
        OR (s.load_batch_id = 21 AND s.action_date_fiscal_year = 2019)
    )
),
unresolved AS (
    SELECT s.*
    FROM source s
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
)
SELECT
    COUNT(*) AS unresolved_transactions,
    COUNT(DISTINCT program_code) AS unresolved_programs,
    ROUND(SUM(obligation)::numeric, 2)
        AS unresolved_net_obligations
FROM unresolved;

ROLLBACK;

\echo 'ETL-209K COMPLETE - NO DATABASE WRITES'
