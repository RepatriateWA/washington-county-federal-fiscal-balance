
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209P - FY2018-FY2019 ASSISTANCE ACCOUNTING BRIDGE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN;

-- 1. Historical certified source population.
CREATE TEMP TABLE etl209p_source AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), '')
    ) AS award_identifier,
    federal_action_obligation AS obligation
FROM analysis.v_certified_assistance_ledger
WHERE (load_batch_id = 20 AND action_date_fiscal_year = 2018)
   OR (load_batch_id = 21 AND action_date_fiscal_year = 2019);

-- 2. Resolve program and award classifications independently.
CREATE TEMP TABLE etl209p_resolution AS
SELECT
    s.*,
    p.federal_inflow_program_policy_mapping_id AS program_mapping_id,
    p.resolved_accounting_disposition AS program_disposition,
    a.federal_inflow_award_classification_id AS award_mapping_id,
    a.accounting_disposition AS award_disposition,
    CASE
        WHEN p.resolved_accounting_disposition IS NOT NULL
         AND a.accounting_disposition IS NOT NULL
            THEN 'BOTH'
        WHEN p.resolved_accounting_disposition IS NOT NULL
            THEN 'PROGRAM'
        WHEN a.accounting_disposition IS NOT NULL
            THEN 'AWARD'
        ELSE 'NONE'
    END AS resolution_source,
    COALESCE(
        a.accounting_disposition,
        p.resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS final_disposition
FROM etl209p_source s
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = s.program_code
 AND s.fiscal_year BETWEEN
     COALESCE(p.valid_from_fiscal_year, -9999)
     AND COALESCE(p.valid_through_fiscal_year, 9999)
LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = s.program_code
 AND a.source_award_identifier = s.award_identifier
 AND s.fiscal_year BETWEEN
     COALESCE(a.valid_from_fiscal_year, -9999)
     AND COALESCE(a.valid_through_fiscal_year, 9999);

\echo ''
\echo '1. SOURCE AND JOIN CARDINALITY'

SELECT
    (SELECT COUNT(*) FROM etl209p_source) AS source_rows,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(obligation)::numeric, 2) AS joined_obligations
FROM etl209p_resolution;

\echo ''
\echo '2. CLASSIFICATION SOURCE PROFILE'

SELECT
    resolution_source,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209p_resolution
GROUP BY resolution_source
ORDER BY resolution_source;

\echo ''
\echo '3. FINAL ACCOUNTING DISPOSITION BY FISCAL YEAR'

SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209p_resolution
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;

\echo ''
\echo '4. COMBINED ACCOUNTING DISPOSITION'

SELECT
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209p_resolution
GROUP BY final_disposition
ORDER BY final_disposition;

\echo ''
\echo '5. AWARD / PROGRAM COLLISIONS'

SELECT
    fiscal_year,
    program_code,
    program_disposition,
    award_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209p_resolution
WHERE resolution_source = 'BOTH'
GROUP BY
    fiscal_year,
    program_code,
    program_disposition,
    award_disposition
ORDER BY fiscal_year, program_code;

\echo ''
\echo '6. HARD VALIDATION ASSERTIONS'

DO $$
DECLARE
    v_source_count bigint;
    v_joined_count bigint;
    v_distinct_count bigint;
    v_total numeric;
    v_collision_count bigint;
    v_bad_disposition_count bigint;
    v_excluded_count bigint;
    v_excluded_amount numeric;
    v_additive_count bigint;
    v_additive_amount numeric;
    v_withheld_count bigint;
    v_withheld_amount numeric;
    v_unclassified_count bigint;
    v_unclassified_amount numeric;
BEGIN
    SELECT COUNT(*)
    INTO v_source_count
    FROM etl209p_source;

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (WHERE resolution_source = 'BOTH'),
        COUNT(*) FILTER (
            WHERE final_disposition NOT IN (
                'EXCLUDE_DUPLICATE',
                'INCLUDE_ADDITIVE',
                'WITHHOLD_UNRESOLVED',
                'UNCLASSIFIED_REVIEW'
            )
        )
    INTO
        v_joined_count,
        v_distinct_count,
        v_total,
        v_collision_count,
        v_bad_disposition_count
    FROM etl209p_resolution;

    IF v_source_count <> 207343
       OR v_joined_count <> 207343
       OR v_distinct_count <> 207343
       OR ROUND(v_total, 2) <> 97097242523.58
    THEN
        RAISE EXCEPTION
            'ETL-209P SOURCE/JOIN FAILURE: source %, joined %, distinct %, amount %',
            v_source_count,
            v_joined_count,
            v_distinct_count,
            v_total;
    END IF;

    IF v_collision_count <> 0
       OR v_bad_disposition_count <> 0
    THEN
        RAISE EXCEPTION
            'ETL-209P CLASSIFICATION FAILURE: collisions %, bad dispositions %',
            v_collision_count,
            v_bad_disposition_count;
    END IF;

    SELECT
        COUNT(*) FILTER (
            WHERE final_disposition = 'EXCLUDE_DUPLICATE'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'EXCLUDE_DUPLICATE'
        ), 0),
        COUNT(*) FILTER (
            WHERE final_disposition = 'INCLUDE_ADDITIVE'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'INCLUDE_ADDITIVE'
        ), 0),
        COUNT(*) FILTER (
            WHERE final_disposition = 'WITHHOLD_UNRESOLVED'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'WITHHOLD_UNRESOLVED'
        ), 0),
        COUNT(*) FILTER (
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ), 0)
    INTO
        v_excluded_count,
        v_excluded_amount,
        v_additive_count,
        v_additive_amount,
        v_withheld_count,
        v_withheld_amount,
        v_unclassified_count,
        v_unclassified_amount
    FROM etl209p_resolution;

    IF v_excluded_count <> 4991
       OR ROUND(v_excluded_amount, 2) <> 61717820211.00
       OR v_additive_count <> 4339
       OR ROUND(v_additive_amount, 2) <> 1752493369.71
       OR v_withheld_count <> 556
       OR ROUND(v_withheld_amount, 2) <> 4173083.00
       OR v_unclassified_count <> 197457
       OR ROUND(v_unclassified_amount, 2) <> 33622755859.87
    THEN
        RAISE EXCEPTION
            'ETL-209P DISPOSITION CONTROL FAILURE: excluded %/%, additive %/%, withheld %/%, unresolved %/%',
            v_excluded_count, v_excluded_amount,
            v_additive_count, v_additive_amount,
            v_withheld_count, v_withheld_amount,
            v_unclassified_count, v_unclassified_amount;
    END IF;

    RAISE NOTICE
        'ETL-209P PASS: 207343 transactions, $97097242523.58, zero collisions; all disposition controls match';
END
$$;

ROLLBACK;

\echo 'ETL-209P COMPLETE - READ ONLY'
