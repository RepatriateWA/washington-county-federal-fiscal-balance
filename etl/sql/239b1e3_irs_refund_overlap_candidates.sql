\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-239B1E3 | IRS REFUND OVERLAP CANDIDATES'
\echo 'READ ONLY - NO DATABASE WRITES'

WITH candidates AS MATERIALIZED (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        cfda_title,
        awarding_agency_name,
        funding_agency_name,
        federal_action_obligation,
        assistance_transaction_id,
        CASE
            WHEN (
                COALESCE(cfda_title, '') || ' ' ||
                COALESCE(canonical_award_description, '') || ' ' ||
                COALESCE(transaction_description, '')
            ) ~* 'economic impact payment|stimulus payment|recovery rebate'
                THEN 'EIP_RECOVERY_REBATE'

            WHEN (
                COALESCE(cfda_title, '') || ' ' ||
                COALESCE(canonical_award_description, '') || ' ' ||
                COALESCE(transaction_description, '')
            ) ~* 'advance child tax credit|advanced child tax credit'
                THEN 'ADVANCE_CHILD_TAX_CREDIT'

            WHEN (
                COALESCE(cfda_title, '') || ' ' ||
                COALESCE(canonical_award_description, '') || ' ' ||
                COALESCE(transaction_description, '')
            ) ~* 'refundable tax credit|earned income tax credit|premium tax credit'
                THEN 'OTHER_REFUNDABLE_CREDIT'

            WHEN (
                COALESCE(cfda_title, '') || ' ' ||
                COALESCE(canonical_award_description, '') || ' ' ||
                COALESCE(transaction_description, '')
            ) ~* 'internal revenue service|tax refund'
                THEN 'IRS_REFUND_RELATED'

            ELSE NULL
        END AS match_category
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2018 AND 2024
)
SELECT
    fiscal_year,
    match_category,
    cfda_number,
    LEFT(MAX(cfda_title), 100) AS program_title,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation_usd,
    MIN(assistance_transaction_id)
        AS example_transaction_id
FROM candidates
WHERE match_category IS NOT NULL
GROUP BY
    fiscal_year,
    match_category,
    cfda_number
ORDER BY
    fiscal_year,
    match_category,
    ABS(SUM(federal_action_obligation)) DESC;

\echo 'CHECK | Completed candidate search'
\echo 'NOTE | A zero-row result is not proof of zero IRS payments.'
\echo 'NOTE | Candidate amounts are not yet authorized inflows.'

ROLLBACK;
\echo 'ETL-239B1E3 COMPLETE'