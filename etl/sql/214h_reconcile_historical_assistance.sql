
\set ON_ERROR_STOP on
\pset pager off

\echo '=========================================================='
\echo 'ETL-214H - FULL HISTORICAL ASSISTANCE RECONCILIATION'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. ANNUAL ACCOUNTING DISPOSITION MATRIX'

WITH source_rows AS MATERIALIZED (
    SELECT
        l.assistance_transaction_id,
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        l.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(l.award_id_fain), ''),
            NULLIF(TRIM(l.award_id_uri), '')
        ) AS award_identifier,
        l.reference_county_id,
        l.performance_state_fips,
        l.is_covid
    FROM analysis.v_certified_assistance_ledger l
    WHERE
        (l.load_batch_id = 20
         AND l.action_date_fiscal_year = 2018)
        OR
        (l.load_batch_id = 21
         AND l.action_date_fiscal_year = 2019)
),
resolved AS MATERIALIZED (
    SELECT
        s.*,
        CASE
            WHEN a.policy_id IS NOT NULL
                THEN 'AWARD_CLASSIFICATION'
            WHEN p.policy_id IS NOT NULL
                THEN 'PROGRAM_POLICY_MAPPING'
            ELSE 'UNCLASSIFIED'
        END AS resolution_source,
        CASE
            WHEN a.policy_id IS NOT NULL
                THEN a.disposition
            WHEN p.policy_id IS NOT NULL
                THEN p.disposition
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS resolved_disposition,
        CASE
            WHEN a.policy_id IS NOT NULL
                THEN a.methodology_version
            WHEN p.policy_id IS NOT NULL
                THEN p.methodology_version
        END AS resolution_methodology,
        COALESCE(a.match_count, 0) AS award_matches,
        COALESCE(p.match_count, 0) AS program_matches,
        CASE
            WHEN a.policy_id IS NOT NULL
             AND p.policy_id IS NOT NULL
             AND a.disposition IS DISTINCT FROM p.disposition
                THEN TRUE
            ELSE FALSE
        END AS conflicting_policy_dispositions
    FROM source_rows s

    LEFT JOIN LATERAL (
        SELECT
            a.federal_inflow_award_classification_id
                AS policy_id,
            a.accounting_disposition AS disposition,
            a.methodology_version,
            COUNT(*) OVER () AS match_count
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
                AS policy_id,
            p.resolved_accounting_disposition
                AS disposition,
            p.methodology_version,
            COUNT(*) OVER () AS match_count
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
),
annual_matrix AS (
    SELECT
        fiscal_year,
        resolved_disposition,
        resolution_source,
        COUNT(*) AS transactions,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_transactions,
        COUNT(DISTINCT program_code)
            AS distinct_programs,
        COALESCE(SUM(obligation), 0)
            AS net_obligations,
        COALESCE(
            SUM(obligation) FILTER (WHERE obligation > 0),
            0
        ) AS positive_obligations,
        COALESCE(
            SUM(obligation) FILTER (WHERE obligation < 0),
            0
        ) AS negative_obligations,
        COUNT(*) FILTER (
            WHERE obligation IS NULL
        ) AS null_obligation_rows,
        COUNT(*) FILTER (
            WHERE award_matches > 1
        ) AS multiple_award_policy_rows,
        COUNT(*) FILTER (
            WHERE program_matches > 1
        ) AS multiple_program_policy_rows,
        COUNT(*) FILTER (
            WHERE conflicting_policy_dispositions
        ) AS conflicting_policy_rows
    FROM resolved
    GROUP BY
        fiscal_year,
        resolved_disposition,
        resolution_source
)
SELECT
    fiscal_year,
    resolved_disposition,
    resolution_source,
    transactions,
    distinct_transactions,
    distinct_programs,
    ROUND(net_obligations, 2)
        AS net_obligations_dollars,
    ROUND(positive_obligations, 2)
        AS positive_obligations_dollars,
    ROUND(negative_obligations, 2)
        AS negative_obligations_dollars,
    null_obligation_rows,
    multiple_award_policy_rows,
    multiple_program_policy_rows,
    conflicting_policy_rows
FROM annual_matrix
ORDER BY
    fiscal_year,
    resolved_disposition,
    resolution_source;

\echo ''
\echo '2. SOURCE CONTROL - INDEPENDENT ANNUAL TOTALS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT TRIM(cfda_number))
        AS distinct_programs,
    ROUND(
        COALESCE(SUM(federal_action_obligation), 0),
        2
    ) AS net_obligations_dollars,
    COUNT(*) FILTER (
        WHERE federal_action_obligation IS NULL
    ) AS null_obligation_rows,
    COUNT(*) FILTER (
        WHERE reference_county_id IS NOT NULL
    ) AS county_linked_rows
FROM analysis.v_certified_assistance_ledger
WHERE
    (load_batch_id = 20
     AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21
     AND action_date_fiscal_year = 2019)
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

\echo ''
\echo '3. HISTORICAL PROGRAM MAPPING INVENTORY'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND valid_from_fiscal_year <= 2019
  AND (
      valid_through_fiscal_year IS NULL
      OR valid_through_fiscal_year >= 2018
  )
ORDER BY
    source_program_code,
    valid_from_fiscal_year,
    methodology_version;

ROLLBACK;

\echo 'ETL-214H COMPLETE - NO DATABASE WRITES'
