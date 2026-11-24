-- ETL-237A
-- Procurement source reconciliation
-- READ ONLY

BEGIN TRANSACTION READ ONLY;

WITH raw_procurement AS (
    SELECT
        fiscal_year,
        COUNT(*) AS transaction_rows,
        SUM(federal_action_obligation) AS raw_obligations
    FROM procurement.award_transaction
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
),
registry AS (
    SELECT
        fiscal_year,
        candidate_observed_amount_usd AS registry_candidate,
        authorized_amount_usd,
        ledger_status,
        measure_basis,
        source_reference
    FROM accounting_registry.canonical_annual_ledger
    WHERE family_id = 'USASPENDING_PROCUREMENT'
      AND fiscal_year BETWEEN 2018 AND 2024
)
SELECT
    r.fiscal_year,
    r.transaction_rows,
    ROUND(r.raw_obligations, 2) AS raw_obligations_usd,
    ROUND(g.registry_candidate, 2) AS registry_candidate_usd,
    ROUND(r.raw_obligations - g.registry_candidate, 2)
        AS raw_minus_registry_usd,
    g.ledger_status,
    g.measure_basis,
    g.source_reference
FROM raw_procurement r
LEFT JOIN registry g USING (fiscal_year)
ORDER BY r.fiscal_year;

ROLLBACK;