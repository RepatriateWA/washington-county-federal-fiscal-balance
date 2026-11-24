
\set ON_ERROR_STOP on
\pset pager off

\echo '=========================================================='
\echo 'ETL-214G - HISTORICAL ASSISTANCE DOLLAR RECONCILIATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. HISTORICAL HCV AND RRB ACCOUNTING DISPOSITIONS'

WITH source_rows AS (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier,
        performance_state_fips,
        performance_county_fips,
        reference_county_id
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
    )
      AND TRIM(cfda_number) IN ('14.871', '57.001')
),
resolved AS (
    SELECT
        s.*,
        CASE
            WHEN a.classification_id IS NOT NULL
                THEN 'AWARD_CLASSIFICATION'
            WHEN p.mapping_id IS NOT NULL
                THEN 'PROGRAM_POLICY_MAPPING'
            ELSE 'UNCLASSIFIED'
        END AS resolution_source,
        COALESCE(
            a.accounting_disposition,
            p.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS resolved_disposition,
        COALESCE(
            a.methodology_version,
            p.methodology_version
        ) AS methodology_version
    FROM source_rows s
    LEFT JOIN LATERAL (
        SELECT
            a.federal_inflow_award_classification_id
                AS classification_id,
            a.accounting_disposition,
            a.methodology_version
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (
              a.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= a.valid_from_fiscal_year
          )
          AND (
              a.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= a.valid_through_fiscal_year
          )
        ORDER BY
            a.updated_at DESC NULLS LAST,
            a.federal_inflow_award_classification_id DESC
        LIMIT 1
    ) a ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            p.federal_inflow_program_policy_mapping_id
                AS mapping_id,
            p.resolved_accounting_disposition
                AS accounting_disposition,
            p.methodology_version
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (
              p.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= p.valid_from_fiscal_year
          )
          AND (
              p.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= p.valid_through_fiscal_year
          )
        ORDER BY
            p.updated_at DESC NULLS LAST,
            p.federal_inflow_program_policy_mapping_id DESC
        LIMIT 1
    ) p ON TRUE
)
SELECT
    fiscal_year,
    program_code,
    resolution_source,
    resolved_disposition,
    methodology_version,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations_dollars,
    COUNT(*) FILTER (
        WHERE reference_county_id IS NOT NULL
    ) AS linked_county_rows,
    COUNT(*) FILTER (
        WHERE performance_county_fips IS NOT NULL
    ) AS source_county_fips_rows,
    COUNT(*) FILTER (
        WHERE performance_state_fips = '53'
    ) AS wa_performance_rows
FROM resolved
GROUP BY
    fiscal_year,
    program_code,
    resolution_source,
    resolved_disposition,
    methodology_version
ORDER BY
    fiscal_year,
    program_code,
    resolved_disposition;

ROLLBACK;

\echo 'ETL-214G COMPLETE - NO DATABASE WRITES'
