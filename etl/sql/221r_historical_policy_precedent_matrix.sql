\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221R - HISTORICAL POLICY PRECEDENT MATRIX'

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
programs AS (
    SELECT
        fiscal_year,
        cfda_number,
        COUNT(*) AS transaction_rows,
        SUM(federal_action_obligation) AS obligations_dollars
    FROM unresolved
    GROUP BY fiscal_year, cfda_number
),
precedents AS (
    SELECT
        p.*,
        (
            SELECT STRING_AGG(
                DISTINCT m.resolved_accounting_disposition,
                ', '
            )
            FROM reference.federal_inflow_program_policy_mapping m
            WHERE m.source_system = 'USASPENDING_ASSISTANCE'
              AND m.source_program_code = p.cfda_number
              AND m.valid_from_fiscal_year <= 2024
              AND (
                  m.valid_through_fiscal_year IS NULL
                  OR m.valid_through_fiscal_year >= 2020
              )
        ) AS later_dispositions,
        (
            SELECT MIN(m.valid_from_fiscal_year)
            FROM reference.federal_inflow_program_policy_mapping m
            WHERE m.source_system = 'USASPENDING_ASSISTANCE'
              AND m.source_program_code = p.cfda_number
              AND m.valid_from_fiscal_year <= 2024
              AND (
                  m.valid_through_fiscal_year IS NULL
                  OR m.valid_through_fiscal_year >= 2020
              )
        ) AS earliest_later_policy_year
    FROM programs p
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY fiscal_year
            ORDER BY ABS(obligations_dollars) DESC,
                     cfda_number
        ) AS program_rank
    FROM precedents
)
SELECT
    fiscal_year,
    cfda_number,
    transaction_rows,
    obligations_dollars,
    COALESCE(
        later_dispositions,
        'NO_FY2020_2024_PRECEDENT'
    ) AS later_policy,
    earliest_later_policy_year
FROM ranked
WHERE program_rank <= 30
ORDER BY fiscal_year, program_rank;

\echo ''
\echo '2. COVERAGE SUMMARY'

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
)
SELECT
    fiscal_year,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM reference.federal_inflow_program_policy_mapping m
            WHERE m.source_system = 'USASPENDING_ASSISTANCE'
              AND m.source_program_code = u.cfda_number
              AND m.valid_from_fiscal_year <= 2024
              AND (
                  m.valid_through_fiscal_year IS NULL
                  OR m.valid_through_fiscal_year >= 2020
              )
        )
        THEN 'HAS_LATER_POLICY_PRECEDENT'
        ELSE 'NO_LATER_POLICY_PRECEDENT'
    END AS precedent_status,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars
FROM unresolved u
GROUP BY 1, 2
ORDER BY 1, 2;

ROLLBACK;