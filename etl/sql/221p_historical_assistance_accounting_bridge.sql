\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '===================================================='
\echo 'ETL-221P - HISTORICAL ASSISTANCE ACCOUNTING BRIDGE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '===================================================='

\echo ''
\echo '1. HISTORICAL PROGRAM POLICY DISPOSITIONS'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.assistance_transaction_id,
        t.cfda_number,
        t.federal_action_obligation,
        t.assistance_award_unique_key,
        t.award_id_fain,
        t.award_id_uri
    FROM analysis.v_certified_assistance_ledger t
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = t.load_batch_id
     AND r.source_row_number = t.source_row_number
    WHERE t.load_batch_id IN (20, 21)
      AND BTRIM(
          r.raw_record ->>
          'prime_award_transaction_place_of_performance_state_fips_code'
      ) = '53'
),
policy AS (
    SELECT
        h.*,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS matching_policies,
        MIN(m.resolved_accounting_disposition)
            AS disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = h.cfda_number
     AND h.fiscal_year >= m.valid_from_fiscal_year
     AND (
         m.valid_through_fiscal_year IS NULL
         OR h.fiscal_year <= m.valid_through_fiscal_year
     )
    GROUP BY
        h.fiscal_year,
        h.assistance_transaction_id,
        h.cfda_number,
        h.federal_action_obligation,
        h.assistance_award_unique_key,
        h.award_id_fain,
        h.award_id_uri
)
SELECT
    fiscal_year,
    CASE
        WHEN matching_policies = 0
            THEN 'NO_PROGRAM_MAPPING'
        WHEN matching_policies > 1
            THEN 'MULTIPLE_PROGRAM_MAPPINGS'
        ELSE disposition
    END AS provisional_disposition,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars
FROM policy
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '2. HISTORICAL AWARD CLASSIFICATION MATCH COVERAGE'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.assistance_transaction_id,
        t.assistance_award_unique_key,
        t.award_id_fain,
        t.award_id_uri,
        t.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.load_batch_id IN (20, 21)
),
matches AS (
    SELECT
        h.fiscal_year,
        h.assistance_transaction_id,
        h.federal_action_obligation,
        COUNT(DISTINCT a.federal_inflow_award_classification_id)
            AS matching_classifications
    FROM historical h
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND h.fiscal_year >= a.valid_from_fiscal_year
     AND (
         a.valid_through_fiscal_year IS NULL
         OR h.fiscal_year <= a.valid_through_fiscal_year
     )
     AND a.source_award_identifier IN (
         h.assistance_award_unique_key,
         h.award_id_fain,
         h.award_id_uri
     )
    GROUP BY
        h.fiscal_year,
        h.assistance_transaction_id,
        h.federal_action_obligation
)
SELECT
    fiscal_year,
    CASE
        WHEN matching_classifications = 0
            THEN 'NO_AWARD_OVERRIDE'
        WHEN matching_classifications = 1
            THEN 'ONE_AWARD_OVERRIDE'
        ELSE 'MULTIPLE_AWARD_OVERRIDES'
    END AS override_status,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars
FROM matches
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '3. HISTORICAL PROGRAM COVERAGE BY LISTING'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.cfda_number,
        t.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.load_batch_id IN (20, 21)
)
SELECT
    h.fiscal_year,
    h.cfda_number,
    COUNT(*) AS transaction_rows,
    SUM(h.federal_action_obligation) AS obligations_dollars,
    COUNT(DISTINCT m.federal_inflow_program_policy_mapping_id)
        AS matching_policy_rows
FROM historical h
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = h.cfda_number
 AND h.fiscal_year >= m.valid_from_fiscal_year
 AND (
     m.valid_through_fiscal_year IS NULL
     OR h.fiscal_year <= m.valid_through_fiscal_year
 )
GROUP BY h.fiscal_year, h.cfda_number
ORDER BY
    h.fiscal_year,
    ABS(SUM(h.federal_action_obligation)) DESC
LIMIT 40;

\echo ''
\echo '4. CANONICAL DOLLAR CONSERVATION CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS canonical_transactions,
    SUM(federal_action_obligation) AS canonical_obligations
FROM analysis.v_certified_assistance_ledger
WHERE load_batch_id IN (20, 21)
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;

ROLLBACK;