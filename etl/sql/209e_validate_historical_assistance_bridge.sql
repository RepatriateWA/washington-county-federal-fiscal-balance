
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209E - HISTORICAL ASSISTANCE ACCOUNTING BRIDGE'
\echo 'FY2018-FY2019 / AL 14.871 AND 57.001'
\echo 'REUSE EXISTING POLICIES - NO PERMANENT DATABASE WRITES'
\echo '============================================================'

BEGIN;

CREATE TEMP TABLE m209e_source ON COMMIT DROP AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year AS fiscal_year,
    TRIM(cfda_number) AS program_code,
    federal_action_obligation AS obligation,
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND TRIM(cfda_number) IN ('14.871', '57.001');

CREATE TEMP TABLE m209e_bridge ON COMMIT DROP AS
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
    FROM m209e_source s
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
    FROM m209e_source s
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
        WHEN a.policy_id IS NOT NULL THEN 'AWARD_CLASSIFICATION'
        WHEN p.policy_id IS NOT NULL THEN 'PROGRAM_POLICY_MAPPING'
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
    a.policy_id AS award_policy_id,
    p.policy_id AS program_policy_id,
    COALESCE(ac.match_count, 0) AS award_matches,
    COALESCE(pc.match_count, 0) AS program_matches
FROM m209e_source s
LEFT JOIN award_candidates a
  ON a.assistance_transaction_id = s.assistance_transaction_id
 AND a.policy_rank = 1
LEFT JOIN program_candidates p
  ON p.assistance_transaction_id = s.assistance_transaction_id
 AND p.policy_rank = 1
LEFT JOIN (
    SELECT
        assistance_transaction_id,
        COUNT(*) AS match_count
    FROM award_candidates
    GROUP BY assistance_transaction_id
) ac
    ON ac.assistance_transaction_id = s.assistance_transaction_id
LEFT JOIN (
    SELECT
        assistance_transaction_id,
        COUNT(*) AS match_count
    FROM program_candidates
    GROUP BY assistance_transaction_id
) pc
    ON pc.assistance_transaction_id = s.assistance_transaction_id;

\echo ''
\echo '1. SOURCE CONTROL BY YEAR AND PROGRAM'

SELECT
    fiscal_year,
    program_code,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_identifier) AS awards,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM m209e_source
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '2. RESOLVED ACCOUNTING BY YEAR, PROGRAM AND DISPOSITION'

SELECT
    fiscal_year,
    program_code,
    resolution_source,
    resolved_disposition,
    resolution_methodology,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM m209e_bridge
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 3, 4, 5;

\echo ''
\echo '3. POLICY COLLISION DIAGNOSTICS'

SELECT
    fiscal_year,
    program_code,
    COUNT(*) FILTER (
        WHERE award_matches > 1
    ) AS multiple_award_matches,
    COUNT(*) FILTER (
        WHERE program_matches > 1
    ) AS multiple_program_matches,
    COUNT(*) FILTER (
        WHERE award_policy_id IS NOT NULL
          AND program_policy_id IS NOT NULL
    ) AS both_policy_layers_present,
    COUNT(*) FILTER (
        WHERE resolution_source = 'UNCLASSIFIED'
    ) AS unclassified_transactions
FROM m209e_bridge
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '4. VALIDATION ASSERTIONS'

DO $$
DECLARE
    v_source_rows bigint;
    v_bridge_rows bigint;
    v_distinct_rows bigint;
    v_source_amount numeric;
    v_bridge_amount numeric;
    v_bad bigint;
    v_hcv_additive numeric;
    v_rrb_additive numeric;
    v_rrb_withheld numeric;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(obligation), 0)
    INTO v_source_rows, v_source_amount
    FROM m209e_source;

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE award_matches > 1
               OR program_matches > 1
               OR resolution_source = 'UNCLASSIFIED'
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
               )
        )
    INTO v_bridge_rows, v_distinct_rows, v_bridge_amount, v_bad
    FROM m209e_bridge;

    SELECT
        COALESCE(SUM(obligation) FILTER (
            WHERE program_code = '14.871'
              AND resolved_disposition = 'INCLUDE_ADDITIVE'
        ), 0),
        COALESCE(SUM(obligation) FILTER (
            WHERE program_code = '57.001'
              AND resolved_disposition = 'INCLUDE_ADDITIVE'
        ), 0),
        COALESCE(SUM(obligation) FILTER (
            WHERE program_code = '57.001'
              AND resolved_disposition = 'WITHHOLD_UNRESOLVED'
        ), 0)
    INTO v_hcv_additive, v_rrb_additive, v_rrb_withheld
    FROM m209e_bridge;

    IF v_source_rows <> 4895
       OR v_bridge_rows <> v_source_rows
       OR v_distinct_rows <> v_source_rows
       OR ROUND(v_source_amount, 2) <> 1756666452.71
       OR ROUND(v_bridge_amount, 2) <> ROUND(v_source_amount, 2)
       OR ROUND(v_hcv_additive, 2) <> 1237486410.00
       OR ROUND(v_rrb_additive, 2) <> 515006959.71
       OR ROUND(v_rrb_withheld, 2) <> 4173083.00
       OR v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-209E FAIL: source rows %, bridge rows %, distinct %, source amount %, bridge amount %, HCV additive %, RRB additive %, RRB withheld %, bad %',
            v_source_rows, v_bridge_rows, v_distinct_rows,
            v_source_amount, v_bridge_amount,
            v_hcv_additive, v_rrb_additive, v_rrb_withheld,
            v_bad;
    END IF;

    RAISE NOTICE
        'ETL-209E PASS: historical assistance accounting bridge reconciled';
END
$$;

ROLLBACK;

\echo 'ETL-209E COMPLETE - NO DATABASE WRITES'
