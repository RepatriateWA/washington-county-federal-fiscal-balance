
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223N5 - AWARD-SPECIFIC PRECEDENCE'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. AWARD MATCH AND ACCOUNTING DISPOSITION BY PROGRAM/YEAR'

WITH target AS (
    SELECT
        v.assistance_transaction_id,
        BTRIM(v.cfda_number) AS program_code,
        v.action_date_fiscal_year AS fiscal_year,
        v.federal_action_obligation AS amount,
        NULLIF(BTRIM(v.award_id_fain), '') AS fain,
        NULLIF(BTRIM(v.award_id_uri), '') AS uri
    FROM analysis.v_certified_assistance_ledger v
    WHERE (
        (v.load_batch_id = 20
         AND v.action_date_fiscal_year = 2018)
        OR
        (v.load_batch_id = 21
         AND v.action_date_fiscal_year = 2019)
    )
      AND BTRIM(v.cfda_number) IN (
          '10.557','10.561','10.924','93.527','93.563'
      )
),
classified AS (
    SELECT
        t.*,
        COALESCE(a.match_count, 0) AS match_count,
        a.disposition,
        CASE
            WHEN COALESCE(a.match_count, 0) = 0
                THEN 'PROGRAM_MAPPING'
            WHEN a.match_count = 1
                THEN 'AWARD_OVERRIDE'
            ELSE 'AMBIGUOUS_AWARD_MATCH'
        END AS precedence_status
    FROM target t
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS match_count,
            MIN(c.accounting_disposition) AS disposition
        FROM reference.federal_inflow_award_classification c
        WHERE c.source_system = 'USASPENDING_ASSISTANCE'
          AND BTRIM(c.source_program_code) = t.program_code
          AND (
              c.source_award_identifier = t.fain
              OR c.source_award_identifier = t.uri
          )
          AND (
              c.valid_from_fiscal_year IS NULL
              OR t.fiscal_year >= c.valid_from_fiscal_year
          )
          AND (
              c.valid_through_fiscal_year IS NULL
              OR t.fiscal_year <= c.valid_through_fiscal_year
          )
    ) a ON TRUE
)
SELECT
    program_code,
    fiscal_year,
    precedence_status,
    CASE
        WHEN precedence_status = 'PROGRAM_MAPPING'
            THEN 'INCLUDE_ADDITIVE'
        WHEN precedence_status = 'AWARD_OVERRIDE'
            THEN disposition
        ELSE 'REVIEW_AMBIGUITY'
    END AS effective_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(amount), 2) AS net_obligations
FROM classified
GROUP BY
    program_code,
    fiscal_year,
    precedence_status,
    effective_disposition
ORDER BY
    program_code,
    fiscal_year,
    precedence_status,
    effective_disposition;

\echo ''
\echo '2. TARGET AWARD CLASSIFICATION RECORDS'

SELECT
    c.source_program_code,
    c.accounting_disposition,
    c.valid_from_fiscal_year,
    c.valid_through_fiscal_year,
    COUNT(*) AS classification_records
FROM reference.federal_inflow_award_classification c
WHERE c.source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(c.source_program_code) IN (
      '10.557','10.561','10.924','93.527','93.563'
  )
GROUP BY
    c.source_program_code,
    c.accounting_disposition,
    c.valid_from_fiscal_year,
    c.valid_through_fiscal_year
ORDER BY
    c.source_program_code,
    c.accounting_disposition;

COMMIT;

\echo 'ETL-223N5 COMPLETE - NO DATABASE WRITES'
