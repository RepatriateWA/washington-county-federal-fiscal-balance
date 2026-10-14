
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209D - HISTORICAL RRB ACCOUNTING VERIFICATION'
\echo 'READ ONLY - REUSE ETL-205'
\echo '============================================================'

BEGIN;

CREATE TEMP TABLE m209d_rrb ON COMMIT DROP AS
SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year AS fiscal_year,
    l.federal_action_obligation AS obligation,
    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ) AS award_identifier
FROM analysis.v_certified_assistance_ledger l
WHERE (
       (l.load_batch_id = 20
        AND l.action_date_fiscal_year = 2018)
    OR (l.load_batch_id = 21
        AND l.action_date_fiscal_year = 2019)
)
AND TRIM(l.cfda_number) = '57.001';

\echo ''
\echo '1. HISTORICAL SOURCE CONTROL'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_identifier) AS awards,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM m209d_rrb
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. EFFECTIVE AWARD CLASSIFICATION'

CREATE TEMP TABLE m209d_resolved ON COMMIT DROP AS
SELECT
    r.*,
    a.federal_inflow_award_classification_id,
    a.accounting_disposition,
    a.methodology_version
FROM m209d_rrb r
LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = '57.001'
 AND a.source_award_identifier = r.award_identifier
 AND (
      a.valid_from_fiscal_year IS NULL
      OR r.fiscal_year >= a.valid_from_fiscal_year
 )
 AND (
      a.valid_through_fiscal_year IS NULL
      OR r.fiscal_year <= a.valid_through_fiscal_year
 );

SELECT
    fiscal_year,
    COALESCE(accounting_disposition, 'UNCLASSIFIED')
        AS accounting_disposition,
    COALESCE(methodology_version, 'NONE')
        AS methodology_version,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM m209d_resolved
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

\echo ''
\echo '3. VALIDATION ASSERTIONS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_resolved bigint;
    v_additive numeric;
    v_withheld numeric;
    v_total numeric;
    v_bad bigint;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COUNT(*) FILTER (
            WHERE methodology_version = 'ANALYSIS-205-v1'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ), 0),
        COALESCE(SUM(obligation) FILTER (
            WHERE accounting_disposition = 'WITHHOLD_UNRESOLVED'
        ), 0),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE federal_inflow_award_classification_id IS NULL
               OR methodology_version IS DISTINCT FROM 'ANALYSIS-205-v1'
               OR accounting_disposition NOT IN (
                   'INCLUDE_ADDITIVE',
                   'WITHHOLD_UNRESOLVED'
               )
        )
    INTO
        v_rows,
        v_distinct,
        v_resolved,
        v_additive,
        v_withheld,
        v_total,
        v_bad
    FROM m209d_resolved;

    IF v_rows <> 3307
       OR v_distinct <> 3307
       OR v_resolved <> 3307
       OR v_bad <> 0
       OR ROUND(v_total, 2) <> 519180042.71
       OR ROUND(v_additive, 2) <> 515006959.71
       OR ROUND(v_withheld, 2) <> 4173083.00
    THEN
        RAISE EXCEPTION
            'ETL-209D FAILED: rows %, distinct %, resolved %, bad %, total %, additive %, withheld %',
            v_rows, v_distinct, v_resolved, v_bad,
            v_total, v_additive, v_withheld;
    END IF;

    RAISE NOTICE
        'ETL-209D PASS: historical RRB classifications and amounts reproduced';
END
$$;

ROLLBACK;

\echo 'ETL-209D COMPLETE - NO DATABASE WRITES'
