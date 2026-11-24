
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-223B - UNCLASSIFIED HISTORICAL ASSISTANCE CONCENTRATION'
\echo 'FY2018-FY2019 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- Reuse the ETL-223A source and policy matching logic.
-- Count applicable policy rows without multiplying source rows.

WITH historical AS (
    SELECT
        t.assistance_transaction_id,
        t.action_date_fiscal_year AS fiscal_year,
        COALESCE(NULLIF(BTRIM(t.cfda_number), ''), '[MISSING]')
            AS program_code,
        t.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(t.award_id_fain), ''),
            NULLIF(BTRIM(t.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger t
    WHERE
        (t.load_batch_id = 20
         AND t.action_date_fiscal_year = 2018)
        OR
        (t.load_batch_id = 21
         AND t.action_date_fiscal_year = 2019)
),
unclassified AS (
    SELECT h.*
    FROM historical h
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = h.program_code
          AND a.source_award_identifier = h.award_identifier
          AND h.fiscal_year BETWEEN
              COALESCE(a.valid_from_fiscal_year, -9999)
              AND COALESCE(a.valid_through_fiscal_year, 9999)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = h.program_code
          AND h.fiscal_year BETWEEN
              COALESCE(p.valid_from_fiscal_year, -9999)
              AND COALESCE(p.valid_through_fiscal_year, 9999)
    )
),
program_year AS (
    SELECT
        program_code,
        fiscal_year,
        COUNT(*) AS transactions,
        SUM(obligation) AS net_obligations,
        SUM(ABS(obligation)) AS absolute_obligations
    FROM unclassified
    GROUP BY program_code, fiscal_year
),
program_totals AS (
    SELECT
        program_code,
        SUM(transactions) AS transactions,
        SUM(net_obligations) AS net_obligations,
        SUM(absolute_obligations) AS absolute_obligations,
        SUM(net_obligations) FILTER (
            WHERE fiscal_year = 2018
        ) AS fy2018_net,
        SUM(net_obligations) FILTER (
            WHERE fiscal_year = 2019
        ) AS fy2019_net,
        SUM(transactions) FILTER (
            WHERE fiscal_year = 2018
        ) AS fy2018_transactions,
        SUM(transactions) FILTER (
            WHERE fiscal_year = 2019
        ) AS fy2019_transactions
    FROM program_year
    GROUP BY program_code
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            ORDER BY absolute_obligations DESC, program_code
        ) AS activity_rank,
        SUM(net_obligations) OVER () AS universe_net,
        SUM(absolute_obligations) OVER () AS universe_absolute
    FROM program_totals
)
SELECT
    activity_rank,
    program_code,
    COALESCE(fy2018_transactions, 0) AS fy2018_tx,
    COALESCE(fy2019_transactions, 0) AS fy2019_tx,
    ROUND(COALESCE(fy2018_net, 0)::numeric, 2)
        AS fy2018_net,
    ROUND(COALESCE(fy2019_net, 0)::numeric, 2)
        AS fy2019_net,
    ROUND(net_obligations::numeric, 2) AS combined_net,
    ROUND(absolute_obligations::numeric, 2)
        AS combined_absolute,
    ROUND(
        100 * absolute_obligations
        / NULLIF(universe_absolute, 0),
        3
    ) AS pct_absolute_activity
FROM ranked
WHERE activity_rank <= 40
ORDER BY activity_rank;

\echo ''
\echo 'ANNUAL UNCLASSIFIED CONTROL'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        COALESCE(NULLIF(BTRIM(t.cfda_number), ''), '[MISSING]')
            AS program_code,
        t.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(t.award_id_fain), ''),
            NULLIF(BTRIM(t.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger t
    WHERE
        (t.load_batch_id = 20
         AND t.action_date_fiscal_year = 2018)
        OR
        (t.load_batch_id = 21
         AND t.action_date_fiscal_year = 2019)
)
SELECT
    h.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT h.program_code) AS programs,
    ROUND(SUM(h.obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(h.obligation))::numeric, 2)
        AS absolute_obligations
FROM historical h
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_award_classification a
    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = h.program_code
      AND a.source_award_identifier = h.award_identifier
      AND h.fiscal_year BETWEEN
          COALESCE(a.valid_from_fiscal_year, -9999)
          AND COALESCE(a.valid_through_fiscal_year, 9999)
)
AND NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_program_policy_mapping p
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.source_program_code = h.program_code
      AND h.fiscal_year BETWEEN
          COALESCE(p.valid_from_fiscal_year, -9999)
          AND COALESCE(p.valid_through_fiscal_year, 9999)
)
GROUP BY h.fiscal_year
ORDER BY h.fiscal_year;

COMMIT;

\echo 'ETL-223B COMPLETE - NO DATABASE WRITES'
