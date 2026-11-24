\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221T - HISTORICAL POLICY EXTENSION EVIDENCE'

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
historical_totals AS (
    SELECT
        fiscal_year,
        cfda_number,
        COUNT(*) AS transaction_rows,
        SUM(federal_action_obligation) AS obligations_dollars
    FROM unresolved
    GROUP BY fiscal_year, cfda_number
)
SELECT
    h.fiscal_year,
    h.cfda_number,
    h.transaction_rows,
    h.obligations_dollars,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version,
    p.mapping_basis
FROM historical_totals h
JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = h.cfda_number
 AND p.valid_from_fiscal_year <= 2024
 AND (
     p.valid_through_fiscal_year IS NULL
     OR p.valid_through_fiscal_year >= 2020
 )
ORDER BY
    p.resolved_accounting_disposition,
    ABS(h.obligations_dollars) DESC,
    h.fiscal_year,
    h.cfda_number;

ROLLBACK;