-- ETL-236J
-- Railroad award-classification linkage
-- READ ONLY

BEGIN TRANSACTION READ ONLY;

-- 1. Railroad obligations by year.
SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_rows,
    ROUND(SUM(federal_action_obligation), 2)
        AS obligations_usd,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_canonical_award_keys,
    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_values,
    COUNT(DISTINCT award_id_uri)
        AS distinct_uri_values
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
  AND cfda_number = '57.001'
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

-- 2. Existing railroad award classifications.
SELECT
    accounting_disposition,
    inflow_family,
    COUNT(*) AS classification_rows,
    COUNT(DISTINCT source_award_identifier)
        AS distinct_award_identifiers,
    MIN(valid_from_fiscal_year) AS earliest_policy_year,
    MAX(valid_through_fiscal_year) AS latest_policy_year
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '57.001'
GROUP BY accounting_disposition, inflow_family
ORDER BY accounting_disposition, inflow_family;

-- 3. Compare a few identifier examples.
SELECT
    'TRANSACTION' AS record_type,
    assistance_award_unique_key AS identifier,
    award_id_fain,
    award_id_uri
FROM analysis.v_certified_assistance_ledger
WHERE cfda_number = '57.001'
  AND action_date_fiscal_year BETWEEN 2018 AND 2024
LIMIT 5;

SELECT
    'CLASSIFICATION' AS record_type,
    source_award_identifier AS identifier,
    inflow_family,
    accounting_disposition
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '57.001'
LIMIT 5;

ROLLBACK;