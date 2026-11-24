-- ============================================================
-- WCFFBP ETL-210M
-- HISTORICAL AL 20.205 SOURCE AND OVERLAP-RISK PROFILE
-- FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210M - HISTORICAL AL 20.205 PROFILE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. HISTORICAL SOURCE CONTROLS
-- ============================================================

\echo ''
\echo '1. SOURCE POPULATION AND FINANCIAL CONTROLS'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT c.assistance_transaction_id)
        AS distinct_transactions,
    COUNT(*) FILTER (
        WHERE c.federal_action_obligation > 0
    ) AS positive_rows,
    COUNT(*) FILTER (
        WHERE c.federal_action_obligation < 0
    ) AS negative_rows,
    COUNT(*) FILTER (
        WHERE c.federal_action_obligation = 0
    ) AS zero_rows,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(c.federal_action_obligation))::numeric, 2)
        AS gross_absolute,
    ROUND(SUM(c.federal_action_obligation) FILTER (
        WHERE c.federal_action_obligation > 0
    )::numeric, 2) AS positive_obligations,
    ROUND(SUM(c.federal_action_obligation) FILTER (
        WHERE c.federal_action_obligation < 0
    )::numeric, 2) AS negative_obligations
FROM analysis.v_certified_assistance_ledger c
WHERE BTRIM(c.cfda_number) = '20.205'
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  )
GROUP BY c.action_date_fiscal_year
ORDER BY fiscal_year;


-- ============================================================
-- 2. RAW SOURCE LINKAGE
-- ============================================================

\echo ''
\echo '2. RAW SOURCE LINKAGE'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS certified_rows,
    COUNT(r.raw_record) AS linked_raw_rows,
    COUNT(*) FILTER (
        WHERE r.raw_record IS NULL
    ) AS missing_raw_rows
FROM analysis.v_certified_assistance_ledger c
LEFT JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = c.load_batch_id
 AND r.source_row_number = c.source_row_number
WHERE BTRIM(c.cfda_number) = '20.205'
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  )
GROUP BY c.action_date_fiscal_year
ORDER BY fiscal_year;


-- ============================================================
-- 3. SOURCE PROGRAM AND AGENCY IDENTITY
-- ============================================================

\echo ''
\echo '3. RAW PROGRAM AND AGENCY IDENTITY'

SELECT
    COALESCE(
        NULLIF(BTRIM(r.raw_record->>'cfda_title'), ''),
        '[MISSING]'
    ) AS program_title,
    COALESCE(
        NULLIF(BTRIM(r.raw_record->>'awarding_agency_name'), ''),
        '[MISSING]'
    ) AS awarding_agency,
    COALESCE(
        NULLIF(BTRIM(r.raw_record->>'funding_agency_name'), ''),
        '[MISSING]'
    ) AS funding_agency,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger c
JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = c.load_batch_id
 AND r.source_row_number = c.source_row_number
WHERE BTRIM(c.cfda_number) = '20.205'
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  )
GROUP BY 1, 2, 3
ORDER BY ABS(SUM(c.federal_action_obligation)) DESC
LIMIT 20;


-- ============================================================
-- 4. RECIPIENT AND PERFORMANCE GEOGRAPHY
-- ============================================================

\echo ''
\echo '4. RAW GEOGRAPHIC EVIDENCE'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    COALESCE(
        NULLIF(BTRIM(r.raw_record->>'recipient_state_code'), ''),
        '[MISSING]'
    ) AS recipient_state,
    COALESCE(
        NULLIF(BTRIM(
            r.raw_record->>'primary_place_of_performance_state_fips_code'
        ), ''),
        '[MISSING]'
    ) AS performance_state_fips,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger c
JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = c.load_batch_id
 AND r.source_row_number = c.source_row_number
WHERE BTRIM(c.cfda_number) = '20.205'
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  )
GROUP BY 1, 2, 3
ORDER BY fiscal_year, ABS(SUM(c.federal_action_obligation)) DESC
LIMIT 30;


-- ============================================================
-- 5. RECIPIENT CONCENTRATION
-- ============================================================

\echo ''
\echo '5. TOP RECIPIENTS'

SELECT
    COALESCE(
        NULLIF(BTRIM(r.raw_record->>'recipient_name'), ''),
        '[MISSING]'
    ) AS recipient_name,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(c.federal_action_obligation))::numeric, 2)
        AS gross_absolute
FROM analysis.v_certified_assistance_ledger c
JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = c.load_batch_id
 AND r.source_row_number = c.source_row_number
