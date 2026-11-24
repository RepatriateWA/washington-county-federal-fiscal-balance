
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-219C6 - VA ASSISTANCE POLICY EXCEPTIONS'
\echo 'FY2018-FY2024 / READ ONLY'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '300s';

\echo '1. VA ASSISTANCE PROGRAM-YEAR INVENTORY'

WITH transactions AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        BTRIM(cfda_number) AS program_code,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2018 AND 2024
      AND BTRIM(cfda_number) LIKE '64.%'
    GROUP BY 1,2
),
resolved AS (
    SELECT
        t.*,
        COUNT(DISTINCT
            m.federal_inflow_program_policy_mapping_id
        ) AS mapping_count,
        COUNT(DISTINCT
            m.resolved_accounting_disposition
        ) AS distinct_dispositions,
        STRING_AGG(
            DISTINCT m.resolved_accounting_disposition,
            ', '
        ) AS dispositions,
        STRING_AGG(
            DISTINCT m.methodology_version,
            ', '
        ) AS methodology_versions
    FROM transactions t
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND BTRIM(m.source_program_code) = t.program_code
     AND t.fiscal_year BETWEEN
         m.valid_from_fiscal_year
         AND m.valid_through_fiscal_year
    GROUP BY
        t.fiscal_year,
        t.program_code,
        t.transactions,
        t.obligations
)
SELECT
    fiscal_year,
    program_code,
    transactions,
    obligations,
    mapping_count,
    distinct_dispositions,
    dispositions,
    methodology_versions
FROM resolved
ORDER BY fiscal_year, program_code;

\echo '2. POLICY COVERAGE AND EXCEPTION SUMMARY'

WITH transactions AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        BTRIM(cfda_number) AS program_code,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2018 AND 2024
      AND BTRIM(cfda_number) LIKE '64.%'
    GROUP BY 1,2
),
resolved AS (
    SELECT
        t.*,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS mapping_count,
        COUNT(DISTINCT m.resolved_accounting_disposition)
            AS disposition_count,
        MIN(m.resolved_accounting_disposition)
            AS disposition
    FROM transactions t
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND BTRIM(m.source_program_code) = t.program_code
     AND t.fiscal_year BETWEEN
         m.valid_from_fiscal_year
         AND m.valid_through_fiscal_year
    GROUP BY
        t.fiscal_year,
        t.program_code,
        t.transactions,
        t.obligations
)
SELECT
    fiscal_year,
    CASE
        WHEN mapping_count = 0 THEN 'UNMAPPED'
        WHEN disposition_count > 1
            THEN 'CONFLICTING_DISPOSITIONS'
        WHEN mapping_count > 1
            THEN 'MULTIPLE_CONSISTENT_MAPPINGS'
        ELSE COALESCE(disposition,'UNRESOLVED')
    END AS policy_status,
    COUNT(*) AS program_years,
    SUM(transactions) AS transactions,
    SUM(obligations) AS net_obligations
FROM resolved
GROUP BY 1,2
ORDER BY 1,2;

DO $gate$
BEGIN
    IF current_setting('transaction_read_only') <> 'on'
    THEN
        RAISE EXCEPTION 'BLOCK: transaction not read-only';
    END IF;

    RAISE NOTICE
        'ETL-219C6 PROFILE COMPLETE; EXCEPTIONS REQUIRE REVIEW';
END
$gate$;

ROLLBACK;

\echo 'ETL-219C6 COMPLETE - READ ONLY'
