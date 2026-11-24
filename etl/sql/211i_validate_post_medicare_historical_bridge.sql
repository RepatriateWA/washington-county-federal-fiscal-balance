
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211I - POST-MEDICARE HISTORICAL BRIDGE'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - FINAL ROLLBACK'
\echo '============================================================'

BEGIN;

-- Reconstruct the ETL-210Q accounting resolution.
CREATE TEMP VIEW etl211i_resolution AS
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
        p.methodology_version AS program_methodology,
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
\echo '1. COMPLETE ACCOUNTING BRIDGE'

SELECT
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl211i_resolution
GROUP BY final_disposition
ORDER BY final_disposition;

\echo ''
\echo '2. MEDICARE PROGRAMS BY FISCAL YEAR'

SELECT
    fiscal_year,
    program_code,
    program_methodology,
    program_disposition,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    COUNT(*) FILTER (
        WHERE award_disposition IS NOT NULL
    ) AS award_override_matches
FROM etl211i_resolution
WHERE program_code IN ('93.773', '93.774')
GROUP BY
    fiscal_year,
    program_code,
    program_methodology,
    program_disposition,
    final_disposition
ORDER BY fiscal_year, program_code;

\echo ''
\echo '3. ACCOUNTING BRIDGE BY FISCAL YEAR'

SELECT
    fiscal_year,
    final_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM etl211i_resolution
GROUP BY fiscal_year, final_disposition
ORDER BY fiscal_year, final_disposition;

\echo ''
\echo '4. AUTOMATED CERTIFICATION'

DO $$
DECLARE
    v_rows bigint;
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

    v_medicare_rows bigint;
    v_medicare_amount numeric;
    v_medicare_bad bigint;
    v_medicare_distinct bigint;

    v_collisions bigint;
    v_invalid bigint;
    v_missing numeric;
    v_program text;
    v_expected_rows bigint;
    v_expected_net numeric;
    v_expected_disposition text;
    v_actual_rows bigint;
    v_actual_net numeric;
    v_bad_rows bigint;
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
        ),
        COALESCE(SUM(obligation) FILTER (
            WHERE final_disposition = 'INCLUDE_ADDITIVE'
              AND program_code IN ('93.773', '93.774')
        ), 0)
    INTO
        v_rows, v_distinct, v_total,
        v_excluded, v_excluded_amount,
        v_additive, v_additive_amount,
        v_unresolved, v_unresolved_amount,
        v_withheld, v_withheld_amount,
        v_collisions, v_invalid, v_missing
    FROM etl211i_resolution;

    IF v_rows <> 207343
       OR v_distinct <> 207343
       OR ROUND(v_total, 2) <> 97097242523.58
    THEN
        RAISE EXCEPTION
            'ETL-211I SOURCE CONSERVATION FAIL: rows %, distinct %, dollars %',
            v_rows, v_distinct, v_total;
    END IF;

    IF v_excluded <> 5956
       OR ROUND(v_excluded_amount, 2) <> 68592496232.00
       OR v_additive <> 10823
       OR ROUND(v_additive_amount, 2) <> 7749510380.85
       OR v_unresolved <> 190008
       OR ROUND(v_unresolved_amount, 2) <> 20751062827.73
       OR v_withheld <> 556
       OR ROUND(v_withheld_amount, 2) <> 4173083.00
       OR v_collisions <> 0
       OR v_invalid <> 0
       OR v_missing <> 0
    THEN
        RAISE EXCEPTION
            'ETL-211I BRIDGE FAIL: excluded %/%, additive %/%, unresolved %/%, withheld %/%, collisions %, invalid %, Medicare additive %',
            v_excluded, v_excluded_amount,
            v_additive, v_additive_amount,
            v_unresolved, v_unresolved_amount,
            v_withheld, v_withheld_amount,
            v_collisions, v_invalid, v_missing;
    END IF;

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0),
        COUNT(*) FILTER (
            WHERE final_disposition <> 'EXCLUDE_DUPLICATE'
               OR program_disposition <> 'EXCLUDE_DUPLICATE'
               OR program_methodology IS DISTINCT FROM
                  'ANALYSIS-211H-HISTORICAL-MEDICARE-v1'
               OR program_mapping_id IS NULL
               OR award_disposition IS NOT NULL
        )
    INTO
        v_medicare_rows,
        v_medicare_distinct,
        v_medicare_amount,
        v_medicare_bad
    FROM etl211i_resolution
    WHERE program_code IN ('93.773', '93.774');

    IF v_medicare_rows <> 36
       OR v_medicare_distinct <> 36
       OR ROUND(v_medicare_amount, 2) <> 2489730308.00
       OR v_medicare_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-211I MEDICARE FAIL: rows %, distinct %, dollars %, classification exceptions %',
            v_medicare_rows, v_medicare_distinct,
            v_medicare_amount, v_medicare_bad;
    END IF;

    -- Preserve ETL-210Q's four prior program controls.
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
        FROM etl211i_resolution
        WHERE program_code = v_program;

        IF v_actual_rows <> v_expected_rows
           OR ROUND(v_actual_net, 2) <>
              ROUND(v_expected_net, 2)
           OR v_bad_rows <> 0
        THEN
            RAISE EXCEPTION
                'ETL-211I PRESERVATION FAIL: program %, rows %, dollars %, exceptions %',
                v_program, v_actual_rows,
                v_actual_net, v_bad_rows;
        END IF;
    END LOOP;

    RAISE NOTICE
        'ETL-211I PASS: 207343 transactions conserved; Medicare 36/$2489730308 excluded; four prior programs preserved; no collisions or additive Medicare obligations';
END $$;

ROLLBACK;

\echo 'ETL-211I COMPLETE - NO DATABASE WRITES'
