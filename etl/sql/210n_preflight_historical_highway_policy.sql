-- ============================================================
-- WCFFBP ETL-210N
-- HISTORICAL HIGHWAY ASSISTANCE POLICY PREFLIGHT
-- AL 20.205, FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210N - HISTORICAL HIGHWAY POLICY PREFLIGHT'
\echo 'AL 20.205 - FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- 1. Preserve the full existing policy rationale.

\echo ''
\echo '1. ORIGINAL FY2020-FY2024 SOURCE POLICY'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id = 21;


\echo ''
\echo '2. ORIGINAL FY2020-FY2024 PROGRAM MAPPING'

SELECT
    federal_inflow_program_policy_mapping_id,
    federal_inflow_source_policy_id,
    source_system,
    source_program_code,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE federal_inflow_program_policy_mapping_id = 67;


-- 2. Inspect potentially overlapping transportation
-- accounting policies without presuming duplication.

\echo ''
\echo '3. TRANSPORTATION SOURCE POLICY INVENTORY'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    source_selection_basis
FROM reference.federal_inflow_source_policy
WHERE
    UPPER(COALESCE(inflow_family, '')) LIKE '%TRANSPORT%'
 OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%HIGHWAY%'
 OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%ROAD%'
 OR UPPER(COALESCE(preferred_source, '')) LIKE '%FHWA%'
 OR UPPER(COALESCE(preferred_source, '')) LIKE '%TRANSPORT%'
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year;


-- 3. Existing historical mappings and award overrides.

\echo ''
\echo '4. ALL AL 20.205 PROGRAM MAPPINGS'

SELECT
    federal_inflow_program_policy_mapping_id,
    federal_inflow_source_policy_id,
    source_system,
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE BTRIM(source_program_code) = '20.205'
ORDER BY valid_from_fiscal_year;


\echo ''
\echo '5. AL 20.205 AWARD CLASSIFICATION INVENTORY'

SELECT
    source_system,
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS classification_records
FROM reference.federal_inflow_award_classification
WHERE BTRIM(source_program_code) = '20.205'
GROUP BY
    source_system,
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY valid_from_fiscal_year;


-- 4. Historical transaction provenance and
-- Washington recipient evidence.

\echo ''
\echo '6. HISTORICAL HIGHWAY SOURCE EVIDENCE'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT c.assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(c.federal_action_obligation))::numeric, 2)
        AS gross_absolute_obligations,
    COUNT(*) FILTER (
        WHERE r.raw_record IS NULL
    ) AS missing_raw_links,
    COUNT(*) FILTER (
        WHERE r.raw_record->>'recipient_state_code' = 'WA'
    ) AS washington_recipient_rows,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(
            r.raw_record->>'recipient_state_code'
        ), '') IS DISTINCT FROM 'WA'
    ) AS non_wa_or_missing_recipient_rows,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(
            r.raw_record->>
            'primary_place_of_performance_state_fips_code'
        ), '') IS NOT NULL
    ) AS performance_state_field_present,
    COUNT(*) FILTER (
        WHERE c.federal_action_obligation < 0
    ) AS negative_transactions
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


-- 5. Automated preflight controls.
-- These certify source and policy consistency,
-- not independent nonoverlap with external accounts.

\echo ''
\echo '7. AUTOMATED PREFLIGHT CONTROLS'

DO $$
DECLARE
    v_original_source integer;
    v_original_mapping integer;
    v_historical_mappings integer;
    v_historical_rows bigint;
    v_historical_distinct bigint;
    v_historical_net numeric;
    v_missing_raw bigint;
    v_non_wa bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_original_source
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 21
      AND inflow_family = 'TRANSPORTATION_ASSISTANCE'
      AND inflow_subfamily = 'HIGHWAY_INFRASTRUCTURE'
      AND accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND ledger_treatment = 'INCLUDE'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    SELECT COUNT(*)
    INTO v_original_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 67
      AND federal_inflow_source_policy_id = 21
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '20.205'
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    SELECT COUNT(*)
    INTO v_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '20.205'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    SELECT
        COUNT(*),
        COUNT(DISTINCT c.assistance_transaction_id),
        COALESCE(SUM(c.federal_action_obligation), 0),
        COUNT(*) FILTER (
            WHERE r.raw_record IS NULL
        ),
        COUNT(*) FILTER (
            WHERE r.raw_record IS NULL
               OR NULLIF(BTRIM(
                   r.raw_record->>'recipient_state_code'
               ), '') IS DISTINCT FROM 'WA'
        )
    INTO
        v_historical_rows,
        v_historical_distinct,
        v_historical_net,
        v_missing_raw,
        v_non_wa
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

    IF v_original_source <> 1
       OR v_original_mapping <> 1
       OR v_historical_mappings <> 0
       OR v_historical_rows <> 4799
       OR v_historical_distinct <> 4799
       OR ROUND(v_historical_net, 2) <> 1451503112.03
       OR v_missing_raw <> 0
       OR v_non_wa <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210N FAIL: source %, mapping %, historical mappings %, rows %, distinct %, net %, missing raw %, non-WA %',
            v_original_source,
            v_original_mapping,
            v_historical_mappings,
            v_historical_rows,
            v_historical_distinct,
            v_historical_net,
            v_missing_raw,
            v_non_wa;
    END IF;

    RAISE NOTICE
        'ETL-210N PASS: original highway policy preserved; 4799 historical transactions; $1451503112.03 net; WA recipient evidence complete; no historical mapping';

END $$;

COMMIT;

\echo 'ETL-210N COMPLETE - READ ONLY'