WHERE BTRIM(c.cfda_number) = '20.205'
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  )
GROUP BY 1
ORDER BY ABS(SUM(c.federal_action_obligation)) DESC
LIMIT 20;


-- ============================================================
-- 6. AWARD CONCENTRATION
-- ============================================================

\echo ''
\echo '6. TOP AWARDS BY GROSS ACTIVITY'

SELECT
    COALESCE(
        NULLIF(BTRIM(c.award_id_fain), ''),
        NULLIF(BTRIM(c.award_id_uri), ''),
        '[MISSING]'
    ) AS award_identifier,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(c.federal_action_obligation))::numeric, 2)
        AS gross_absolute
FROM analysis.v_certified_assistance_ledger c
WHERE BTRIM(c.cfda_number) = '20.205'
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  )
GROUP BY 1
ORDER BY gross_absolute DESC
LIMIT 20;


-- ============================================================
-- 7. EXISTING PROGRAM POLICIES
-- ============================================================

\echo ''
\echo '7. EXISTING AL 20.205 POLICY COVERAGE'

SELECT
    p.federal_inflow_program_policy_mapping_id AS mapping_id,
    p.federal_inflow_source_policy_id AS source_policy_id,
    p.source_system,
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping p
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE BTRIM(p.source_program_code) = '20.205'
ORDER BY p.valid_from_fiscal_year;


-- ============================================================
-- 8. AWARD OVERRIDES
-- ============================================================

\echo ''
\echo '8. HISTORICAL AWARD OVERRIDE COUNTS'

WITH historical AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE BTRIM(c.cfda_number) = '20.205'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    h.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(a.accounting_disposition)
        AS award_override_matches,
    COUNT(*) FILTER (
        WHERE h.award_identifier IS NULL
    ) AS missing_award_identifiers
FROM historical h
LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(a.source_program_code) = '20.205'
 AND a.source_award_identifier = h.award_identifier
 AND h.fiscal_year BETWEEN
     COALESCE(a.valid_from_fiscal_year, -9999)
     AND COALESCE(a.valid_through_fiscal_year, 9999)
GROUP BY h.fiscal_year
ORDER BY h.fiscal_year;


-- ============================================================
-- 9. RAW SOURCE FIELD AVAILABILITY
-- ============================================================

\echo ''
\echo '9. SELECTED RAW SOURCE FIELD AVAILABILITY'

SELECT
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(
            r.raw_record->>'assistance_award_unique_key'
        ), '') IS NOT NULL
    ) AS unique_key_present,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(
            r.raw_record->>'award_id_uri'
        ), '') IS NOT NULL
    ) AS award_uri_present,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(
            r.raw_record->>'recipient_name'
        ), '') IS NOT NULL
    ) AS recipient_present,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(
            r.raw_record->>'awarding_agency_name'
        ), '') IS NOT NULL
    ) AS awarding_agency_present,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(
            r.raw_record->>'funding_agency_name'
        ), '') IS NOT NULL
    ) AS funding_agency_present
FROM analysis.v_certified_assistance_ledger c
JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = c.load_batch_id
 AND r.source_row_number = c.source_row_number
WHERE BTRIM(c.cfda_number) = '20.205'
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  );


-- ============================================================
-- 10. AUTOMATED SOURCE CONTROLS
-- ============================================================

\echo ''
\echo '10. AUTOMATED SOURCE CONTROLS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_gross numeric;
    v_raw bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT c.assistance_transaction_id),
        COALESCE(SUM(c.federal_action_obligation), 0),
        COALESCE(SUM(ABS(c.federal_action_obligation)), 0),
        COUNT(r.raw_record)
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_gross,
        v_raw
    FROM analysis.v_certified_assistance_ledger c
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) = '20.205'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      );

    IF v_rows <> 4799
       OR v_distinct <> 4799
       OR ROUND(v_net, 2) <> 1451503112.03
       OR ROUND(v_gross, 2) <> 2274783059.83
       OR v_raw <> 4799
    THEN
        RAISE EXCEPTION
            'ETL-210M FAIL: rows %, distinct %, net %, gross %, raw links %',
            v_rows, v_distinct, v_net, v_gross, v_raw;
    END IF;

    RAISE NOTICE
        'ETL-210M PASS: 4799 AL 20.205 transactions; net $1451503112.03; gross $2274783059.83; complete raw linkage';
END $$;

COMMIT;

\echo 'ETL-210M COMPLETE - READ ONLY'