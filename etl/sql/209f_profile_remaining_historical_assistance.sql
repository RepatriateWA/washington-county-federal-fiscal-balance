
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209F - REMAINING HISTORICAL ASSISTANCE INVENTORY'
\echo 'FY2018-FY2019 / EXISTING ACCOUNTING POLICIES'
\echo 'NO PERMANENT DATABASE WRITES'
\echo '============================================================'

BEGIN;
SET LOCAL statement_timeout = '900s';

-- Reuse historical batch selection from ETL-205 / ETL-209E.
CREATE TEMP TABLE m209f_source ON COMMIT DROP AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year AS fiscal_year,
    NULLIF(BTRIM(cfda_number), '') AS program_code,
    cfda_title AS program_title,
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

-- Reconstruct the established award-first resolution hierarchy.
-- Match counts are retained to detect policy collisions.
CREATE TEMP TABLE m209f_resolved ON COMMIT DROP AS
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
        ) AS policy_rank,
        COUNT(*) OVER (
            PARTITION BY s.assistance_transaction_id
        ) AS match_count
    FROM m209f_source s
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
        ) AS policy_rank,
        COUNT(*) OVER (
            PARTITION BY s.assistance_transaction_id
        ) AS match_count
    FROM m209f_source s
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
    CASE
        WHEN a.policy_id IS NOT NULL THEN a.disposition
        WHEN p.policy_id IS NOT NULL THEN p.disposition
        ELSE 'UNCLASSIFIED_REVIEW'
    END AS resolved_disposition,
    CASE
        WHEN a.policy_id IS NOT NULL THEN a.methodology_version
        WHEN p.policy_id IS NOT NULL THEN p.methodology_version
    END AS methodology_version,
    COALESCE(a.match_count, 0) AS award_matches,
    COALESCE(p.match_count, 0) AS program_matches,
    (a.policy_id IS NOT NULL AND p.policy_id IS NOT NULL)
        AS both_layers_present
FROM m209f_source s
LEFT JOIN award_candidates a
  ON a.assistance_transaction_id = s.assistance_transaction_id
 AND a.policy_rank = 1
LEFT JOIN program_candidates p
  ON p.assistance_transaction_id = s.assistance_transaction_id
 AND p.policy_rank = 1;

\echo ''
\echo '1. FULL HISTORICAL SOURCE POPULATION'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id) AS distinct_transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(COALESCE(SUM(obligation), 0)::numeric, 2)
        AS net_obligations
FROM m209f_source
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '2. ACCOUNTING RESOLUTION - ALL HISTORICAL PROGRAMS'

SELECT
    fiscal_year,
    resolution_source,
    resolved_disposition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(COALESCE(SUM(obligation), 0)::numeric, 2)
        AS net_obligations
FROM m209f_resolved
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

\echo ''
\echo '3. REMAINING POPULATION - EXCLUDING HCV AND RRB'

SELECT
    fiscal_year,
    resolution_source,
    resolved_disposition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS programs,
    ROUND(COALESCE(SUM(obligation), 0)::numeric, 2)
        AS net_obligations
FROM m209f_resolved
WHERE program_code IS DISTINCT FROM '14.871'
  AND program_code IS DISTINCT FROM '57.001'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

\echo ''
\echo '4. TOP 30 REMAINING UNCLASSIFIED PROGRAMS'
\echo 'Ranking uses absolute net obligations for triage only.'

SELECT
    program_code,
    MAX(program_title) AS program_title,
    COUNT(*) AS transactions,
    COUNT(DISTINCT fiscal_year) AS fiscal_years,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM m209f_resolved
WHERE resolved_disposition = 'UNCLASSIFIED_REVIEW'
  AND program_code IS DISTINCT FROM '14.871'
  AND program_code IS DISTINCT FROM '57.001'
GROUP BY program_code
ORDER BY ABS(SUM(obligation)) DESC, program_code
LIMIT 30;

\echo ''
\echo '5. POLICY COLLISION AND COVERAGE DIAGNOSTICS'

SELECT
    fiscal_year,
    COUNT(*) FILTER (
        WHERE award_matches > 1
    ) AS multiple_award_matches,
    COUNT(*) FILTER (
        WHERE program_matches > 1
    ) AS multiple_program_matches,
    COUNT(*) FILTER (
        WHERE both_layers_present
    ) AS both_policy_layers_present,
    COUNT(*) FILTER (
        WHERE award_identifier IS NULL
    ) AS missing_award_identifiers,
    COUNT(*) FILTER (
        WHERE program_code IS NULL
    ) AS missing_program_codes
FROM m209f_resolved
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '6. SOURCE-TO-BRIDGE RECONCILIATION'

WITH source_control AS (
    SELECT
        fiscal_year,
        COUNT(*) AS source_rows,
        COALESCE(SUM(obligation), 0) AS source_amount
    FROM m209f_source
    GROUP BY fiscal_year
),
bridge_control AS (
    SELECT
        fiscal_year,
        COUNT(*) AS bridge_rows,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_bridge_transactions,
        COALESCE(SUM(obligation), 0) AS bridge_amount
    FROM m209f_resolved
    GROUP BY fiscal_year
)
SELECT
    s.fiscal_year,
    s.source_rows,
    b.bridge_rows,
    b.distinct_bridge_transactions,
    ROUND(s.source_amount::numeric, 2) AS source_amount,
    ROUND(b.bridge_amount::numeric, 2) AS bridge_amount,
    CASE
        WHEN s.source_rows = b.bridge_rows
         AND b.bridge_rows = b.distinct_bridge_transactions
         AND ROUND(s.source_amount::numeric, 2)
             = ROUND(b.bridge_amount::numeric, 2)
        THEN 'PASS'
        ELSE 'FAIL'
    END AS reconciliation_status
FROM source_control s
JOIN bridge_control b USING (fiscal_year)
ORDER BY s.fiscal_year;

\echo ''
\echo '7. HARD CONTROLS'

DO $$
DECLARE
    v_source bigint;
    v_bridge bigint;
    v_distinct bigint;
    v_bad_years bigint;
    v_focal bigint;
    v_focal_amount numeric;
BEGIN
    SELECT COUNT(*)
    INTO v_source
    FROM m209f_source;

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id)
    INTO v_bridge, v_distinct
    FROM m209f_resolved;

    SELECT COUNT(*)
    INTO v_bad_years
    FROM (
        SELECT fiscal_year, SUM(obligation) AS amount
        FROM m209f_source
        GROUP BY fiscal_year
        EXCEPT
        SELECT fiscal_year, SUM(obligation)
        FROM m209f_resolved
        GROUP BY fiscal_year
    ) q;

    SELECT
        COUNT(*),
        COALESCE(SUM(obligation), 0)
    INTO v_focal, v_focal_amount
    FROM m209f_resolved
    WHERE program_code IN ('14.871', '57.001');

    IF v_source <> v_bridge
       OR v_bridge <> v_distinct
       OR v_bad_years <> 0
       OR v_focal <> 4895
       OR ROUND(v_focal_amount, 2) <> 1756666452.71
    THEN
        RAISE EXCEPTION
            'ETL-209F FAIL: source %, bridge %, distinct %, bad years %, focal %, focal amount %',
            v_source, v_bridge, v_distinct,
            v_bad_years, v_focal, v_focal_amount;
    END IF;

    RAISE NOTICE
        'ETL-209F PASS: complete historical bridge preserves source and certified focal controls';
END
$$;

ROLLBACK;

\echo 'ETL-209F COMPLETE - NO PERMANENT DATABASE WRITES'
