-- ETL-236I
-- USAspending additive candidate: COVID and IIJA decomposition
-- READ ONLY; diagnostic, not ledger authorization

BEGIN TRANSACTION READ ONLY;

WITH tx AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        federal_action_obligation,
        COALESCE(is_covid, FALSE) AS is_covid,
        COALESCE(is_iija, FALSE) AS is_iija
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
),
policy AS (
    SELECT
        t.assistance_transaction_id,
        COUNT(DISTINCT p.resolved_accounting_disposition)
            AS disposition_count,
        MIN(p.resolved_accounting_disposition)
            AS disposition
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
additive AS (
    SELECT t.*
    FROM tx t
    JOIN policy p
      ON p.assistance_transaction_id = t.assistance_transaction_id
    WHERE p.disposition_count = 1
      AND p.disposition = 'INCLUDE_ADDITIVE'
)
SELECT
    fiscal_year,
    COUNT(*) AS transaction_rows,

    ROUND(SUM(federal_action_obligation), 2)
        AS additive_obligations_usd,

    ROUND(SUM(federal_action_obligation)
        FILTER (WHERE is_covid), 2)
        AS covid_tagged_usd,

    ROUND(SUM(federal_action_obligation)
        FILTER (WHERE is_iija), 2)
        AS iija_tagged_usd,

    ROUND(SUM(federal_action_obligation)
        FILTER (WHERE is_covid AND is_iija), 2)
        AS both_tagged_usd,

    ROUND(SUM(federal_action_obligation)
        FILTER (WHERE NOT is_covid AND NOT is_iija), 2)
        AS neither_tagged_usd

FROM additive
GROUP BY fiscal_year
ORDER BY fiscal_year;

ROLLBACK;