-- ============================================================
-- WCFFBP ETL-210Q
-- POST-HIGHWAY HISTORICAL ASSISTANCE ACCOUNTING BRIDGE
-- FY2018-FY2019
--
-- NO PERSISTENT DATABASE WRITES
-- TEMP VIEW, FINAL ROLLBACK
--
-- Baseline: ETL-210L
-- Highway migration: ETL-210O
-- Independent validation: ETL-210P
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210Q - POST-HIGHWAY HISTORICAL BRIDGE'
\echo 'FY2018-FY2019'
\echo 'NO PERSISTENT DATABASE WRITES'
\echo '============================================================'

BEGIN;

-- ============================================================
-- 1. RECONSTRUCT EFFECTIVE DISPOSITIONS
-- ============================================================

CREATE TEMP VIEW etl210q_resolution AS
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
        p.federal_inflow_program_policy_mapping_id
            AS program_mapping_id,
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
-- 2. COMPLETE ACCOUNTING BRIDGE
-- ============================================================

\echo ''
\echo '1. COMPLETE POST-HIGHWAY ACCOUNTING BRIDGE'

SELECT
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM etl210q_resolution
GROUP BY final_disposition
ORDER BY final_disposition;


-- ============================================================
-- 3. ACCOUNTING BRIDGE BY FISCAL YEAR
-- ============================================================

\echo ''
\echo '2. ACCOUNTING BRIDGE BY FISCAL YEAR'

SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM etl210q_resolution
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;


-- ============================================================
-- 4. HISTORICAL PROGRAM PRESERVATION
-- ============================================================

\echo ''
\echo '3. CERTIFIED PROGRAM CLASSIFICATIONS'

SELECT
    program_code,
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE award_disposition IS NOT NULL
    ) AS award_override_matches
FROM etl210q_resolution
WHERE program_code IN (
    '10.551',  -- SNAP
    '96.006',  -- SSI
    '64.109',  -- VA
    '20.205'   -- Highway
)
GROUP BY
    program_code,
    fiscal_year,
    final_disposition
ORDER BY program_code, fiscal_year;


-- ============================================================
-- 5. REMAINING UNRESOLVED PROGRAMS
-- ============================================================

\echo ''
\echo '4. REMAINING UNRESOLVED ASSISTANCE BY YEAR'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS distinct_programs,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM etl210q_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY fiscal_year
ORDER BY fiscal_year;


\echo ''
\echo '5. TOP 25 REMAINING UNRESOLVED PROGRAMS'

SELECT
    COALESCE(program_code, '[MISSING]') AS program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM etl210q_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY COALESCE(program_code, '[MISSING]')
ORDER BY net_obligations DESC, program_code
LIMIT 25;


-- ============================================================
-- 6. AUTOMATED ACCOUNTING CONTROLS
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

    v_unresolved bigint;
    v_unresolved_amount numeric;

    v_withheld bigint;
    v_withheld_amount numeric;

    v_collision bigint;
    v_invalid bigint;

    v_program text;
    v_expected_rows bigint;
    v_expected_net numeric;
    v_expected_disposition text;

    v_actual_rows bigint;
    v_actual_net numeric;
    v_bad_rows bigint;
BEGIN

    -- Source and disposition conservation.

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
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
        ), 0),

        COUNT(*) FILTER (
            WHERE final_disposition = 'WITHHOLD_UNRESOLVED'
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'WITHHOLD_UNRESOLVED'
        ), 0),

        COUNT(*) FILTER (
            WHERE program_disposition IS NOT NULL
              AND award_disposition IS NOT NULL
        ),

        COUNT(*) FILTER (
            WHERE final_disposition IS NULL
               OR final_disposition NOT IN (
                   'EXCLUDE_DUPLICATE',
                   'INCLUDE_ADDITIVE',
                   'UNCLASSIFIED_REVIEW',
                   'WITHHOLD_UNRESOLVED'
               )
        )
    INTO
        v_source,
        v_distinct,
        v_total,
        v_excluded,
        v_excluded_amount,
        v_additive,
        v_additive_amount,
        v_unresolved,
        v_unresolved_amount,
        v_withheld,
        v_withheld_amount,
        v_collision,
        v_invalid
    FROM etl210q_resolution;

    IF v_source <> 207343
       OR v_distinct <> 207343
       OR ROUND(v_total, 2) <> 97097242523.58
    THEN
        RAISE EXCEPTION
            'ETL-210Q source conservation FAIL: rows %, distinct %, net %',
            v_source, v_distinct, v_total;
    END IF;

    IF v_excluded <> 5920
       OR ROUND(v_excluded_amount, 2) <> 66102765924.00
       OR v_additive <> 10823
       OR ROUND(v_additive_amount, 2) <> 7749510380.85
       OR v_unresolved <> 190044
       OR ROUND(v_unresolved_amount, 2) <> 23240793135.73
       OR v_withheld <> 556
       OR ROUND(v_withheld_amount, 2) <> 4173083.00
       OR v_collision <> 0
       OR v_invalid <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210Q bridge FAIL: excluded %/%, additive %/%, unresolved %/%, withheld %/%, collisions %, invalid %',
            v_excluded, v_excluded_amount,
            v_additive, v_additive_amount,
            v_unresolved, v_unresolved_amount,
            v_withheld, v_withheld_amount,
            v_collision, v_invalid;
    END IF;

    -- Independently preserve all four recently
    -- certified historical program classifications.

    FOR
        v_program,
        v_expected_rows,
        v_expected_net,
        v_expected_disposition
    IN
        SELECT *
        FROM (
            VALUES
                ('10.551'::text, 27::bigint,
                 2461253053.11::numeric,
                 'INCLUDE_ADDITIVE'::text),

                ('96.006'::text, 1658::bigint,
                 2084260846.00::numeric,
                 'INCLUDE_ADDITIVE'::text),

                ('64.109'::text, 929::bigint,
                 4384945713.00::numeric,
                 'EXCLUDE_DUPLICATE'::text),

                ('20.205'::text, 4799::bigint,
                 1451503112.03::numeric,
                 'INCLUDE_ADDITIVE'::text)
        ) AS expected(
            program_code,
            transactions,
            net_obligations,
            disposition
        )
    LOOP

        SELECT
            COUNT(*),
            COALESCE(SUM(obligation), 0),
            COUNT(*) FILTER (
                WHERE final_disposition
                    IS DISTINCT FROM v_expected_disposition
                   OR program_disposition
                    IS DISTINCT FROM v_expected_disposition
                   OR award_disposition IS NOT NULL
            )
        INTO
            v_actual_rows,
            v_actual_net,
            v_bad_rows
        FROM etl210q_resolution
        WHERE program_code = v_program;

        IF v_actual_rows <> v_expected_rows
           OR ROUND(v_actual_net, 2) <>
              ROUND(v_expected_net, 2)
           OR v_bad_rows <> 0
        THEN
            RAISE EXCEPTION
                'ETL-210Q program % FAIL: rows %, net %, classification exceptions %',
                v_program,
                v_actual_rows,
                v_actual_net,
                v_bad_rows;
        END IF;

    END LOOP;

    RAISE NOTICE
        'ETL-210Q PASS: 207343 transactions conserved; highway 4799/$1451503112.03 additive; SNAP, SSI, VA preserved; zero collisions';

END $$;

-- Discard temporary view.
ROLLBACK;

\echo 'ETL-210Q COMPLETE - NO DATABASE WRITES'