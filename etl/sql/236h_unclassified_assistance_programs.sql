-- ETL-236H
-- Largest assistance programs without an applicable program policy
-- READ ONLY
-- Diagnostic ranking only: award-level exceptions are not applied here.

BEGIN TRANSACTION READ ONLY;

WITH tx AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        cfda_title,
        federal_action_obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
),
program_coverage AS (
    SELECT
        t.assistance_transaction_id,
        COUNT(p.federal_inflow_program_policy_mapping_id)
            AS matching_policy_rows
    FROM tx t
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = t.cfda_number
     AND t.fiscal_year >= COALESCE(
         p.valid_from_fiscal_year, -2147483648
     )
     AND t.fiscal_year <= COALESCE(
         p.valid_through_fiscal_year, 2147483647
     )
    GROUP BY t.assistance_transaction_id
)
SELECT
    COALESCE(t.cfda_number, '(missing)') AS program_code,
    MAX(t.cfda_title) AS program_title,
    COUNT(*) AS transaction_rows,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS obligations_usd
FROM tx t
JOIN program_coverage p
  ON p.assistance_transaction_id = t.assistance_transaction_id
WHERE p.matching_policy_rows = 0
GROUP BY t.cfda_number
ORDER BY ABS(SUM(t.federal_action_obligation)) DESC
LIMIT 30;

ROLLBACK;