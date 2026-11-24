-- ============================================================
-- WCFFBP ETL-210L
-- POST-SSI HISTORICAL ASSISTANCE ACCOUNTING BRIDGE
-- FY2018-FY2019
--
-- READ ONLY IN EFFECT
-- TEMP VIEW ONLY; FINAL ROLLBACK
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210L - POST-SSI HISTORICAL ACCOUNTING BRIDGE'
\echo 'NO PERSISTENT DATABASE WRITES'
\echo '============================================================'

BEGIN;

CREATE TEMP VIEW etl210l_resolution AS
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


\echo ''
\echo '1. COMPLETE POST-SSI ACCOUNTING BRIDGE'

SELECT
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl210l_resolution
GROUP BY final_disposition
ORDER BY final_disposition;


\echo ''
\echo '2. ACCOUNTING BRIDGE BY FISCAL YEAR'

SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl210l_resolution
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;


\echo ''
\echo '3. SSI ADDITIVE CLASSIFICATION'

SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    COUNT(*) FILTER (
        WHERE program_disposition = 'INCLUDE_ADDITIVE'
    ) AS program_level_inclusions,
    COUNT(*) FILTER (
        WHERE award_disposition IS NOT NULL
    ) AS award_overrides
FROM etl210l_resolution
WHERE program_code = '96.006'
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year;


\echo ''
\echo '4. SNAP AND VA PRESERVATION'

SELECT
    program_code,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl210l_resolution
WHERE program_code IN ('10.551', '64.109')
GROUP BY program_code, final_disposition
ORDER BY program_code, final_disposition;


\echo ''
\echo '5. REMAINING UNRESOLVED BY FISCAL YEAR'

SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT program_code) AS distinct_programs,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl210l_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY fiscal_year
ORDER BY fiscal_year;


\echo ''
\echo '6. TOP 25 REMAINING UNRESOLVED PROGRAMS'

SELECT
    COALESCE(program_code, '[MISSING]') AS program_code,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations
FROM etl210l_resolution
WHERE final_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY COALESCE(program_code, '[MISSING]')
ORDER BY net_obligations DESC, program_code
LIMIT 25;


\echo ''
\echo '7. AUTOMATED ACCOUNTING CONTROLS'

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

    v_ssi_rows bigint;
    v_ssi_net numeric;
    v_ssi_bad bigint;

    v_snap_rows bigint;
    v_snap_net numeric;
    v_snap_bad bigint;

    v_va_rows bigint;
    v_va_net numeric;
    v_va_bad bigint;
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
    FROM etl210l_resolution;

    IF v_source <> 207343
       OR v_distinct <> 207343
       OR ROUND(v_total, 2) <> 97097242523.58
    THEN
        RAISE EXCEPTION
            'ETL-210L source conservation FAIL: rows %, distinct %, net %',
            v_source, v_distinct, v_total;
    END IF;

    IF v_excluded <> 5920
       OR ROUND(v_excluded_amount, 2) <> 66102765924.00

       OR v_additive <> 6024
       OR ROUND(v_additive_amount, 2) <> 6298007268.82

       OR v_unresolved <> 194843
       OR ROUND(v_unresolved_amount, 2) <> 24692296247.76

       OR v_withheld <> 556
       OR ROUND(v_withheld_amount, 2) <> 4173083.00

       OR v_collision <> 0
       OR v_invalid <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210L bridge FAIL: excluded %/%, additive %/%, unresolved %/%, withheld %/%, collisions %, invalid %',
            v_excluded, v_excluded_amount,
            v_additive, v_additive_amount,
            v_unresolved, v_unresolved_amount,
            v_withheld, v_withheld_amount,
            v_collision, v_invalid;
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE final_disposition <> 'INCLUDE_ADDITIVE'
               OR program_disposition <> 'INCLUDE_ADDITIVE'
               OR award_disposition IS NOT NULL
        )
    INTO v_ssi_rows, v_ssi_net, v_ssi_bad
    FROM etl210l_resolution
    WHERE program_code = '96.006';

    IF v_ssi_rows <> 1658
       OR ROUND(v_ssi_net, 2) <> 2084260846.00
       OR v_ssi_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210L SSI FAIL: rows %, net %, exceptions %',
            v_ssi_rows, v_ssi_net, v_ssi_bad;
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE final_disposition <> 'INCLUDE_ADDITIVE'
               OR program_disposition <> 'INCLUDE_ADDITIVE'
               OR award_disposition IS NOT NULL
        )
    INTO v_snap_rows, v_snap_net, v_snap_bad
    FROM etl210l_resolution
    WHERE program_code = '10.551';

    IF v_snap_rows <> 27
       OR ROUND(v_snap_net, 2) <> 2461253053.11
       OR v_snap_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210L SNAP FAIL: rows %, net %, exceptions %',
            v_snap_rows, v_snap_net, v_snap_bad;
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE final_disposition <> 'EXCLUDE_DUPLICATE'
               OR program_disposition <> 'EXCLUDE_DUPLICATE'
               OR award_disposition IS NOT NULL
        )
    INTO v_va_rows, v_va_net, v_va_bad
    FROM etl210l_resolution
    WHERE program_code = '64.109';

    IF v_va_rows <> 929
       OR ROUND(v_va_net, 2) <> 4384945713.00
       OR v_va_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210L VA FAIL: rows %, net %, exceptions %',
            v_va_rows, v_va_net, v_va_bad;
    END IF;

    RAISE NOTICE
        'ETL-210L PASS: 207343 transactions conserved; SSI 1658 additive; SNAP 27 additive; VA 929 excluded; zero collisions';

END $$;

-- Discard temporary view.
ROLLBACK;

\echo 'ETL-210L COMPLETE - NO DATABASE WRITES'