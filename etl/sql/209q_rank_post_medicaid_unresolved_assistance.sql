
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209Q - POST-MEDICAID UNRESOLVED ASSISTANCE'
\echo 'FY2018-FY2019 / READ ONLY'
\echo '============================================================'

BEGIN;

-- ============================================================
-- 1. RECONSTRUCT ETL-209P ACCOUNTING RESOLUTION
-- ============================================================

CREATE OR REPLACE TEMP VIEW etl209q_resolution AS
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
)
SELECT
    *,
    COALESCE(
        award_disposition,
        program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS final_disposition
FROM resolved;

\echo ''
\echo '1. FULL BRIDGE CONTROL'

SELECT
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209q_resolution
GROUP BY final_disposition
ORDER BY final_disposition;

\echo ''
\echo '2. UNRESOLVED PROGRAM RANKING - TOP 40'

WITH program_totals AS (
    SELECT
        COALESCE(program_code, '[MISSING]') AS program_code,
        COUNT(*) AS transactions,
        COUNT(*) FILTER (WHERE obligation < 0)
            AS negative_transactions,
        COUNT(*) FILTER (WHERE obligation > 0)
            AS positive_transactions,
        ROUND(SUM(obligation)::numeric, 2)
            AS net_obligations,
        ROUND(SUM(ABS(obligation))::numeric, 2)
            AS gross_absolute_obligations,
        COUNT(*) FILTER (WHERE fiscal_year = 2018)
            AS fy2018_transactions,
        ROUND(COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2018
        ), 0)::numeric, 2) AS fy2018_net,
        COUNT(*) FILTER (WHERE fiscal_year = 2019)
            AS fy2019_transactions,
        ROUND(COALESCE(SUM(obligation) FILTER (
            WHERE fiscal_year = 2019
        ), 0)::numeric, 2) AS fy2019_net
    FROM etl209q_resolution
    WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
    GROUP BY COALESCE(program_code, '[MISSING]')
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY net_obligations DESC, program_code
    ) AS net_rank,
    *,
    ROUND(
        100.0 * net_obligations
        / NULLIF(SUM(net_obligations) OVER (), 0),
        3
    ) AS percent_unresolved_net
FROM program_totals
ORDER BY net_rank
LIMIT 40;

\echo ''
\echo '3. TOP 20 BY ABSOLUTE OBLIGATIONS'

SELECT
    COALESCE(program_code, '[MISSING]') AS program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM etl209q_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY COALESCE(program_code, '[MISSING]')
ORDER BY gross_absolute_obligations DESC
LIMIT 20;

\echo ''
\echo '4. UNRESOLVED CONTROL BY YEAR'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS distinct_programs,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209q_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '5. HARD CONTROL ASSERTIONS'

DO $$
DECLARE
    v_source bigint;
    v_distinct bigint;
    v_total numeric;
    v_unresolved bigint;
    v_unresolved_amount numeric;
    v_collision bigint;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ), 0),
        COUNT(*) FILTER (
            WHERE program_disposition IS NOT NULL
              AND award_disposition IS NOT NULL
        )
    INTO
        v_source,
        v_distinct,
        v_total,
        v_unresolved,
        v_unresolved_amount,
        v_collision
    FROM etl209q_resolution;

    IF v_source <> 207343
       OR v_distinct <> 207343
       OR ROUND(v_total, 2) <> 97097242523.58
       OR v_unresolved <> 197457
       OR ROUND(v_unresolved_amount, 2) <> 33622755859.87
       OR v_collision <> 0
    THEN
        RAISE EXCEPTION
            'ETL-209Q FAILED: rows %, distinct %, total %, unresolved %/%, collisions %',
            v_source,
            v_distinct,
            v_total,
            v_unresolved,
            v_unresolved_amount,
            v_collision;
    END IF;

    RAISE NOTICE
        'ETL-209Q PASS: 197457 unresolved transactions, $33622755859.87, zero collisions';
END
$$;

ROLLBACK;

\echo 'ETL-209Q COMPLETE - NO DATABASE WRITES'
