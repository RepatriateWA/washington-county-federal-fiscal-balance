\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '===================================================='
\echo 'ETL-221J - ASSISTANCE ACCOUNTING RECONCILIATION'
\echo 'FY2018-FY2024 - READ ONLY'
\echo '===================================================='

\echo ''
\echo '1. POLICY SOURCE SYSTEMS'

SELECT
    'PROGRAM_MAPPING' AS policy_type,
    source_system,
    COUNT(*) AS rows
FROM reference.federal_inflow_program_policy_mapping
GROUP BY source_system

UNION ALL

SELECT
    'AWARD_CLASSIFICATION',
    source_system,
    COUNT(*)
FROM reference.federal_inflow_award_classification
GROUP BY source_system

ORDER BY policy_type, source_system;

\echo ''
\echo '2. WASHINGTON ASSISTANCE - PROGRAM POLICY MATCHES'

WITH transactions AS (
    SELECT
        g.action_date_fiscal_year AS fiscal_year,
        g.assistance_transaction_id,
        g.cfda_number,
        g.federal_action_obligation,
        g.geographic_attribution_class
    FROM analysis.v_assistance_geographic_attribution g
    WHERE g.action_date_fiscal_year BETWEEN 2018 AND 2024
      AND g.is_washington_attributed IS TRUE
),
matched AS (
    SELECT
        t.*,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS matching_policies,
        MIN(m.resolved_accounting_disposition)
            AS disposition
    FROM transactions t
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_program_code = t.cfda_number
     AND t.fiscal_year BETWEEN
         m.valid_from_fiscal_year
         AND m.valid_through_fiscal_year
    GROUP BY
        t.fiscal_year,
        t.assistance_transaction_id,
        t.cfda_number,
        t.federal_action_obligation,
        t.geographic_attribution_class
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
FROM matched
GROUP BY fiscal_year, provisional_disposition
ORDER BY fiscal_year, provisional_disposition;

\echo ''
\echo '3. HISTORICAL GEOGRAPHIC COVERAGE'

SELECT
    action_date_fiscal_year AS fiscal_year,
    geographic_attribution_class,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars
FROM analysis.v_assistance_geographic_attribution
WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
GROUP BY
    action_date_fiscal_year,
    geographic_attribution_class
ORDER BY
    action_date_fiscal_year,
    geographic_attribution_class;

\echo ''
\echo '4. AWARD CLASSIFICATION IDENTIFIER PROFILE'

SELECT
    source_system,
    accounting_disposition,
    COUNT(*) AS classification_rows,
    COUNT(*) FILTER (
        WHERE source_award_identifier IS NULL
    ) AS missing_award_identifiers
FROM reference.federal_inflow_award_classification
WHERE valid_from_fiscal_year <= 2024
  AND valid_through_fiscal_year >= 2018
GROUP BY source_system, accounting_disposition
ORDER BY source_system, accounting_disposition;

ROLLBACK;