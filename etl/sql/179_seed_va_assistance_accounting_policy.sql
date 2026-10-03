/*
================================================================================
ETL-179
Persist VA assistance accounting policy for ETL-174B reconciliation
================================================================================

Purpose
-------
Persist the evidence-based accounting treatment of USAspending VA assistance
(CFDA/Assistance Listing 64.*) for Washington, FY2020-FY2024.

Accounting principle
--------------------
VA GDX is the preferred accounting source for VA expenditures.

USAspending assistance is retained for transaction-level provenance,
COVID/DEFC identification, and reconciliation, but must not create a second
additive accounting path when the assistance expenditure is already represented
in VA GDX.

Resolution hierarchy remains:

    1. Award-specific classification
    2. Explicit program-policy mapping
    3. UNCLASSIFIED_REVIEW

This migration establishes explicit PROGRAM-level mappings for all 49 observed
CFDA 64.* programs in the certified Washington FY2020-FY2024 assistance
universe.

Evidence chain
--------------
ETL-174B-5N     VA assistance/GDX reconciliation profile
ETL-174B-5N-2   GDX category crosswalk
ETL-174B-5N-3   49-program evidence classification
ETL-174B-5N-4   final-review evidence package
ETL-174B-5N-5   official-source provenance review
ETL-174B-5N-5B  State Veterans Home/NHC transaction review

Important
---------
* No FY2025 accounting treatment is authorized here.
* COVID status is orthogonal to accounting disposition.
* EXCLUDE_DUPLICATE does NOT erase COVID provenance.
* 64.030 is a face-amount/coverage measure, not expenditure.
* Programs without sufficient containment evidence remain
  WITHHOLD_UNRESOLVED.
================================================================================
*/

BEGIN;

-- ============================================================================
-- 0. PRE-WRITE HARD CONTROLS
-- ============================================================================

