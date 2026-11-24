\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-239B1E7D - IRS REFUND / ADDITIVE ASSISTANCE PROFILE'
\echo 'READ ONLY - NO LEDGER OR POLICY CHANGES'

WITH tx AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        assistance_award_unique_key,
        award_id_fain,
        award_id_uri,
        federal_action_obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2018 AND 2024
),
program_policy AS (
    SELECT
        t.assistance_transaction_id,
        COUNT(DISTINCT p.resolved_accounting_disposition)
            AS distinct_dispositions,
        MIN(p.resolved_accounting_disposition) AS disposition
    FROM tx t
    JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = t.cfda_number
     AND t.fiscal_year >= COALESCE(
         p.valid_from_fiscal_year, -2147483648
     )
     AND t.fiscal_year <= COALESCE(
         p.valid_through_fiscal_year, 2147483647
     )
    GROUP BY t.assistance_transaction_id
),
award_policy AS (
    SELECT
        t.assistance_transaction_id,
        COUNT(DISTINCT a.accounting_disposition)
            AS distinct_dispositions,
        MIN(a.accounting_disposition) AS disposition
    FROM tx t
    JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = t.cfda_number
     AND t.fiscal_year >= COALESCE(
         a.valid_from_fiscal_year, -2147483648
     )
     AND t.fiscal_year <= COALESCE(
         a.valid_through_fiscal_year, 2147483647
     )
     AND a.source_award_identifier IN (
         t.assistance_award_unique_key,
         t.award_id_fain,
         t.award_id_uri
     )
    GROUP BY t.assistance_transaction_id
),
classified AS MATERIALIZED (
    SELECT
        t.*,
        CASE
            WHEN a.distinct_dispositions > 1
                THEN 'CONFLICTING_AWARD_POLICIES'
            WHEN a.disposition IS NOT NULL
                THEN a.disposition
            WHEN p.distinct_dispositions > 1
                THEN 'CONFLICTING_PROGRAM_POLICIES'
            WHEN p.disposition IS NOT NULL
                THEN p.disposition
            ELSE 'NO_APPLICABLE_POLICY'
        END AS current_disposition
    FROM tx t
    LEFT JOIN award_policy a
      USING (assistance_transaction_id)
    LEFT JOIN program_policy p
      USING (assistance_transaction_id)
),
additive AS (
    SELECT *
    FROM classified
    WHERE current_disposition = 'INCLUDE_ADDITIVE'
),
program_totals AS (
    SELECT
        cfda_number,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT fiscal_year) AS fiscal_years,
        ROUND(SUM(federal_action_obligation)::numeric, 2)
            AS net_obligations_usd
    FROM additive
    GROUP BY cfda_number
)
SELECT
    cfda_number,
    transaction_count,
    fiscal_years,
    net_obligations_usd
FROM program_totals
ORDER BY ABS(net_obligations_usd) DESC, cfda_number
LIMIT 100;

\echo 'CONTROL: Ranked top 100 additive assistance programs.'
\echo 'NOTE: This does not yet certify absence of IRS overlap.'

ROLLBACK;