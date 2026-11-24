
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209A - HISTORICAL HCV ACCOUNTING RESOLUTION'
\echo 'FY2018-FY2019 | READ ONLY'
\echo '============================================================'

BEGIN READ ONLY;

WITH source AS (
    SELECT
        assistance_transaction_id,
        load_batch_id,
        source_row_number,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        award_id_fain,
        federal_action_obligation AS amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (load_batch_id = 20 AND action_date_fiscal_year = 2018
           OR load_batch_id = 21 AND action_date_fiscal_year = 2019)
      AND TRIM(cfda_number) = '14.871'
),
award_matches AS (
    SELECT
        s.assistance_transaction_id,
        c.federal_inflow_award_classification_id AS policy_id,
        c.accounting_disposition AS disposition,
        c.methodology_version,
        ROW_NUMBER() OVER (
            PARTITION BY s.assistance_transaction_id
            ORDER BY c.updated_at DESC NULLS LAST,
                     c.federal_inflow_award_classification_id DESC
        ) AS match_rank,
        COUNT(*) OVER (
            PARTITION BY s.assistance_transaction_id
        ) AS match_count
    FROM source s
    JOIN reference.federal_inflow_award_classification c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = s.program_code
     AND c.source_award_identifier = s.award_id_fain
     AND (c.valid_from_fiscal_year IS NULL
          OR s.fiscal_year >= c.valid_from_fiscal_year)
     AND (c.valid_through_fiscal_year IS NULL
          OR s.fiscal_year <= c.valid_through_fiscal_year)
),
program_matches AS (
    SELECT
        s.assistance_transaction_id,
        m.federal_inflow_program_policy_mapping_id AS policy_id,
        m.resolved_accounting_disposition AS disposition,
        m.methodology_version,
        ROW_NUMBER() OVER (
            PARTITION BY s.assistance_transaction_id
            ORDER BY m.updated_at DESC NULLS LAST,
                     m.federal_inflow_program_policy_mapping_id DESC
        ) AS match_rank,
        COUNT(*) OVER (
            PARTITION BY s.assistance_transaction_id
        ) AS match_count
    FROM source s
    JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = s.program_code
     AND (m.valid_from_fiscal_year IS NULL
          OR s.fiscal_year >= m.valid_from_fiscal_year)
     AND (m.valid_through_fiscal_year IS NULL
          OR s.fiscal_year <= m.valid_through_fiscal_year)
),
resolved AS (
    SELECT
        s.*,
        COALESCE(a.match_count, 0) AS award_match_count,
        COALESCE(p.match_count, 0) AS program_match_count,
        a.policy_id AS award_policy_id,
        p.policy_id AS program_policy_id,
        CASE
            WHEN a.policy_id IS NOT NULL THEN 'AWARD_CLASSIFICATION'
            WHEN p.policy_id IS NOT NULL THEN 'PROGRAM_POLICY_MAPPING'
            ELSE 'UNCLASSIFIED'
        END AS resolution_source,
        CASE
            WHEN a.policy_id IS NOT NULL THEN a.disposition
            WHEN p.policy_id IS NOT NULL THEN p.disposition
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS final_disposition,
        CASE
            WHEN a.policy_id IS NOT NULL THEN a.methodology_version
            WHEN p.policy_id IS NOT NULL THEN p.methodology_version
        END AS resolution_methodology
    FROM source s
    LEFT JOIN award_matches a
      ON a.assistance_transaction_id = s.assistance_transaction_id
     AND a.match_rank = 1
    LEFT JOIN program_matches p
      ON p.assistance_transaction_id = s.assistance_transaction_id
     AND p.match_rank = 1
)
SELECT
    fiscal_year,
    resolution_source,
    final_disposition,
    resolution_methodology,
    COUNT(*) AS transactions,
    ROUND(SUM(amount), 2) AS net_obligations,
    COUNT(*) FILTER (WHERE award_match_count > 1)
        AS multiple_award_matches,
    COUNT(*) FILTER (WHERE program_match_count > 1)
        AS multiple_program_matches,
    COUNT(*) FILTER (WHERE award_policy_id IS NOT NULL
                       AND program_policy_id IS NOT NULL)
        AS both_policy_layers_present
FROM resolved
GROUP BY
    fiscal_year,
    resolution_source,
    final_disposition,
    resolution_methodology
ORDER BY fiscal_year, resolution_source, final_disposition;

ROLLBACK;

\echo 'ETL-209A COMPLETE - NO DATABASE WRITES'
