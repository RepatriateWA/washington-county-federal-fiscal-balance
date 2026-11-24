
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209J - HISTORICAL ASSISTANCE ACCOUNTING VALIDATION'
\echo 'FY2018-FY2019 / POST OASDI POLICY EXTENSION'
\echo 'READ ONLY - NO PERMANENT DATABASE WRITES'
\echo '============================================================'

BEGIN;

CREATE TEMP TABLE m209j_source ON COMMIT DROP AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    federal_action_obligation AS obligation,
    COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), '')
    ) AS award_identifier
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
);

CREATE TEMP TABLE m209j_bridge ON COMMIT DROP AS
WITH award_candidates AS (
    SELECT
        s.assistance_transaction_id,
        a.federal_inflow_award_classification_id AS policy_id,
        a.accounting_disposition AS disposition,
        a.methodology_version,
        ROW_NUMBER() OVER (
            PARTITION BY s.assistance_transaction_id
            ORDER BY
                a.updated_at DESC NULLS LAST,
                a.federal_inflow_award_classification_id DESC
        ) AS policy_rank
    FROM m209j_source s
    JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
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
),
program_candidates AS (
    SELECT
        s.assistance_transaction_id,
        p.federal_inflow_program_policy_mapping_id AS policy_id,
        p.resolved_accounting_disposition AS disposition,
        p.methodology_version,
        ROW_NUMBER() OVER (
            PARTITION BY s.assistance_transaction_id
            ORDER BY
                p.updated_at DESC NULLS LAST,
                p.federal_inflow_program_policy_mapping_id DESC
        ) AS policy_rank
    FROM m209j_source s
    JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = s.program_code
     AND (
          p.valid_from_fiscal_year IS NULL
          OR s.fiscal_year >= p.valid_from_fiscal_year
     )
     AND (
          p.valid_through_fiscal_year IS NULL
          OR s.fiscal_year <= p.valid_through_fiscal_year
     )
)
SELECT
    s.*,
    CASE
        WHEN a.policy_id IS NOT NULL
            THEN 'AWARD_CLASSIFICATION'
        WHEN p.policy_id IS NOT NULL
            THEN 'PROGRAM_POLICY_MAPPING'
        ELSE 'UNCLASSIFIED'
    END AS resolution_source,
    COALESCE(
        a.disposition,
        p.disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS resolved_disposition,
    CASE
        WHEN a.policy_id IS NOT NULL THEN a.methodology_version
        WHEN p.policy_id IS NOT NULL THEN p.methodology_version
    END AS resolution_methodology,
    COALESCE(ac.match_count, 0) AS award_matches,
    COALESCE(pc.match_count, 0) AS program_matches
FROM m209j_source s
LEFT JOIN award_candidates a
  ON a.assistance_transaction_id = s.assistance_transaction_id
 AND a.policy_rank = 1
LEFT JOIN program_candidates p
  ON p.assistance_transaction_id = s.assistance_transaction_id
 AND p.policy_rank = 1
LEFT JOIN (
    SELECT assistance_transaction_id, COUNT(*) AS match_count  
    FROM award_candidates
    GROUP BY assistance_transaction_id
) ac
    ON ac.assistance_transaction_id = s.assistance_transaction_id
LEFT JOIN (
    SELECT assistance_transaction_id, COUNT(*) AS match_count
    FROM program_candidates
    GROUP BY assistance_transaction_id
) pc
    ON pc.assistance_transaction_id = s.assistance_transaction_id;

\echo ''
\echo '1. SOURCE AND BRIDGE RECONCILIATION'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM m209j_bridge
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. ACCOUNTING DISPOSITION SUMMARY'

SELECT
    fiscal_year,
    resolved_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM m209j_bridge
GROUP BY fiscal_year, resolved_disposition
ORDER BY fiscal_year, resolved_disposition;

\echo ''
\echo '3. CLASSIFIED PROGRAMS AND METHODOLOGIES'

SELECT
    fiscal_year,
    program_code,
    resolution_source,
    resolved_disposition,
    resolution_methodology,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM m209j_bridge
WHERE resolved_disposition <> 'UNCLASSIFIED_REVIEW'
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 3, 4, 5;

\echo ''
\echo '4. COLLISION DIAGNOSTICS'

SELECT
    COUNT(*) FILTER (WHERE award_matches > 1)
        AS multiple_award_matches,
    COUNT(*) FILTER (WHERE program_matches > 1)
        AS multiple_program_matches,
    COUNT(*) FILTER (
        WHERE award_matches > 0 AND program_matches > 0
    ) AS both_layers_present,
    COUNT(*) FILTER (
        WHERE resolution_source = 'UNCLASSIFIED'
    ) AS unresolved_transactions
FROM m209j_bridge;

\echo ''
\echo '5. INDEPENDENT VALIDATION ASSERTIONS'

DO $$
DECLARE
    v_rows bigint;
    v_unique bigint;
    v_amount numeric;
    v_bad bigint;
    v_oasdi_rows bigint;
    v_oasdi_amount numeric;
    v_hcv_amount numeric;
    v_rrb_additive numeric;
    v_rrb_withheld numeric;
    v_unclassified_rows bigint;
    v_unclassified_amount numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0)
    INTO v_rows, v_unique, v_amount
    FROM m209j_bridge;

    IF v_rows <> 207343
       OR v_unique <> v_rows
       OR ROUND(v_amount, 2) <> 97097242523.58
    THEN
        RAISE EXCEPTION
            'ETL-209J FAIL: source control rows %, unique %, amount %',
            v_rows, v_unique, v_amount;
    END IF;

    IF (
        SELECT COUNT(*)
        FROM m209j_bridge
        WHERE fiscal_year = 2018
    ) <> 100426
    OR (
        SELECT COUNT(*)
        FROM m209j_bridge
        WHERE fiscal_year = 2019
    ) <> 106917
    THEN
        RAISE EXCEPTION
            'ETL-209J FAIL: fiscal-year row controls changed';
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM m209j_bridge
    WHERE award_matches > 1
       OR program_matches > 1
       OR (
           program_code IN ('96.001','96.002','96.004')
           AND (
               resolution_source <> 'PROGRAM_POLICY_MAPPING'
               OR resolved_disposition <> 'EXCLUDE_DUPLICATE'
               OR resolution_methodology <> 'ANALYSIS-209I-v1'
           )
       )
       OR (
           program_code = '14.871'
           AND (
               resolution_source <> 'PROGRAM_POLICY_MAPPING'
               OR resolved_disposition <> 'INCLUDE_ADDITIVE'
               OR resolution_methodology <> 'ANALYSIS-208-v1'
           )
       )
       OR (
           program_code = '57.001'
           AND (
               resolution_source <> 'AWARD_CLASSIFICATION'
               OR resolution_methodology <> 'ANALYSIS-205-v1'
               OR resolved_disposition NOT IN (
                   'INCLUDE_ADDITIVE',
                   'WITHHOLD_UNRESOLVED'
               )
           )
       );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209J FAIL: % classification/collision exceptions',
            v_bad;
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(obligation), 0)
    INTO v_oasdi_rows, v_oasdi_amount
    FROM m209j_bridge
    WHERE program_code IN ('96.001','96.002','96.004')
      AND resolved_disposition = 'EXCLUDE_DUPLICATE';

    SELECT COALESCE(SUM(obligation), 0)
    INTO v_hcv_amount
    FROM m209j_bridge
    WHERE program_code = '14.871'
      AND resolved_disposition = 'INCLUDE_ADDITIVE';

    SELECT
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_disposition = 'INCLUDE_ADDITIVE'
        ), 0),
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_disposition = 'WITHHOLD_UNRESOLVED'
        ), 0)
    INTO v_rrb_additive, v_rrb_withheld
    FROM m209j_bridge
    WHERE program_code = '57.001';

    SELECT
        COUNT(*),
        COALESCE(SUM(obligation), 0)
    INTO v_unclassified_rows, v_unclassified_amount
    FROM m209j_bridge
    WHERE resolved_disposition = 'UNCLASSIFIED_REVIEW';

    IF v_oasdi_rows <> 4938
       OR ROUND(v_oasdi_amount, 2) <> 45264113835.00
       OR ROUND(v_hcv_amount, 2) <> 1237486410.00
       OR ROUND(v_rrb_additive, 2) <> 515006959.71
       OR ROUND(v_rrb_withheld, 2) <> 4173083.00
       OR v_unclassified_rows <> 197510
       OR ROUND(v_unclassified_amount, 2) <> 50076462235.87
    THEN
        RAISE EXCEPTION
            'ETL-209J FAIL: OASDI %/%, HCV %, RRB additive %, RRB withheld %, unresolved %/%',
            v_oasdi_rows, v_oasdi_amount,
            v_hcv_amount, v_rrb_additive, v_rrb_withheld,
            v_unclassified_rows, v_unclassified_amount;
    END IF;

    -- Original FY2020-2024 OASDI policy must remain intact.
    IF (
        SELECT COUNT(*)
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version = 'ANALYSIS-116-v1'
          AND inflow_family = 'SOCIAL_SECURITY'
          AND inflow_subfamily = 'OASDI'
          AND preferred_source = 'SSA'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
    ) <> 1
    OR (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-174B-5L-v1'
          AND source_program_code IN (
              '96.001','96.002','96.004'
          )
          AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
    ) <> 3 THEN
        RAISE EXCEPTION
            'ETL-209J FAIL: original FY2020-FY2024 OASDI policies changed';
    END IF;

    -- SSI must not be classified by the OASDI extension.
    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-209I-v1'
          AND source_program_code = '96.006'
    ) THEN
        RAISE EXCEPTION
            'ETL-209J FAIL: SSI incorrectly included in OASDI policy';
    END IF;

    RAISE NOTICE
        'ETL-209J PASS: full historical bridge reconciles; OASDI nonadditive; HCV/RRB preserved; original policies intact';
END
$$;

ROLLBACK;

\echo 'ETL-209J COMPLETE - NO PERMANENT DATABASE WRITES'
