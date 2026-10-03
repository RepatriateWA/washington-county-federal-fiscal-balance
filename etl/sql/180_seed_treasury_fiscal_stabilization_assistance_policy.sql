/*
================================================================================
MIGRATION 180
ETL-174B-5Q
Persist Treasury Fiscal Stabilization Assistance Accounting Policy
================================================================================

Purpose
-------
Persist accounting policy for three Treasury assistance programs reviewed in
ETL-174B-5Q:

    21.019  Coronavirus Relief Fund
    21.023  Emergency Rental Assistance Program
    21.027  Coronavirus State and Local Fiscal Recovery Funds

Accounting conclusion
---------------------
All three programs are classified INCLUDE_ADDITIVE for FY2020-FY2024.

Accounting measure
------------------
USAspending net federal_action_obligation.

Important
---------
COVID / extraordinary status is independent provenance. It does not determine
the accounting disposition.

These three programs remain COVID-tagged in the certified assistance ledger,
allowing:

    COVID-inclusive ledger -> includes the additive obligations
    COVID-excluded ledger  -> excludes those same obligations

Scope
-----
This migration applies ONLY to 21.019, 21.023, and 21.027.

It does NOT establish a blanket accounting rule for Treasury assistance or
for Assistance Listing prefix 21.*.

Expected ETL-174B-5Q control
----------------------------
Programs       : 3
Transactions   : 660
Net obligations: 12,561,260,982.36
COVID amount   : 12,561,260,982.36
IIJA amount    : 0.00

Methodology version
-------------------
ANALYSIS-174B-5Q-v1
================================================================================
*/

BEGIN;


-- ================================================================================================
-- 1. HARD SOURCE PRECHECK
-- ================================================================================================

DO $$
DECLARE
    v_program_count       bigint;
    v_transaction_count   bigint;
    v_total               numeric;
    v_covid               numeric;
    v_iija                numeric;
