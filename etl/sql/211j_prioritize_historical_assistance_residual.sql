
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211J - HISTORICAL ASSISTANCE RESIDUAL PRIORITIZATION'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - NO TEMP TABLES OR VIEWS'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
resolved AS (
    SELECT
        h.*,
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
),
classified AS (
    SELECT
        *,
        COALESCE(
            award_disposition,
            program_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS final_disposition
    FROM resolved
),
baseline AS (
    SELECT
        COUNT(*) AS total_rows,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_rows,
        COALESCE(SUM(obligation), 0)
            AS total_net,
        COUNT(*) FILTER (
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ) AS unresolved_rows,
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ), 0) AS unresolved_net
    FROM classified
),
residual AS (
    SELECT *
    FROM classified
    WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
),
program_summary AS (
    SELECT
        program_code,
        COUNT(*) AS transactions,
        COUNT(*) FILTER (
            WHERE fiscal_year = 2018
        ) AS fy2018_transactions,
        COUNT(*) FILTER (
            WHERE fiscal_year = 2019
        ) AS fy2019_transactions,
        COALESCE(SUM(obligation), 0)
            AS net_obligations,
        COALESCE(SUM(obligation) FILTER (
            WHERE obligation > 0
        ), 0) AS positive_obligations,
        COALESCE(SUM(obligation) FILTER (
            WHERE obligation < 0
        ), 0) AS negative_obligations,
        COUNT(*) FILTER (
            WHERE obligation < 0
        ) AS negative_transactions,
        COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2018
        ), 0) AS fy2018_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2019
        ), 0) AS fy2019_net
    FROM residual
    GROUP BY program_code
),
ranked AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY ABS(net_obligations) DESC,
                     program_code NULLS LAST
        ) AS priority_rank,
        *
    FROM program_summary
)
SELECT
    CASE
        WHEN b.total_rows = 207343
         AND b.distinct_rows = 207343
         AND ROUND(b.total_net, 2) = 97097242523.58
         AND b.unresolved_rows = 190008
         AND ROUND(b.unresolved_net, 2) = 20751062827.73
        THEN 'PASS'
        ELSE 'FAIL'
    END AS baseline_status,
    r.priority_rank,
    COALESCE(r.program_code, '[MISSING]') AS program_code,
    r.transactions,
    r.fy2018_transactions,
    r.fy2019_transactions,
    ROUND(r.net_obligations::numeric, 2)
        AS net_obligations,
    ROUND(r.positive_obligations::numeric, 2)
        AS positive_obligations,
    ROUND(r.negative_obligations::numeric, 2)
        AS negative_obligations,
    r.negative_transactions,
    ROUND(r.fy2018_net::numeric, 2)
        AS fy2018_net,
    ROUND(r.fy2019_net::numeric, 2)
        AS fy2019_net,
    ROUND(
        100 * ABS(r.net_obligations)
        / NULLIF(ABS(b.unresolved_net), 0),
        4
    ) AS pct_of_unresolved_net
FROM ranked r
CROSS JOIN baseline b
ORDER BY r.priority_rank
LIMIT 50;

ROLLBACK;

\echo 'ETL-211J COMPLETE - NO DATABASE WRITES'