DO $$
DECLARE
    v_program_count integer;
    v_transaction_count bigint;
    v_total numeric;
    v_covid numeric;
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
        )
    INTO
        v_program_count,
        v_transaction_count,
        v_total,
        v_covid
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%';

    IF v_program_count <> 49 THEN
        RAISE EXCEPTION
            'ETL-179 PRECHECK FAILED: expected 49 VA programs, found %',
            v_program_count;
    END IF;

    IF v_transaction_count <> 59160 THEN
        RAISE EXCEPTION
            'ETL-179 PRECHECK FAILED: expected 59160 VA transactions, found %',
            v_transaction_count;
    END IF;

    IF ABS(v_total - 23707643332.28::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-179 PRECHECK FAILED: VA assistance control expected %, found %',
            23707643332.28,
            v_total;
    END IF;

    IF ABS(v_covid - 306522432.91::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-179 PRECHECK FAILED: VA COVID control expected %, found %',
            306522432.91,
            v_covid;
    END IF;

    RAISE NOTICE
        'ETL-179 PRECHECK PASS: % programs; % transactions; total=%; COVID=%',
        v_program_count,
        v_transaction_count,
        v_total,
        v_covid;
END
$$;


-- ============================================================================
-- 1. CREATE VA ASSISTANCE SOURCE POLICIES
--
-- These policies are intentionally distinct from the existing FY2024
-- VA procurement reconciliation policy.
-- ============================================================================

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
VALUES
(
    'VETERANS_AFFAIRS',
    'VA_GDX_ASSISTANCE_OVERLAP',
    'VA expenditures',
    'VA_GDX',
    'VA_GDX',
    ARRAY['USASPENDING_ASSISTANCE']::text[],
    'EXCLUDE_DUPLICATE',
    'VA GDX is the preferred accounting source. USAspending assistance '
        || 'programs with demonstrated containment in GDX are retained for '
        || 'provenance and reconciliation but excluded as a second additive '
        || 'federal inflow.',
    'ANALYSIS-174B-5N-v1',
    2020,
    2024
),
(
    'VETERANS_AFFAIRS',
    'VA_ASSISTANCE_UNRESOLVED',
    'VA assistance obligations',
    'REVIEW_REQUIRED',
    'USASPENDING_ASSISTANCE',
    ARRAY['VA_GDX']::text[],
    'REVIEW_REQUIRED',
    'Program relationship to VA GDX has not been demonstrated strongly enough '
        || 'to authorize either additive inclusion or duplicate exclusion.',
    'ANALYSIS-174B-5N-v1',
    2020,
    2024
),
(
    'VETERANS_AFFAIRS',
    'VA_NONEXPENDITURE_REFERENCE',
    'Reference or contingent measure',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'SEPARATE_CONTINGENT_MEASURE',
    'Program measure is not a current federal expenditure and is retained only '
        || 'as a reference measure.',
    'ANALYSIS-174B-5N-v1',
    2020,
    2024
);


-- ============================================================================
-- 2. ASSERT SOURCE POLICIES EXIST EXACTLY ONCE
-- ============================================================================

DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-174B-5N-v1'
      AND inflow_family = 'VETERANS_AFFAIRS'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_count <> 3 THEN
        RAISE EXCEPTION
            'ETL-179 POLICY ASSERTION FAILED: expected 3 policies, found %',
            v_count;
    END IF;
END
$$;


-- ============================================================================
-- 3. PROGRAM DECISION TABLE
--
-- disposition:
--   EXCLUDE_DUPLICATE
--   WITHHOLD_UNRESOLVED
--   REFERENCE_ONLY
--
-- Class-A programs from 5N-3 are direct demonstrated GDX overlaps.
--
-- Additional Class-B programs resolved through 5N-4/5N-5:
--   64.015  State Nursing Home Care
--   64.029  Purchase Care
--   64.031  Government Life Insurance payments
--   64.035  Veterans Transportation
--   64.100  Automobiles/adaptive equipment
--   64.106  Specially Adapted Housing
--   64.116  Veteran Readiness and Employment
--   64.130  Veteran Rapid Retraining Assistance
--
-- 64.030 is REFERENCE_ONLY because the observed measure is face amount of
-- new life-insurance coverage rather than expenditure.
--
-- Remaining Class-B programs are conservatively withheld.
--
-- Class-C zero-dollar loan programs are REFERENCE_ONLY.
-- ============================================================================

CREATE TEMP TABLE etl179_va_program_decision (
    source_program_code text PRIMARY KEY,
    resolved_accounting_disposition text NOT NULL,
    policy_subfamily text NOT NULL,
    decision_basis text NOT NULL
) ON COMMIT DROP;


-- --------------------------------------------------------------------------
-- 3A. Demonstrated GDX overlap: Class A
-- --------------------------------------------------------------------------

INSERT INTO etl179_va_program_decision
VALUES

-- Compensation / pension
('64.104', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX COMPENSATION_PENSION overlap'),
('64.105', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX COMPENSATION_PENSION overlap'),
('64.109', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX COMPENSATION_PENSION overlap'),
('64.110', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX COMPENSATION_PENSION overlap'),

-- Construction
('64.005', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX CONSTRUCTION overlap'),

-- Education / VR&E
('64.028', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX EDUCATION_VRE overlap'),
('64.032', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX EDUCATION_VRE overlap'),
('64.117', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX EDUCATION_VRE overlap'),
('64.120', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX EDUCATION_VRE overlap'),
('64.124', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX EDUCATION_VRE overlap'),

-- Medical care
('64.011', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.012', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.013', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.039', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.040', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.041', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.042', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.043', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.044', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.045', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.046', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.047', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.048', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.049', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),
('64.050', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEDICAL_CARE overlap'),

-- Memorial benefits
('64.101', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEMORIAL_BENEFITS overlap'),
('64.203', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEMORIAL_BENEFITS overlap'),
('64.206', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-3: direct GDX MEMORIAL_BENEFITS overlap');


-- --------------------------------------------------------------------------
-- 3B. Class-B programs resolved by 5N-4 / 5N-5
-- --------------------------------------------------------------------------

INSERT INTO etl179_va_program_decision
VALUES
('64.015', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-5B: State Veterans Home NHC; VHA State Home care / GDX Medical Care overlap; COVID provenance retained independently'),

('64.029', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-4/5N-5: Community Care payments; GDX Medical Care overlap'),

('64.031', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-4/5N-5: Government Life Insurance payments; GDX insurance expenditure overlap'),

('64.035', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-4/5N-5: transportation in connection with provision of VA medical care'),

('64.100', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-4/5N-5: automobile/adaptive-equipment expenditure represented in GDX'),

('64.106', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-4/5N-5: specially adapted housing expenditure represented in GDX'),

('64.116', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-4/5N-5: Veteran Readiness and Employment; GDX EDUCATION_VRE overlap'),

('64.130', 'EXCLUDE_DUPLICATE', 'VA_GDX_ASSISTANCE_OVERLAP',
 'ETL-174B-5N-4/5N-5: Veteran Rapid Retraining Assistance; GDX EDUCATION_VRE overlap'),

('64.030', 'REFERENCE_ONLY', 'VA_NONEXPENDITURE_REFERENCE',
 'ETL-174B-5N-4: face amount of new life-insurance policies issued; coverage measure rather than expenditure');


-- --------------------------------------------------------------------------
-- 3C. Class-B programs still unresolved
-- --------------------------------------------------------------------------

INSERT INTO etl179_va_program_decision
VALUES
('64.014', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'State Domiciliary Care; containment in GDX not demonstrated sufficiently'),

('64.024', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'Homeless Providers Grant and Per Diem; GDX containment not demonstrated sufficiently'),

('64.033', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'Supportive Services for Veteran Families; GDX containment not demonstrated sufficiently'),

('64.034', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'Adaptive sports grants; GDX containment not demonstrated sufficiently'),

('64.037', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'Paralympics allowance; GDX containment not demonstrated sufficiently'),

('64.053', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'State Veterans Home nurse hiring/retention; GDX containment not demonstrated sufficiently'),

('64.055', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'Fox suicide-prevention grants; GDX containment not demonstrated sufficiently'),

('64.056', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'Legal-services grants; GDX containment not demonstrated sufficiently'),

('64.127', 'WITHHOLD_UNRESOLVED', 'VA_ASSISTANCE_UNRESOLVED',
 'Spina bifida child allowance; GDX containment not demonstrated sufficiently');


-- --------------------------------------------------------------------------
-- 3D. Class-C zero-dollar credit/loan programs
-- --------------------------------------------------------------------------

INSERT INTO etl179_va_program_decision
VALUES
('64.114', 'REFERENCE_ONLY', 'VA_NONEXPENDITURE_REFERENCE',
 'ETL-174B-5N-3: housing guaranteed/insured loan program; observed FY2020-FY2024 obligation control is zero'),

('64.118', 'REFERENCE_ONLY', 'VA_NONEXPENDITURE_REFERENCE',
 'ETL-174B-5N-3: housing direct-loan program; observed FY2020-FY2024 obligation control is zero'),

('64.126', 'REFERENCE_ONLY', 'VA_NONEXPENDITURE_REFERENCE',
 'ETL-174B-5N-3: Native American Veteran Direct Loan; observed FY2020-FY2024 obligation control is zero');


-- ============================================================================
-- 4. HARD ASSERTION: EXACTLY 49 PROGRAM DECISIONS
-- ============================================================================

DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM etl179_va_program_decision;

    IF v_count <> 49 THEN
        RAISE EXCEPTION
            'ETL-179 DECISION TABLE FAILED: expected 49 programs, found %',
            v_count;
    END IF;
END
$$;


-- ============================================================================
-- 5. ASSERT DECISION TABLE EXACTLY COVERS OBSERVED FY2020-FY2024 VA PROGRAMS
-- ============================================================================

DO $$
DECLARE
    v_missing integer;
    v_extra integer;
BEGIN
    SELECT COUNT(*)
    INTO v_missing
    FROM (
        SELECT DISTINCT cfda_number
        FROM analysis.v_certified_assistance_ledger
        WHERE reference_state_abbreviation = 'WA'
          AND action_date_fiscal_year BETWEEN 2020 AND 2024
          AND cfda_number LIKE '64.%'

        EXCEPT

        SELECT source_program_code
        FROM etl179_va_program_decision
    ) x;

    SELECT COUNT(*)
    INTO v_extra
    FROM (
        SELECT source_program_code
        FROM etl179_va_program_decision

        EXCEPT

        SELECT DISTINCT cfda_number
        FROM analysis.v_certified_assistance_ledger
        WHERE reference_state_abbreviation = 'WA'
          AND action_date_fiscal_year BETWEEN 2020 AND 2024
          AND cfda_number LIKE '64.%'
    ) x;

    IF v_missing <> 0 OR v_extra <> 0 THEN
        RAISE EXCEPTION
            'ETL-179 PROGRAM COVERAGE FAILED: missing=%, extra=%',
            v_missing,
            v_extra;
    END IF;
END
$$;


-- ============================================================================
-- 6. PERSIST PROGRAM -> POLICY MAPPINGS
-- ============================================================================

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
    d.source_program_code,
    p.federal_inflow_source_policy_id,
    d.resolved_accounting_disposition,
    d.decision_basis,
    'ANALYSIS-174B-5N-v1',
    2020,
    2024
FROM etl179_va_program_decision d
JOIN reference.federal_inflow_source_policy p
  ON p.inflow_family = 'VETERANS_AFFAIRS'
 AND p.inflow_subfamily = d.policy_subfamily
 AND p.methodology_version = 'ANALYSIS-174B-5N-v1'
 AND p.valid_from_fiscal_year = 2020
 AND p.valid_through_fiscal_year = 2024
ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)
DO UPDATE
SET
    federal_inflow_source_policy_id =
        EXCLUDED.federal_inflow_source_policy_id,
    resolved_accounting_disposition =
        EXCLUDED.resolved_accounting_disposition,
    mapping_basis =
        EXCLUDED.mapping_basis,
    valid_from_fiscal_year =
        EXCLUDED.valid_from_fiscal_year,
    valid_through_fiscal_year =
        EXCLUDED.valid_through_fiscal_year,
    updated_at = CURRENT_TIMESTAMP;


-- ============================================================================
-- 7. POST-WRITE MAPPING ASSERTIONS
-- ============================================================================

DO $$
DECLARE
    v_count integer;
    v_bad_year integer;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-174B-5N-v1';

    IF v_count <> 49 THEN
        RAISE EXCEPTION
            'ETL-179 POSTCHECK FAILED: expected 49 persisted mappings, found %',
            v_count;
    END IF;

    SELECT COUNT(*)
    INTO v_bad_year
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-174B-5N-v1'
      AND (
          valid_from_fiscal_year <> 2020
          OR valid_through_fiscal_year <> 2024
      );

    IF v_bad_year <> 0 THEN
        RAISE EXCEPTION
            'ETL-179 POSTCHECK FAILED: % mappings have invalid FY bounds',
            v_bad_year;
    END IF;
END
$$;


-- ============================================================================
-- 8. ACCOUNTING BRIDGE UNDER NEW PROGRAM MAPPINGS
--
-- Award-specific classifications continue to override program mappings.
-- ============================================================================

CREATE TEMP TABLE etl179_resolved_va_transactions
ON COMMIT DROP
AS
WITH base AS (
    SELECT
        l.assistance_transaction_id,
        l.action_date_fiscal_year,
        l.cfda_number,
        l.award_id_fain,
        l.federal_action_obligation,
        l.is_covid
    FROM analysis.v_certified_assistance_ledger l
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number LIKE '64.%'
),
award_resolution AS (
    SELECT
        b.*,
        a.accounting_disposition AS award_disposition
    FROM base b
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = b.cfda_number
     AND a.source_award_identifier = b.award_id_fain
     AND b.action_date_fiscal_year
         BETWEEN COALESCE(a.valid_from_fiscal_year, b.action_date_fiscal_year)
             AND COALESCE(a.valid_through_fiscal_year, b.action_date_fiscal_year)
),
program_resolution AS (
    SELECT
        a.*,
        m.resolved_accounting_disposition AS program_disposition
    FROM award_resolution a
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = a.cfda_number
     AND m.methodology_version = 'ANALYSIS-174B-5N-v1'
     AND a.action_date_fiscal_year
         BETWEEN m.valid_from_fiscal_year
             AND m.valid_through_fiscal_year
)
SELECT
    *,
    COALESCE(
        award_disposition,
        program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS resolved_accounting_disposition
FROM program_resolution;


-- ============================================================================
-- 9. HARD ASSERTION: NO VA TRANSACTION REMAINS UNCLASSIFIED
-- ============================================================================

DO $$
DECLARE
    v_unclassified bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_unclassified
    FROM etl179_resolved_va_transactions
    WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW';

    IF v_unclassified <> 0 THEN
        RAISE EXCEPTION
            'ETL-179 FAILED: % VA transactions remain unclassified',
            v_unclassified;
    END IF;
END
$$;


-- ============================================================================
-- 10. HARD CONTROL: ACCOUNTING BRIDGE MUST CLOSE EXACTLY
-- ============================================================================

DO $$
DECLARE
    v_total numeric;
    v_difference numeric;
BEGIN
    SELECT
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_total
    FROM etl179_resolved_va_transactions;

    v_difference := v_total - 23707643332.28::numeric;

    IF ABS(v_difference) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-179 BRIDGE FAILED: expected %, found %, difference %',
            23707643332.28,
            v_total,
            v_difference;
    END IF;
END
$$;


-- ============================================================================
-- 11. REPORT PERSISTED VA ACCOUNTING BRIDGE
-- ============================================================================

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl179_resolved_va_transactions
GROUP BY resolved_accounting_disposition
ORDER BY resolved_accounting_disposition;


-- ============================================================================
-- 12. REPORT ANNUAL VA ACCOUNTING BRIDGE
-- ============================================================================

SELECT
    action_date_fiscal_year AS fiscal_year,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl179_resolved_va_transactions
GROUP BY
    action_date_fiscal_year,
    resolved_accounting_disposition
ORDER BY
    action_date_fiscal_year,
    resolved_accounting_disposition;


-- ============================================================================
-- 13. EXPLICIT 64.015 CONTROL
-- ============================================================================

SELECT
    action_date_fiscal_year AS fiscal_year,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl179_resolved_va_transactions
WHERE cfda_number = '64.015'
GROUP BY
    action_date_fiscal_year,
    resolved_accounting_disposition
ORDER BY
    action_date_fiscal_year;


-- ============================================================================
-- 14. ASSERT 64.015 CONTROL AND DISPOSITION
-- ============================================================================

DO $$
DECLARE
    v_total numeric;
    v_covid numeric;
    v_bad_disposition bigint;
BEGIN
    SELECT
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
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition <> 'EXCLUDE_DUPLICATE'
        )
    INTO
        v_total,
        v_covid,
        v_bad_disposition
    FROM etl179_resolved_va_transactions
    WHERE cfda_number = '64.015';

    IF ABS(v_total - 254229609.16::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-179 64.015 CONTROL FAILED: expected %, found %',
            254229609.16,
            v_total;
    END IF;

    IF ABS(v_covid - 241859039.16::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-179 64.015 COVID CONTROL FAILED: expected %, found %',
            241859039.16,
            v_covid;
    END IF;

    IF v_bad_disposition <> 0 THEN
        RAISE EXCEPTION
            'ETL-179 64.015 DISPOSITION FAILED: % transactions not EXCLUDE_DUPLICATE',
            v_bad_disposition;
    END IF;
END
$$;


-- ============================================================================
-- 15. FY2025 GUARDRAIL
--
-- No ETL-179 program mapping may authorize FY2025 treatment.
-- ============================================================================

DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-174B-5N-v1'
      AND valid_through_fiscal_year >= 2025;

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-179 FY2025 GUARDRAIL FAILED: % mappings extend into FY2025',
            v_count;
    END IF;
END
$$;


-- ============================================================================
-- 16. COMPLETION MARKER
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-179 PASS - VA assistance accounting policy persisted; '
        '49 programs resolved; FY2020-FY2024 only; '
        'COVID provenance preserved independently';
END
$$;

COMMIT;