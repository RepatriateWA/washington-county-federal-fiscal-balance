-- ETL-236G
-- USAspending assistance classified-dollar bridge
-- READ ONLY; no ledger authorizations or database writes

BEGIN TRANSACTION READ ONLY;

WITH tx AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        assistance_award_unique_key,
        award_id_fain,
        award_id_uri,
        federal_action_obligation,
        is_covid
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
),
program_policy AS (
    SELECT
        t.assistance_transaction_id,
        COUNT(DISTINCT p.resolved_accounting_disposition)
            AS distinct_dispositions,
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
award_policy AS (
    SELECT
        t.assistance_transaction_id,
        COUNT(DISTINCT a.accounting_disposition)
            AS distinct_dispositions,
        MIN(a.accounting_disposition)
            AS disposition
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
classified AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation,
        t.is_covid,
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
        END AS disposition
    FROM tx t
    LEFT JOIN award_policy a
      ON a.assistance_transaction_id =
         t.assistance_transaction_id
    LEFT JOIN program_policy p
      ON p.assistance_transaction_id =
         t.assistance_transaction_id
)
SELECT
    fiscal_year,
    disposition,
    COUNT(*) AS transaction_rows,
    ROUND(SUM(federal_action_obligation), 2)
        AS obligations_usd,
    ROUND(
        SUM(federal_action_obligation)
        FILTER (WHERE is_covid IS TRUE),
        2
    ) AS covid_flagged_obligations_usd
FROM classified
GROUP BY fiscal_year, disposition
ORDER BY fiscal_year, disposition;

ROLLBACK;