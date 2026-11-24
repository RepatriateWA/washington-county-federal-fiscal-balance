-- ============================================================
-- WCFFBP ETL-211G
-- HISTORICAL MEDICARE OVERLAP POLICY PREFLIGHT
-- FY2018-FY2019 | AL 93.773 and 93.774
-- READ ONLY - NO DATABASE OR LEDGER WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211G - HISTORICAL MEDICARE POLICY PREFLIGHT'
\echo 'READ ONLY - NO DATABASE OR LEDGER WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- 1. Historical transaction controls

\echo ''
\echo '1. HISTORICAL SOURCE CONTROLS'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
        r.raw_record
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
    COUNT(*) FILTER (WHERE raw_record IS NULL)
        AS missing_raw_records,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM historical
GROUP BY fiscal_year, program_code
ORDER BY fiscal_year, program_code;

-- 2. Existing program policy mappings

\echo ''
\echo '2. EXISTING PROGRAM POLICY MAPPINGS'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    federal_inflow_source_policy_id,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(source_program_code) IN ('93.773', '93.774')
ORDER BY source_program_code, valid_from_fiscal_year;

-- 3. Existing preferred source policies

\echo ''
\echo '3. PREFERRED SOURCE POLICY'

SELECT
    inflow_subfamily,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'MEDICARE'
  AND (
      'USASPENDING_ASSISTANCE_93.773' = ANY(overlapping_sources)
      OR
      'USASPENDING_ASSISTANCE_93.774' = ANY(overlapping_sources)
  )
ORDER BY inflow_subfamily, valid_from_fiscal_year;

-- 4. Historical award-level overrides

\echo ''
\echo '4. HISTORICAL AWARD CLASSIFICATION CONFLICTS'

SELECT
    a.source_program_code,
    a.accounting_disposition,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year,
    COUNT(*) AS classification_rows
FROM reference.federal_inflow_award_classification a
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND a.source_program_code IN ('93.773', '93.774')
  AND COALESCE(a.valid_from_fiscal_year, -9999) <= 2019
  AND COALESCE(a.valid_through_fiscal_year, 9999) >= 2018
GROUP BY
    a.source_program_code,
    a.accounting_disposition,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year;

-- 5. CMS ledger authorization remains separate

\echo ''
\echo '5. CMS STATEWIDE CORE AUTHORIZATION'

SELECT
    calendar_year,
    state_id,
    ledger_status,
    timing_basis_status,
    combined_period_status,
    partc_year_completeness,
    partd_coverage_status,
    ROUND(core_medicare_sum_dollars, 2)
        AS core_medicare_sum_dollars
FROM cms.medicare_core_state_year
WHERE calendar_year IN (2018, 2019)
  AND state_id = 48
ORDER BY calendar_year;

-- 6. Fail-closed source and policy assertions

\echo ''
\echo '6. AUTOMATED PREFLIGHT ASSERTIONS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_missing_raw bigint;
    v_net numeric;
    v_original_mappings bigint;
    v_bad_mappings bigint;
    v_historical_mappings bigint;
    v_award_conflicts bigint;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT c.assistance_transaction_id),
        COUNT(*) FILTER (WHERE r.raw_record IS NULL),
        COALESCE(SUM(c.federal_action_obligation), 0)
    INTO
        v_rows,
        v_distinct,
        v_missing_raw,
        v_net
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

    IF v_rows <> 36
       OR v_distinct <> 36
       OR v_missing_raw <> 0
       OR ROUND(v_net, 2) <> 2489730308.00
    THEN
        RAISE EXCEPTION
          'ETL-211G source FAIL: rows %, distinct %, missing raw %, net %',
          v_rows, v_distinct, v_missing_raw, v_net;
    END IF;

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition
                  IS DISTINCT FROM 'EXCLUDE_DUPLICATE'
               OR valid_from_fiscal_year IS DISTINCT FROM 2020
               OR valid_through_fiscal_year IS DISTINCT FROM 2024
               OR federal_inflow_source_policy_id IS NULL
        ),
        COUNT(*) FILTER (
            WHERE COALESCE(valid_from_fiscal_year, -9999) <= 2019
              AND COALESCE(valid_through_fiscal_year, 9999) >= 2018
        )
    INTO
        v_original_mappings,
        v_bad_mappings,
        v_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) IN ('93.773', '93.774');

    IF v_original_mappings <> 2
       OR v_bad_mappings <> 0
       OR v_historical_mappings <> 0
    THEN
        RAISE EXCEPTION
          'ETL-211G mapping FAIL: originals %, bad %, historical %',
          v_original_mappings,
          v_bad_mappings,
          v_historical_mappings;
    END IF;

    SELECT COUNT(*)
    INTO v_award_conflicts
    FROM reference.federal_inflow_award_classification a
    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code IN ('93.773', '93.774')
      AND COALESCE(a.valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(a.valid_through_fiscal_year, 9999) >= 2018;

    IF v_award_conflicts <> 0 THEN
        RAISE EXCEPTION
          'ETL-211G award classification conflicts: %',
          v_award_conflicts;
    END IF;

    RAISE NOTICE
      'ETL-211G PASS: 36 transactions, $2489730308.00, original mappings preserved, zero historical mappings or award conflicts';
END $$;

COMMIT;

\echo ''
\echo 'ETL-211G COMPLETE - READ ONLY'