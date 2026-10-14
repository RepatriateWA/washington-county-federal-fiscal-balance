-- ============================================================
-- WCFFBP ETL-209W
-- POST-VA HISTORICAL ASSISTANCE ACCOUNTING BRIDGE
-- FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
--
-- Baseline: ETL-209Q
-- VA extension: ETL-209U
-- Independent policy validation: ETL-209V
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-209W - POST-VA HISTORICAL ACCOUNTING BRIDGE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

-- TEMP VIEW creation requires a regular transaction.
-- The transaction is rolled back at the end.
BEGIN;

-- ============================================================
-- 1. RECONSTRUCT ORIGINAL ETL-209Q RESOLUTION LOGIC
-- ============================================================

CREATE OR REPLACE TEMP VIEW etl209w_resolution AS
WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
resolved AS (
    SELECT
        h.*,
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
)
SELECT
    *,
    COALESCE(
        award_disposition,
        program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS final_disposition
FROM resolved;


-- ============================================================
-- 2. COMPLETE POST-VA ACCOUNTING BRIDGE
-- ============================================================

\echo ''
\echo '1. FULL POST-VA ACCOUNTING BRIDGE'

SELECT
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209w_resolution
GROUP BY final_disposition
ORDER BY final_disposition;


-- ============================================================
-- 3. FY2018-FY2019 RESOLUTION BY FISCAL YEAR
-- ============================================================

\echo ''
\echo '2. ACCOUNTING BRIDGE BY FISCAL YEAR'

SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209w_resolution
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;


-- ============================================================
-- 4. INDEPENDENT VA RECLASSIFICATION CHECK
-- ============================================================

\echo ''
\echo '3. VA AL 64.109 EFFECTIVE DISPOSITION'

SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    COUNT(*) FILTER (
        WHERE award_disposition IS NOT NULL
    ) AS award_level_overrides
FROM etl209w_resolution
WHERE program_code = '64.109'
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;


-- ============================================================
-- 5. HISTORICAL UNCLASSIFIED BALANCE
-- ============================================================

\echo ''
\echo '4. POST-VA UNCLASSIFIED BALANCE'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS distinct_programs,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl209w_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY fiscal_year
ORDER BY fiscal_year;


-- ============================================================
-- 6. UNRESOLVED PROGRAM RANKING
-- ============================================================

\echo ''
\echo '5. TOP 25 REMAINING UNCLASSIFIED PROGRAMS'

SELECT
    COALESCE(program_code, '[MISSING]') AS program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM etl209w_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY COALESCE(program_code, '[MISSING]')
ORDER BY net_obligations DESC, program_code
LIMIT 25;


-- ============================================================
-- 7. AUTOMATED HARD CONTROLS
-- ============================================================

\echo ''
\echo '6. AUTOMATED ACCOUNTING CONTROLS'

DO $$
DECLARE
    v_source bigint;
    v_distinct bigint;
    v_total numeric;

    v_excluded bigint;
    v_excluded_amount numeric;

    v_additive bigint;
    v_additive_amount numeric;

    v_withheld bigint;
    v_withheld_amount numeric;

    v_unresolved bigint;
    v_unresolved_amount numeric;

    v_collision bigint;

    v_va_rows bigint;
    v_va_amount numeric;
    v_va_bad bigint;

    v_bad bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0),

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
        ), 0),

        COUNT(*) FILTER (
            WHERE program_disposition IS NOT NULL
              AND award_disposition IS NOT NULL
        )
    INTO
        v_source,
        v_distinct,
        v_total,
        v_excluded,
        v_excluded_amount,
        v_additive,
        v_additive_amount,
        v_withheld,
        v_withheld_amount,
        v_unresolved,
        v_unresolved_amount,
        v_collision
    FROM etl209w_resolution;

    -- Source population must be unchanged.
    IF v_source <> 207343
       OR v_distinct <> 207343
       OR ROUND(v_total, 2) <> 97097242523.58 THEN
        RAISE EXCEPTION
            'ETL-209W source control failed: rows %, distinct %, amount %',
            v_source, v_distinct, v_total;
    END IF;

    -- Historical VA extension must account for exactly
    -- 929 transactions and $4,384,945,713.00.
    SELECT
        COUNT(*),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE final_disposition <> 'EXCLUDE_DUPLICATE'
               OR program_disposition <> 'EXCLUDE_DUPLICATE'
               OR award_disposition IS NOT NULL
        )
    INTO
        v_va_rows,
        v_va_amount,
        v_va_bad
    FROM etl209w_resolution
    WHERE program_code = '64.109';

    IF v_va_rows <> 929
       OR ROUND(v_va_amount, 2) <> 4384945713.00
       OR v_va_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209W VA resolution failed: rows %, amount %, bad %',
            v_va_rows, v_va_amount, v_va_bad;
    END IF;

    -- Compare against original ETL-209Q controls.
    IF v_excluded <> 5920
       OR ROUND(v_excluded_amount, 2)
          <> 66102765924.00
       OR v_additive <> 4339
       OR ROUND(v_additive_amount, 2)
          <> 1752493369.71
       OR v_withheld <> 556
       OR ROUND(v_withheld_amount, 2)
          <> 4173083.00
       OR v_unresolved <> 196528
       OR ROUND(v_unresolved_amount, 2)
          <> 29237810146.87
       OR v_collision <> 0 THEN

        RAISE EXCEPTION
            'ETL-209W accounting bridge mismatch: excluded %/%, additive %/%, withheld %/%, unresolved %/%, collisions %',
            v_excluded,
            v_excluded_amount,
            v_additive,
            v_additive_amount,
            v_withheld,
            v_withheld_amount,
            v_unresolved,
            v_unresolved_amount,
            v_collision;
    END IF;

    -- All effective dispositions must be recognized.
    SELECT COUNT(*)
    INTO v_bad
    FROM etl209w_resolution
    WHERE final_disposition NOT IN (
        'EXCLUDE_DUPLICATE',
        'INCLUDE_ADDITIVE',
        'WITHHOLD_UNRESOLVED',
        'UNCLASSIFIED_REVIEW'
    )
       OR final_disposition IS NULL;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209W unexpected accounting dispositions: %',
            v_bad;
    END IF;

    RAISE NOTICE
        'ETL-209W PASS: 196528 unresolved transactions, $29237810146.87, 929 VA exclusions, zero collisions';

END $$;

ROLLBACK;

\echo 'ETL-209W COMPLETE - NO DATABASE WRITES'