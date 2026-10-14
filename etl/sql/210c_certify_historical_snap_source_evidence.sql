-- ============================================================
-- WCFFBP ETL-210C
-- HISTORICAL SNAP SOURCE-EVIDENCE CERTIFICATION
-- FY2018-FY2019 | Assistance Listing 10.551
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210C - HISTORICAL SNAP SOURCE CERTIFICATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. Complete raw recipient and award inventory
-- ============================================================

\echo ''
\echo '1. RAW RECIPIENT AND AWARD INVENTORY'

WITH snap AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        c.assistance_transaction_id,
        c.federal_action_obligation AS obligation,
        r.raw_record AS raw
    FROM analysis.v_certified_assistance_ledger c
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) = '10.551'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    COALESCE(
        NULLIF(BTRIM(raw->>'award_id_uri'), ''),
        NULLIF(BTRIM(raw->>'award_id_fain'), ''),
        '[MISSING]'
    ) AS award_identifier,
    NULLIF(BTRIM(raw->>'recipient_name'), '')
        AS recipient_name,
    NULLIF(BTRIM(raw->>'recipient_name_raw'), '')
        AS recipient_name_raw,
    NULLIF(BTRIM(raw->>'recipient_state_code'), '')
        AS recipient_state,
    NULLIF(BTRIM(raw->>'primary_place_of_performance_code'), '')
        AS performance_code,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM snap
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY fiscal_year, net_obligations DESC;


-- ============================================================
-- 2. Award-level program and agency evidence
-- ============================================================

\echo ''
\echo '2. PROGRAM AND AGENCY CONTINUITY'

WITH snap AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        c.federal_action_obligation AS obligation,
        r.raw_record AS raw
    FROM analysis.v_certified_assistance_ledger c
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) = '10.551'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    raw->>'cfda_number' AS raw_program_code,
    raw->>'cfda_title' AS raw_program_title,
    raw->>'awarding_agency_name' AS awarding_agency,
    raw->>'awarding_sub_agency_name' AS awarding_subagency,
    raw->>'funding_agency_name' AS funding_agency,
    raw->>'funding_sub_agency_name' AS funding_subagency,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM snap
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY fiscal_year, net_obligations DESC;


-- ============================================================
-- 3. Individual award adjustments and geographic exceptions
-- ============================================================

\echo ''
\echo '3. AWARD AND GEOGRAPHIC EXCEPTIONS'

WITH snap AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        c.assistance_transaction_id,
        c.federal_action_obligation AS obligation,
        r.raw_record AS raw
    FROM analysis.v_certified_assistance_ledger c
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) = '10.551'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    assistance_transaction_id,
    COALESCE(
        NULLIF(BTRIM(raw->>'award_id_uri'), ''),
        NULLIF(BTRIM(raw->>'award_id_fain'), '')
    ) AS award_identifier,
    obligation,
    raw->>'recipient_name' AS recipient_name,
    raw->>'recipient_state_code' AS recipient_state,
    raw->>'prime_award_transaction_recipient_state_fips_code'
        AS recipient_state_fips,
    raw->>'primary_place_of_performance_code'
        AS performance_code,
    raw->>'prime_award_transaction_place_of_performance_state_fips_code'
        AS performance_state_fips,
    raw->>'prime_award_transaction_place_of_performance_county_fips_code'
        AS performance_county_fips
FROM snap
WHERE obligation < 0
   OR NULLIF(BTRIM(
       raw->>'prime_award_transaction_place_of_performance_county_fips_code'
   ), '') IS NOT NULL
   OR COALESCE(BTRIM(raw->>'recipient_state_code'), '') <> 'WA'
   OR COALESCE(BTRIM(
       raw->>'prime_award_transaction_place_of_performance_state_fips_code'
   ), '') <> '53'
ORDER BY fiscal_year, assistance_transaction_id;


-- ============================================================
-- 4. Benefit-stream versus administrative-program evidence
-- ============================================================

\echo ''
\echo '4. SNAP BENEFIT AND ADMINISTRATIVE PROGRAM DISTINCTION'

WITH snap AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        c.federal_action_obligation AS obligation,
        r.raw_record AS raw
    FROM analysis.v_certified_assistance_ledger c
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) = '10.551'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    raw->>'cfda_number' AS program_code,
    raw->>'prime_award_base_transaction_description'
        AS source_description,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM snap
