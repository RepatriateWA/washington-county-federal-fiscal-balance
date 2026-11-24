-- ============================================================
-- WCFFBP ETL-210R
-- HISTORICAL HEALTH ASSISTANCE OVERLAP-RISK PROFILE
-- AL 93.773 AND 93.774, FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210R - HISTORICAL HEALTH OVERLAP PROFILE'
\echo 'AL 93.773 AND 93.774'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. SOURCE POPULATION AND RAW PROVENANCE
-- ============================================================

\echo ''
\echo '1. TRANSACTION AND FINANCIAL PROFILE'

WITH target AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        c.load_batch_id,
        c.source_row_number,
        c.award_id_fain,
        c.award_id_uri,
        r.raw_record AS raw
    FROM analysis.v_certified_assistance_ledger c
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    program_code,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(*) FILTER (WHERE obligation > 0)
        AS positive_transactions,
    COUNT(*) FILTER (WHERE obligation < 0)
        AS negative_transactions,
    COUNT(*) FILTER (WHERE obligation = 0)
        AS zero_transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS gross_absolute_obligations,
    COUNT(*) FILTER (WHERE raw IS NULL)
        AS missing_raw_records
FROM target
GROUP BY fiscal_year, program_code
ORDER BY fiscal_year, program_code;


-- ============================================================
-- 2. PROGRAM DESCRIPTIONS AND AGENCIES
-- ============================================================

\echo ''
\echo '2. PROGRAM TITLES AND AGENCY ATTRIBUTION'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    BTRIM(c.cfda_number) AS program_code,
    r.raw_record->>'cfda_title' AS program_title,
    r.raw_record->>'awarding_agency_name'
        AS awarding_agency,
    r.raw_record->>'funding_agency_name'
        AS funding_agency,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger c
JOIN assistance.raw_award_transaction r
  ON r.load_batch_id = c.load_batch_id
 AND r.source_row_number = c.source_row_number
WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
  AND (
       (c.load_batch_id = 20
        AND c.action_date_fiscal_year = 2018)
    OR (c.load_batch_id = 21
        AND c.action_date_fiscal_year = 2019)
  )
GROUP BY
    fiscal_year,
    program_code,
    program_title,
    awarding_agency,
    funding_agency
ORDER BY program_code, fiscal_year, net_obligations DESC;


-- ============================================================
-- 3. RECIPIENT AND GEOGRAPHY EVIDENCE
-- ============================================================

\echo ''
\echo '3. RECIPIENT AND GEOGRAPHY PROFILE'

WITH recipient_evidence AS (
    SELECT
        BTRIM(c.cfda_number) AS program_code,
        r.raw_record->>'recipient_name'
            AS recipient_name,
        r.raw_record->>'recipient_state_code'
            AS recipient_state,
        r.raw_record->>
            'primary_place_of_performance_state_fips_code'
            AS performance_state_fips,
        c.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger c
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    program_code,
    recipient_name,
    recipient_state,
    performance_state_fips,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM recipient_evidence
GROUP BY
    program_code,
    recipient_name,
    recipient_state,
    performance_state_fips
ORDER BY net_obligations DESC;


-- ============================================================
-- 4. AWARD-IDENTIFIER INVENTORY
-- ============================================================

\echo ''
\echo '4. AWARD IDENTIFIERS AND FINANCIAL TOTALS'

WITH target AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), ''),
            NULLIF(
                BTRIM(
                    r.raw_record->>'assistance_award_unique_key'
                ),
                ''
            )
        ) AS award_identifier,
        c.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger c
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    program_code,
    COALESCE(award_identifier, '[MISSING]')
        AS award_identifier,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM target
GROUP BY fiscal_year, program_code, award_identifier
ORDER BY program_code, fiscal_year, net_obligations DESC;


-- ============================================================
-- 5. CROSS-PROGRAM AWARD MATCHES
-- ============================================================

\echo ''
\echo '5. CROSS-PROGRAM AWARD IDENTIFIER MATCHES'

WITH target AS (
    SELECT
        BTRIM(c.cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), ''),
            NULLIF(
                BTRIM(
                    r.raw_record->>'assistance_award_unique_key'
                ),
                ''
            )
        ) AS award_identifier,
        c.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger c
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    award_identifier,
    COUNT(DISTINCT program_code) AS distinct_programs,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS combined_net_obligations
FROM target
WHERE award_identifier IS NOT NULL
GROUP BY award_identifier
HAVING COUNT(DISTINCT program_code) > 1
ORDER BY combined_net_obligations DESC;


-- ============================================================
-- 6. EXISTING PROGRAM POLICIES
-- ============================================================

\echo ''
\echo '6. EXISTING POLICY MAPPINGS'

SELECT
    source_program_code,
    federal_inflow_program_policy_mapping_id,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    mapping_basis
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(source_program_code) IN ('93.773', '93.774')
ORDER BY source_program_code, valid_from_fiscal_year;


-- ============================================================
-- 7. AUTOMATED SOURCE-CONSERVATION ASSERTIONS
-- ============================================================

\echo ''
\echo '7. AUTOMATED SOURCE CONTROLS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_missing_raw bigint;
    v_historical_mappings bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT c.assistance_transaction_id),
        COALESCE(SUM(c.federal_action_obligation), 0),
        COUNT(*) FILTER (WHERE r.raw_record IS NULL)
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_missing_raw
    FROM analysis.v_certified_assistance_ledger c
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      );

    SELECT COUNT(*)
    INTO v_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_rows <> 36
       OR v_distinct <> 36
       OR ROUND(v_net, 2) <> 2489730308.00
       OR v_missing_raw <> 0
       OR v_historical_mappings <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210R FAIL: rows %, distinct %, net %, missing raw %, historical mappings %',
            v_rows,
            v_distinct,
            v_net,
            v_missing_raw,
            v_historical_mappings;
    END IF;

    RAISE NOTICE
        'ETL-210R PASS: 36 transactions, $2489730308.00 net, raw provenance complete, no historical program mappings';

END $$;

COMMIT;

\echo 'ETL-210R COMPLETE - READ ONLY'