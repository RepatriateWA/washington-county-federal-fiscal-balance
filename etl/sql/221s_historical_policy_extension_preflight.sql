\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221S - HISTORICAL POLICY EXTENSION PREFLIGHT'

WITH historical AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.cfda_number,
        t.assistance_award_unique_key,
        t.award_id_fain,
        t.award_id_uri,
        t.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.load_batch_id IN (20, 21)
),
unresolved AS (
    SELECT h.*
    FROM historical h
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = h.cfda_number
          AND h.fiscal_year >= p.valid_from_fiscal_year
          AND (
              p.valid_through_fiscal_year IS NULL
              OR h.fiscal_year <= p.valid_through_fiscal_year
          )
    )
    AND NOT EXISTS (
        SELECT 1
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
    )
),
later_policies AS (
    SELECT
        source_program_code,
        COUNT(DISTINCT resolved_accounting_disposition)
            AS disposition_count,
        STRING_AGG(
            DISTINCT resolved_accounting_disposition,
            ', '
        ) AS later_dispositions,
        MIN(valid_from_fiscal_year)
            AS earliest_policy_year,
        STRING_AGG(
            DISTINCT methodology_version,
            ', '
        ) AS methodology_versions
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND valid_from_fiscal_year <= 2024
      AND (
          valid_through_fiscal_year IS NULL
          OR valid_through_fiscal_year >= 2020
      )
    GROUP BY source_program_code
),
program_summary AS (
    SELECT
        u.fiscal_year,
        u.cfda_number,
        COUNT(*) AS transaction_rows,
        SUM(u.federal_action_obligation) AS obligations_dollars,
        COALESCE(p.disposition_count, 0)
            AS disposition_count,
        COALESCE(
            p.later_dispositions,
            'NO_LATER_PRECEDENT'
        ) AS later_dispositions,
        p.earliest_policy_year,
        p.methodology_versions
    FROM unresolved u
    LEFT JOIN later_policies p
      ON p.source_program_code = u.cfda_number
    GROUP BY
        u.fiscal_year,
        u.cfda_number,
        p.disposition_count,
        p.later_dispositions,
        p.earliest_policy_year,
        p.methodology_versions
)
SELECT
    fiscal_year,
    CASE
        WHEN disposition_count = 0
            THEN 'NO_LATER_PRECEDENT'
        WHEN disposition_count > 1
            THEN 'CONFLICTING_LATER_PRECEDENTS'
        ELSE later_dispositions
    END AS precedent_class,
    COUNT(*) AS program_count,
    SUM(transaction_rows) AS transaction_rows,
    SUM(obligations_dollars) AS obligations_dollars
FROM program_summary
GROUP BY 1, 2
ORDER BY fiscal_year, precedent_class;

\echo ''
\echo '2. LATER POLICY CONFLICTS'

WITH policies AS (
    SELECT
        source_program_code,
        COUNT(DISTINCT resolved_accounting_disposition)
            AS disposition_count,
        STRING_AGG(
            DISTINCT resolved_accounting_disposition,
            ', '
        ) AS dispositions
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND valid_from_fiscal_year <= 2024
      AND (
          valid_through_fiscal_year IS NULL
          OR valid_through_fiscal_year >= 2020
      )
    GROUP BY source_program_code
)
SELECT
    source_program_code,
    disposition_count,
    dispositions
FROM policies
WHERE disposition_count > 1
ORDER BY source_program_code;

ROLLBACK;