BEGIN
    SELECT
        COUNT(DISTINCT cfda_number),
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(
                CASE
                    WHEN is_covid
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ),
        COALESCE(
            SUM(
                CASE
                    WHEN is_iija
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        )
    INTO
        v_program_count,
        v_transaction_count,
        v_total,
        v_covid,
        v_iija
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number IN (
          '21.019',
          '21.023',
          '21.027'
      );

    IF v_program_count <> 3 THEN
        RAISE EXCEPTION
            'ETL-180 PRECHECK FAILED: expected 3 programs; found %',
            v_program_count;
    END IF;

    IF v_transaction_count <> 660 THEN
        RAISE EXCEPTION
            'ETL-180 PRECHECK FAILED: expected 660 transactions; found %',
            v_transaction_count;
    END IF;

    IF ABS(v_total - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-180 PRECHECK FAILED: expected total 12561260982.36; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-180 PRECHECK FAILED: expected COVID total 12561260982.36; found %',
            v_covid;
    END IF;

    IF ABS(v_iija - 0.00::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-180 PRECHECK FAILED: expected IIJA total 0.00; found %',
            v_iija;
    END IF;

    RAISE NOTICE
        'ETL-180 PRECHECK PASS: programs=% transactions=% total=% COVID=% IIJA=%',
        v_program_count,
        v_transaction_count,
        v_total,
        v_covid,
        v_iija;
END
$$;


-- ================================================================================================
-- 2. GUARD AGAINST PREEXISTING 5Q POLICY
--
-- federal_inflow_source_policy does NOT have a composite uniqueness constraint.
-- Therefore we explicitly test before inserting instead of using ON CONFLICT.
-- ================================================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE inflow_family = 'TREASURY_FISCAL_STABILIZATION'
          AND inflow_subfamily = 'STATE_LOCAL_FISCAL_STABILIZATION'
          AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
          AND methodology_version = 'ANALYSIS-174B-5Q-v1'
    ) THEN
        RAISE EXCEPTION
            'ETL-180 ABORTED: ANALYSIS-174B-5Q-v1 source policy already exists';
    END IF;
END
$$;


-- ================================================================================================
-- 3. INSERT SOURCE POLICY
-- ================================================================================================

INSERT INTO reference.federal_inflow_source_policy (
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
)
VALUES (
    'TREASURY_FISCAL_STABILIZATION',
    'STATE_LOCAL_FISCAL_STABILIZATION',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'ETL-174B-5Q established that Assistance Listings 21.019, 21.023, and 21.027 represent direct federal Treasury assistance obligations to Washington state, local, and tribal recipients. No existing WCFFBP authoritative accounting source, program-policy mapping, award-specific classification, or source policy was identified as an overlapping accounting path. Net federal_action_obligation is retained so subsequent deobligations and adjustments remain part of the accounting measure. COVID and extraordinary status are preserved independently as funding provenance and do not determine accounting disposition. This policy applies only to the three explicitly mapped programs and is not a blanket policy for Treasury or Assistance Listing prefix 21.*.',
    'ANALYSIS-174B-5Q-v1',
    2020,
    2024
);


-- ================================================================================================
-- 4. CAPTURE POLICY ID
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl180_policy;

CREATE TEMP TABLE etl180_policy AS
SELECT
    federal_inflow_source_policy_id
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'TREASURY_FISCAL_STABILIZATION'
  AND inflow_subfamily = 'STATE_LOCAL_FISCAL_STABILIZATION'
  AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
  AND methodology_version = 'ANALYSIS-174B-5Q-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM etl180_policy;

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-180 POLICY-ID CHECK FAILED: expected exactly 1 policy; found %',
            v_count;
    END IF;
END
$$;


-- ================================================================================================
-- 5. PROGRAM CLASSIFICATION RECORDS
--
-- These describe program semantics / overlap risk independently of the
-- accounting mapping.
-- ================================================================================================

INSERT INTO reference.federal_inflow_program_classification (
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
VALUES
(
    'USASPENDING_ASSISTANCE',
    '21.019',
    'CORONAVIRUS RELIEF FUND',
    'TREASURY_FISCAL_STABILIZATION',
    'STATE_LOCAL_FISCAL_STABILIZATION',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5Q review: direct Treasury assistance to state, local, and tribal governments; no existing WCFFBP accounting path identified as duplicative. Net obligations retained, including later deobligations.',
    'ANALYSIS-174B-5Q-v1',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '21.023',
    'EMERGENCY RENTAL ASSISTANCE PROGRAM',
    'TREASURY_FISCAL_STABILIZATION',
    'STATE_LOCAL_FISCAL_STABILIZATION',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5Q review: direct Treasury assistance for rental and housing-stability purposes; no existing WCFFBP accounting path identified as duplicative. Net obligations retained because deobligations are material.',
    'ANALYSIS-174B-5Q-v1',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '21.027',
    'CORONAVIRUS STATE AND LOCAL FISCAL RECOVERY FUNDS',
    'TREASURY_FISCAL_STABILIZATION',
    'STATE_LOCAL_FISCAL_STABILIZATION',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5Q review: direct Treasury assistance to state, local, and tribal governments; no existing WCFFBP accounting path identified as duplicative. Net obligations retained, including later adjustments.',
    'ANALYSIS-174B-5Q-v1',
    2020,
    2024
)
ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)
DO NOTHING;


-- ================================================================================================
-- 6. PROGRAM -> POLICY MAPPINGS
-- ================================================================================================

INSERT INTO reference.federal_inflow_program_policy_mapping (
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    'USASPENDING_ASSISTANCE',
    p.source_program_code,
    policy.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    p.mapping_basis,
    'ANALYSIS-174B-5Q-v1',
    2020,
    2024
FROM (
    VALUES
        (
            '21.019',
            'ETL-174B-5Q: Coronavirus Relief Fund is additive Treasury fiscal-stabilization assistance. COVID remains independent funding provenance.'
        ),
        (
            '21.023',
            'ETL-174B-5Q: Emergency Rental Assistance is additive Treasury assistance. Net federal obligations are used because subsequent deobligations are material. COVID remains independent funding provenance.'
        ),
        (
            '21.027',
            'ETL-174B-5Q: Coronavirus State and Local Fiscal Recovery Funds are additive Treasury fiscal-stabilization assistance. COVID remains independent funding provenance.'
        )
) AS p (
    source_program_code,
    mapping_basis
)
CROSS JOIN etl180_policy policy
ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)
DO NOTHING;


-- ================================================================================================
-- 7. VERIFY PERSISTED CLASSIFICATIONS
-- ================================================================================================

DO $$
DECLARE
    v_program_classifications bigint;
    v_mappings                bigint;
    v_include_mappings        bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_program_classifications
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
          '21.019',
          '21.023',
          '21.027'
      )
      AND methodology_version = 'ANALYSIS-174B-5Q-v1';

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
        )
    INTO
        v_mappings,
        v_include_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
          '21.019',
          '21.023',
          '21.027'
      )
      AND methodology_version = 'ANALYSIS-174B-5Q-v1';

    IF v_program_classifications <> 3 THEN
        RAISE EXCEPTION
            'ETL-180 VERIFICATION FAILED: expected 3 program classifications; found %',
            v_program_classifications;
    END IF;

    IF v_mappings <> 3 THEN
        RAISE EXCEPTION
            'ETL-180 VERIFICATION FAILED: expected 3 program mappings; found %',
            v_mappings;
    END IF;

    IF v_include_mappings <> 3 THEN
        RAISE EXCEPTION
            'ETL-180 VERIFICATION FAILED: expected 3 INCLUDE_ADDITIVE mappings; found %',
            v_include_mappings;
    END IF;
