\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221Q - HISTORICAL ASSISTANCE POLICY RESOLUTION'

\echo ''
\echo '1. AWARD CLASSIFICATION VS PROGRAM POLICY'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.assistance_transaction_id,
        t.cfda_number,
        t.assistance_award_unique_key,
        t.award_id_fain,
        t.award_id_uri,
        t.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.load_batch_id IN (20, 21)
),
resolved AS (
    SELECT
        h.*,
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition,
        a.source_program_code
            AS award_program_code,
        a.source_award_identifier
            AS matched_award_identifier,
        a.methodology_version
            AS award_methodology_version
    FROM historical h
    LEFT JOIN LATERAL (
        SELECT
            m.resolved_accounting_disposition
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = h.cfda_number
          AND h.fiscal_year >= m.valid_from_fiscal_year
          AND (
              m.valid_through_fiscal_year IS NULL
              OR h.fiscal_year <= m.valid_through_fiscal_year
          )
        ORDER BY m.federal_inflow_program_policy_mapping_id
        LIMIT 1
    ) p ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            a.accounting_disposition,
            a.source_program_code,
            a.source_award_identifier,
            a.methodology_version
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
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
        ORDER BY a.federal_inflow_award_classification_id
        LIMIT 1
    ) a ON TRUE
)
SELECT
    fiscal_year,
    COALESCE(program_disposition, 'NO_PROGRAM_MAPPING')
        AS program_disposition,
    COALESCE(award_disposition, 'NO_AWARD_OVERRIDE')
        AS award_disposition,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars,
    COUNT(*) FILTER (
        WHERE award_disposition IS NOT NULL
          AND award_program_code IS DISTINCT FROM cfda_number
    ) AS award_program_code_mismatch_rows
FROM resolved
GROUP BY 1, 2, 3
ORDER BY fiscal_year, program_disposition, award_disposition;

\echo ''
\echo '2. LARGEST HISTORICAL UNMAPPED PROGRAMS'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.cfda_number,
        t.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.load_batch_id IN (20, 21)
),
unmapped AS (
    SELECT h.*
    FROM historical h
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping m
        WHERE m.source_system = 'USASPENDING_ASSISTANCE'
          AND m.source_program_code = h.cfda_number
          AND h.fiscal_year >= m.valid_from_fiscal_year
          AND (
              m.valid_through_fiscal_year IS NULL
              OR h.fiscal_year <= m.valid_through_fiscal_year
          )
    )
),
ranked AS (
    SELECT
        fiscal_year,
        cfda_number,
        COUNT(*) AS transaction_rows,
        SUM(federal_action_obligation) AS obligations_dollars,
        ROW_NUMBER() OVER (
            PARTITION BY fiscal_year
            ORDER BY ABS(SUM(federal_action_obligation)) DESC
        ) AS program_rank
    FROM unmapped
    GROUP BY fiscal_year, cfda_number
)
SELECT
    fiscal_year,
    cfda_number,
    transaction_rows,
    obligations_dollars
FROM ranked
WHERE program_rank <= 20
ORDER BY fiscal_year, program_rank;

ROLLBACK;