GROUP BY 1, 2, 3
ORDER BY fiscal_year, program_code;


-- ============================================================
-- 5. Automated certification controls
-- ============================================================

\echo ''
\echo '5. AUTOMATED SOURCE CERTIFICATION'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_raw_matches bigint;
    v_wa_recipient bigint;
    v_wa_performance bigint;
    v_usda bigint;
    v_fns bigint;
    v_snap bigint;
    v_missing_recipient bigint;
    v_distinct_awards bigint;
BEGIN

    WITH snap AS (
        SELECT
            c.assistance_transaction_id,
            c.federal_action_obligation AS obligation,
            r.raw_assistance_transaction_id AS raw_id,
            r.raw_record AS raw
        FROM analysis.v_certified_assistance_ledger c
        LEFT JOIN assistance.raw_award_transaction r
          ON r.load_batch_id = c.load_batch_id
         AND r.source_row_number = c.source_row_number
        WHERE BTRIM(c.cfda_number) = '10.551'
          AND (
               (c.load_batch_id = 20
                AND c.action_date_fiscal_year = 2018)
            OR (c.load_batch_id = 21
                AND c.action_date_fiscal_year = 2019)
          )
    )
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0),
        COUNT(raw_id),

        COUNT(*) FILTER (
            WHERE BTRIM(raw->>'recipient_state_code') = 'WA'
              AND BTRIM(
                  raw->>'prime_award_transaction_recipient_state_fips_code'
              ) = '53'
        ),

        COUNT(*) FILTER (
            WHERE BTRIM(
                raw->>'prime_award_transaction_place_of_performance_state_fips_code'
            ) = '53'
              AND BTRIM(
                  raw->>'primary_place_of_performance_state_name'
              ) = 'WASHINGTON'
        ),

        COUNT(*) FILTER (
            WHERE BTRIM(raw->>'awarding_agency_code') = '012'
              AND BTRIM(raw->>'funding_agency_code') = '012'
        ),

        COUNT(*) FILTER (
            WHERE BTRIM(raw->>'awarding_sub_agency_name')
                  = 'Food and Nutrition Service'
              AND BTRIM(raw->>'funding_sub_agency_name')
                  = 'Food and Nutrition Service'
        ),

        COUNT(*) FILTER (
            WHERE BTRIM(raw->>'cfda_number') = '10.551'
              AND UPPER(
                  BTRIM(raw->>'cfda_title')
              ) = 'SUPPLEMENTAL NUTRITION ASSISTANCE PROGRAM'
        ),

        COUNT(*) FILTER (
            WHERE NULLIF(BTRIM(raw->>'recipient_name'), '')
                  IS NULL
        ),

        COUNT(DISTINCT COALESCE(
            NULLIF(BTRIM(raw->>'award_id_uri'), ''),
            NULLIF(BTRIM(raw->>'award_id_fain'), '')
        ))
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_raw_matches,
        v_wa_recipient,
        v_wa_performance,
        v_usda,
        v_fns,
        v_snap,
        v_missing_recipient,
        v_distinct_awards
    FROM snap;

    IF v_rows <> 27
       OR v_distinct <> 27
       OR ROUND(v_net, 2) <> 2461253053.11
       OR v_raw_matches <> 27
    THEN
        RAISE EXCEPTION
            'ETL-210C population control failed: rows %, distinct %, raw %, net %',
            v_rows, v_distinct, v_raw_matches, v_net;
    END IF;

    IF v_wa_recipient <> 27
       OR v_wa_performance <> 27
       OR v_usda <> 27
       OR v_fns <> 27
       OR v_snap <> 27
       OR v_missing_recipient <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210C provenance exception: WA recipient %, WA performance %, USDA %, FNS %, SNAP %, missing recipient %',
            v_wa_recipient,
            v_wa_performance,
            v_usda,
            v_fns,
            v_snap,
            v_missing_recipient;
    END IF;

    IF v_distinct_awards <> 4 THEN
        RAISE EXCEPTION
            'ETL-210C award count mismatch: %',
            v_distinct_awards;
    END IF;

    RAISE NOTICE
        'ETL-210C PASS: 27 transactions, 4 distinct awards, $2461253053.11 net; raw WA/USDA/FNS/SNAP evidence complete';

END $$;

COMMIT;

\echo 'ETL-210C COMPLETE - READ ONLY'