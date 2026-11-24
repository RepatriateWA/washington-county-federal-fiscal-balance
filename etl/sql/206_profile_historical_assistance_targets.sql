\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-206 - FY2018/FY2019 HISTORICAL ASSISTANCE PROGRAM PROFILE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

WITH historical AS (
    SELECT
        load_batch_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        federal_action_obligation::numeric AS obligation
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
        COUNT(*) FILTER (WHERE fiscal_year = 2018)
            AS fy2018_transactions,
        COUNT(*) FILTER (WHERE fiscal_year = 2019)
            AS fy2019_transactions,
        SUM(obligation) FILTER (WHERE fiscal_year = 2018)
            AS fy2018_obligations,
        SUM(obligation) FILTER (WHERE fiscal_year = 2019)
            AS fy2019_obligations,
        SUM(obligation) AS combined_obligations
    FROM historical
    GROUP BY program_code
)
SELECT
    program_code,
    transactions,
    fy2018_transactions,
    fy2019_transactions,
    ROUND(COALESCE(fy2018_obligations, 0), 2)
        AS fy2018_obligations,
    ROUND(COALESCE(fy2019_obligations, 0), 2)
        AS fy2019_obligations,
    ROUND(combined_obligations, 2)
        AS combined_obligations
FROM programs
ORDER BY combined_obligations DESC NULLS LAST
LIMIT 75;

COMMIT;