END
$$;


-- ================================================================================================
-- 8. VERIFY MAPPED SOURCE DOLLARS
-- ================================================================================================

DO $$
DECLARE
    v_transaction_count bigint;
    v_total             numeric;
    v_covid             numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(l.federal_action_obligation), 0),
        COALESCE(
            SUM(
                CASE
                    WHEN l.is_covid
                    THEN l.federal_action_obligation
                    ELSE 0
                END
            ),
            0
        )
    INTO
        v_transaction_count,
        v_total,
        v_covid
    FROM analysis.v_certified_assistance_ledger l
    JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = l.cfda_number
     AND m.methodology_version = 'ANALYSIS-174B-5Q-v1'
     AND l.action_date_fiscal_year
         BETWEEN m.valid_from_fiscal_year
             AND m.valid_through_fiscal_year
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number IN (
          '21.019',
          '21.023',
          '21.027'
      )
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE';

    IF v_transaction_count <> 660 THEN
        RAISE EXCEPTION
            'ETL-180 MAPPED-DOLLAR CHECK FAILED: expected 660 transactions; found %',
            v_transaction_count;
    END IF;

    IF ABS(v_total - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-180 MAPPED-DOLLAR CHECK FAILED: expected 12561260982.36; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-180 COVID CHECK FAILED: expected 12561260982.36; found %',
            v_covid;
    END IF;

    RAISE NOTICE
        'ETL-180 MAPPED-DOLLAR PASS: transactions=% additive=% COVID=%',
        v_transaction_count,
        v_total,
        v_covid;
END
$$;


-- ================================================================================================
-- 9. SCOPE GUARD
--
-- Migration 180 must not create mappings for any other Treasury program.
-- ================================================================================================

DO $$
DECLARE
    v_other_programs bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_other_programs
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-174B-5Q-v1'
      AND source_program_code NOT IN (
          '21.019',
          '21.023',
          '21.027'
      );

    IF v_other_programs <> 0 THEN
        RAISE EXCEPTION
            'ETL-180 SCOPE GUARD FAILED: methodology mapped % unexpected programs',
            v_other_programs;
    END IF;
END
$$;


-- ================================================================================================
-- 10. HUMAN-READABLE RESULT
-- ================================================================================================

SELECT
    m.source_program_code,
    c.source_program_title,
    m.resolved_accounting_disposition,
    p.accounting_measure,
    p.ledger_treatment,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
LEFT JOIN reference.federal_inflow_program_classification c
  ON c.source_system = m.source_system
 AND c.source_program_code = m.source_program_code
 AND c.methodology_version = m.methodology_version
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.methodology_version = 'ANALYSIS-174B-5Q-v1'
ORDER BY m.source_program_code;


DO $$
BEGIN
    RAISE NOTICE
        'ETL-180 PASS - Treasury 21.019/21.023/21.027 persisted as INCLUDE_ADDITIVE; FY2020-FY2024 only; COVID provenance preserved independently';
END
$$;


COMMIT;