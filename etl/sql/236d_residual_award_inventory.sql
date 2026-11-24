-- ETL-236D
-- Residual award and overlap-policy inventory
-- READ ONLY; no source-policy or registry changes

BEGIN TRANSACTION READ ONLY;

-- 1. Assistance obligations by fiscal year and COVID flag.
SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(is_covid, FALSE) AS is_covid,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS gross_obligations_usd
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
GROUP BY action_date_fiscal_year, COALESCE(is_covid, FALSE)
ORDER BY action_date_fiscal_year, is_covid;

-- 2. Procurement obligations by fiscal year.
SELECT
    fiscal_year,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS gross_obligations_usd
FROM procurement.award_transaction
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

-- 3. Existing award-level accounting dispositions.
SELECT
    source_system,
    inflow_family,
    accounting_disposition,
    COUNT(*) AS classification_rows
FROM reference.federal_inflow_award_classification
GROUP BY
    source_system,
    inflow_family,
    accounting_disposition
ORDER BY
    source_system,
    inflow_family,
    accounting_disposition;

-- 4. Existing program-level policy dispositions.
SELECT
    source_system,
    resolved_accounting_disposition,
    COUNT(*) AS mapping_rows
FROM reference.federal_inflow_program_policy_mapping
GROUP BY
    source_system,
    resolved_accounting_disposition
ORDER BY
    source_system,
    resolved_accounting_disposition;

ROLLBACK;