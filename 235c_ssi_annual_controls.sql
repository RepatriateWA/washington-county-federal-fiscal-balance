\pset pager off

\echo ============================================================
\echo ETL-235C - SSI ANNUAL CONTROLS
\echo ============================================================

BEGIN TRANSACTION READ ONLY;

\echo
\echo === A. FY2018-FY2024 ANNUAL CONTROLS ===

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(
        COALESCE(SUM(federal_action_obligation), 0)::numeric,
        2
    ) AS net_obligations_usd,
    COUNT(DISTINCT award_id_fain) AS distinct_fain_count,
    COUNT(DISTINCT recipient_name) AS distinct_recipients,
    MIN(action_date) AS earliest_action,
    MAX(action_date) AS latest_action
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '96.006'
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

\echo
\echo === B. FY2018-FY2019 HISTORICAL SOURCE PROFILE ===

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    cfda_title,
    recipient_name,
    assistance_type_description,
    COUNT(*) AS transaction_count,
    ROUND(
        COALESCE(SUM(federal_action_obligation), 0)::numeric,
        2
    ) AS net_obligations_usd
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2019
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '96.006'
GROUP BY
    action_date_fiscal_year,
    cfda_number,
    cfda_title,
    recipient_name,
    assistance_type_description
ORDER BY action_date_fiscal_year, recipient_name;

\echo
\echo === C. FY2020-FY2024 CERTIFICATION REPRODUCTION ===

SELECT
    COUNT(*) AS transactions,
    ROUND(
        COALESCE(SUM(federal_action_obligation), 0)::numeric,
        2
    ) AS obligations_usd,
    CASE
        WHEN COUNT(*) = 4535
         AND ROUND(
             COALESCE(SUM(federal_action_obligation), 0)::numeric,
             2
         ) = 5676088795.00
        THEN 'PASS'
        ELSE 'FAIL'
    END AS etl_176_control
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '96.006';

ROLLBACK;

\echo
\echo === END ETL-235C ===
