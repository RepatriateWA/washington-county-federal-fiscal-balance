/*
================================================================================
ETL-182
SEED TRANSPORTATION ASSISTANCE ACCOUNTING POLICY
================================================================================

Purpose
-------
Persist the accounting treatment established by ETL-174B-5V and refined by
ETL-174B-5V-1 for six major Washington transportation assistance programs.

Accounting conclusion
---------------------
These programs represent federal transportation assistance flowing to
Washington recipients and are not represented by another authoritative
WCFFBP ledger stream.

Classification is based on the Assistance Listing/program and substantive
economic purpose, NOT solely on funding_agency_name.

Important scope refinement
--------------------------
ETL-174B-5V initially profiled 9,606 transactions totaling
$12,204,425,068.99 where funding_agency_name = 'Department of Transportation'.

ETL-174B-5V-1 established that Assistance Listing 20.205 also contains
217 Washington transactions totaling $99,150,613.43 administered through
the Department of the Interior.

Those transactions are substantively Tribal Transportation Program,
highway construction, transportation planning, and related transportation
assistance. They therefore remain part of the TRANSPORTATION_ASSISTANCE
accounting family.

Raw funding-agency provenance is preserved unchanged.

Family:
    TRANSPORTATION_ASSISTANCE

Subfamilies:
    HIGHWAY_INFRASTRUCTURE
        20.205  Highway Planning and Construction

    PUBLIC_TRANSIT
        20.500  Federal Transit Capital Investment Grants
        20.507  Federal Transit Formula Grants
        20.509  Formula Grants for Rural Areas and Tribal Transit Program
        20.525  State of Good Repair Grants Program

    AIRPORT_INFRASTRUCTURE
        20.106  Airport Improvement Program / COVID / IIJA airport programs

Accounting measure:
    NET_FEDERAL_ACTION_OBLIGATION

Preferred source:
    USASPENDING_ASSISTANCE

Allocation source:
    USASPENDING_ASSISTANCE

Ledger treatment:
    INCLUDE

Resolved disposition:
    INCLUDE_ADDITIVE

Funding provenance:
    COVID / IIJA / other extraordinary funding remains independently tagged
    and does not change accounting disposition.

Scope:
    Washington
    FY2020-FY2024

Corrected full six-program control:
    transactions       9,823
    programs           6
    awards             6,074
    obligation amount  $12,303,575,682.42
    COVID              $3,897,266,967.77
    IIJA                $4,332,494,636.31
    extraordinary      $8,310,671,261.57

Interior-administered 20.205 subset:
    transactions       217
    programs           1
    awards             81
    obligation amount  $99,150,613.43
    COVID              $43,365,102.09
    IIJA                $54,625,383.27
    extraordinary      $93,891,334.66

Expected post-migration effect, subject to independent bridge reconstruction:
    prior INCLUDE_ADDITIVE:
        30,158,111,888.47
      + 12,303,575,682.42
      = 42,461,687,570.89

    prior UNCLASSIFIED_REVIEW:
        82,843,039,059.13
      - 12,303,575,682.42
      = 70,539,463,376.71

This migration is intentionally NOT idempotent.
If target policies or mappings already exist, fail closed.

================================================================================
*/

BEGIN;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-182 SEED TRANSPORTATION ASSISTANCE ACCOUNTING POLICY'
\echo '===================================================================================================='
\echo ''


-- ================================================================================================
-- 1. FULL SIX-PROGRAM SOURCE-POPULATION PRECHECK
--
-- Deliberately no funding_agency_name restriction.
-- ================================================================================================

DO $$
DECLARE
    v_transactions   bigint;
    v_programs       bigint;
    v_awards         bigint;
    v_total          numeric;
    v_covid          numeric;
    v_iija           numeric;
    v_extraordinary  numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COUNT(
            DISTINCT COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            )
        ),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(CASE WHEN is_covid
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_iija
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_extraordinary
                     THEN federal_action_obligation ELSE 0 END),
            0
        )
    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extraordinary
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number IN (
            '20.205',
            '20.500',
            '20.507',
            '20.509',
            '20.525',
            '20.106'
      );

    IF v_transactions <> 9823 THEN
        RAISE EXCEPTION
            'ETL-182 PRECHECK FAILED: expected 9823 transactions; found %',
            v_transactions;
    END IF;

    IF v_programs <> 6 THEN
        RAISE EXCEPTION
            'ETL-182 PRECHECK FAILED: expected 6 programs; found %',
            v_programs;
    END IF;

    IF v_awards <> 6074 THEN
        RAISE EXCEPTION
            'ETL-182 PRECHECK FAILED: expected 6074 awards; found %',
            v_awards;
    END IF;

    IF ABS(v_total - 12303575682.42::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-182 PRECHECK FAILED: expected total 12303575682.42; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 3897266967.77::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-182 PRECHECK FAILED: expected COVID 3897266967.77; found %',
            v_covid;
    END IF;

    IF ABS(v_iija - 4332494636.31::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-182 PRECHECK FAILED: expected IIJA 4332494636.31; found %',
            v_iija;
    END IF;

    IF ABS(v_extraordinary - 8310671261.57::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-182 PRECHECK FAILED: expected extraordinary 8310671261.57; found %',
            v_extraordinary;
    END IF;

    RAISE NOTICE
        'ETL-182 FULL SIX-PROGRAM PRECHECK PASS: programs=% transactions=% awards=% total=% COVID=% IIJA=% extraordinary=%',
        v_programs,
        v_transactions,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extraordinary;
END
$$;


-- ================================================================================================
-- 2. INTERIOR-ADMINISTERED 20.205 SCOPE GUARD
--
-- Preserve and explicitly verify the scope refinement discovered by 5V-1.
-- ================================================================================================

DO $$
DECLARE
    v_transactions   bigint;
    v_awards         bigint;
    v_total          numeric;
    v_covid          numeric;
    v_iija           numeric;
    v_extraordinary  numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(
            DISTINCT COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            )
        ),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(CASE WHEN is_covid
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_iija
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_extraordinary
                     THEN federal_action_obligation ELSE 0 END),
            0
        )
    INTO
        v_transactions,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extraordinary
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number = '20.205'
      AND funding_agency_name = 'Department of the Interior';

    IF v_transactions <> 217
       OR v_awards <> 81
       OR ABS(v_total - 99150613.43::numeric) > 0.01
       OR ABS(v_covid - 43365102.09::numeric) > 0.01
       OR ABS(v_iija - 54625383.27::numeric) > 0.01
       OR ABS(v_extraordinary - 93891334.66::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-182 DOI 20.205 GUARD FAILED: tx=% awards=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_awards,
            v_total,
            v_covid,
            v_iija,
            v_extraordinary;
    END IF;

    RAISE NOTICE
        'ETL-182 DOI 20.205 GUARD PASS: 217 transactions / 81 awards / $99,150,613.43 included as HIGHWAY_INFRASTRUCTURE';
END
$$;


-- ================================================================================================
-- 3. EXACT PROGRAM-SET GUARD
-- ================================================================================================

DO $$
DECLARE
    v_missing integer;
BEGIN
    WITH expected(program_code) AS (
        VALUES
            ('20.205'),
            ('20.500'),
            ('20.507'),
            ('20.509'),
            ('20.525'),
            ('20.106')
    ),
    observed AS (
        SELECT DISTINCT cfda_number AS program_code
        FROM analysis.v_certified_assistance_ledger
        WHERE reference_state_abbreviation = 'WA'
          AND action_date_fiscal_year BETWEEN 2020 AND 2024
          AND cfda_number IN (
                '20.205',
                '20.500',
                '20.507',
                '20.509',
                '20.525',
                '20.106'
          )
    )
    SELECT COUNT(*)
    INTO v_missing
    FROM expected e
    LEFT JOIN observed o
      ON o.program_code = e.program_code
    WHERE o.program_code IS NULL;

    IF v_missing <> 0 THEN
        RAISE EXCEPTION
            'ETL-182 PROGRAM-SET GUARD FAILED: % expected programs absent',
            v_missing;
    END IF;

    RAISE NOTICE
        'ETL-182 PROGRAM-SET GUARD PASS: all six programs present';
END
$$;


-- ================================================================================================
-- 4. FAIL IF ANY TARGET AWARD OVERRIDES EXIST
--
-- A program-level INCLUDE_ADDITIVE decision should not silently supersede an
-- existing award-level accounting decision.
-- ================================================================================================

DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
            '20.205',
            '20.500',
            '20.507',
            '20.509',
            '20.525',
            '20.106'
      );

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-182 AWARD-OVERRIDE GUARD FAILED: % target award classifications already exist',
            v_count;
    END IF;

    RAISE NOTICE
        'ETL-182 AWARD-OVERRIDE GUARD PASS: no target award classifications exist';
END
$$;


-- ================================================================================================
-- 5. FAIL IF TARGET PROGRAM-POLICY MAPPINGS ALREADY EXIST
-- ================================================================================================

DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
            '20.205',
            '20.500',
            '20.507',
            '20.509',
            '20.525',
            '20.106'
      );

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-182 MAPPING DUPLICATE GUARD FAILED: % target mappings already exist',
            v_count;
    END IF;

    RAISE NOTICE
        'ETL-182 MAPPING DUPLICATE GUARD PASS';
END
$$;


-- ================================================================================================
-- 6. FAIL IF TARGET SOURCE POLICIES ALREADY EXIST
--
-- federal_inflow_source_policy has no composite unique constraint.
-- ================================================================================================

DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'TRANSPORTATION_ASSISTANCE'
      AND inflow_subfamily IN (
            'HIGHWAY_INFRASTRUCTURE',
            'PUBLIC_TRANSIT',
            'AIRPORT_INFRASTRUCTURE'
      )
      AND methodology_version = 'ANALYSIS-174B-5V-v2';

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-182 SOURCE-POLICY DUPLICATE GUARD FAILED: % target policies already exist',
            v_count;
    END IF;

    RAISE NOTICE
        'ETL-182 SOURCE-POLICY DUPLICATE GUARD PASS';
END
$$;


-- ================================================================================================
-- 7. INSERT THREE TRANSPORTATION SOURCE POLICIES
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
VALUES
(
    'TRANSPORTATION_ASSISTANCE',
    'HIGHWAY_INFRASTRUCTURE',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'Federal highway assistance under Assistance Listing 20.205 represents additive Washington federal inflow. Classification follows the assistance program and substantive transportation purpose rather than funding-agency label. This includes Tribal Transportation Program and related highway activity administered through the Department of the Interior. Raw funding-agency provenance remains unchanged. USAspending net federal action obligations preserve obligations and deobligations. COVID, IIJA, and other extraordinary funding remain independent provenance dimensions.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
),
(
    'TRANSPORTATION_ASSISTANCE',
    'PUBLIC_TRANSIT',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'Federal public-transit assistance under Assistance Listings 20.500, 20.507, 20.509, and 20.525 represents additive Washington federal inflow. USAspending net federal action obligations preserve obligations and deobligations. COVID, IIJA, and other extraordinary funding remain independent provenance dimensions.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
),
(
    'TRANSPORTATION_ASSISTANCE',
    'AIRPORT_INFRASTRUCTURE',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'Federal airport assistance under Assistance Listing 20.106 represents additive Washington federal inflow. USAspending net federal action obligations preserve obligations and deobligations. COVID, IIJA, and other extraordinary funding remain independent provenance dimensions.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
);


-- ================================================================================================
-- 8. CAPTURE AND VERIFY NEW POLICY IDS
-- ================================================================================================

CREATE TEMP TABLE etl182_transportation_policy AS
SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'TRANSPORTATION_ASSISTANCE'
  AND inflow_subfamily IN (
        'HIGHWAY_INFRASTRUCTURE',
        'PUBLIC_TRANSIT',
        'AIRPORT_INFRASTRUCTURE'
  )
  AND methodology_version = 'ANALYSIS-174B-5V-v2';


DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM etl182_transportation_policy;

    IF v_count <> 3 THEN
        RAISE EXCEPTION
            'ETL-182 POLICY INSERT FAILED: expected 3 policies; found %',
            v_count;
    END IF;

    RAISE NOTICE
        'ETL-182 SOURCE-POLICY INSERT PASS: 3 policies';
END
$$;


-- ================================================================================================
-- 9. INSERT METHODOLOGY-VERSIONED PROGRAM CLASSIFICATIONS
--
-- Older classifications, including the prior 20.205 record, remain untouched.
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
    '20.205',
    'HIGHWAY PLANNING AND CONSTRUCTION',
    'TRANSPORTATION_ASSISTANCE',
    'HIGHWAY_INFRASTRUCTURE',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5V/5V-1: Highway Planning and Construction is additive transportation assistance. The full program scope includes DOT-funded transactions and Interior-administered Tribal Transportation Program activity. Funding-agency provenance is preserved but does not alter economic classification.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '20.500',
    'FEDERAL TRANSIT CAPITAL INVESTMENT GRANTS',
    'TRANSPORTATION_ASSISTANCE',
    'PUBLIC_TRANSIT',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5V/5V-1 transportation-family review: additive federal public-transit assistance using net federal action obligations.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '20.507',
    'FEDERAL TRANSIT FORMULA GRANTS',
    'TRANSPORTATION_ASSISTANCE',
    'PUBLIC_TRANSIT',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5V/5V-1 transportation-family review: additive federal public-transit assistance using net federal action obligations.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '20.509',
    'FORMULA GRANTS FOR RURAL AREAS AND TRIBAL TRANSIT PROGRAM',
    'TRANSPORTATION_ASSISTANCE',
    'PUBLIC_TRANSIT',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5V/5V-1 transportation-family review: additive federal rural and tribal transit assistance using net federal action obligations.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '20.525',
    'STATE OF GOOD REPAIR GRANTS PROGRAM',
    'TRANSPORTATION_ASSISTANCE',
    'PUBLIC_TRANSIT',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5V/5V-1 transportation-family review: additive federal public-transit state-of-good-repair assistance using net federal action obligations.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '20.106',
    'AIRPORT IMPROVEMENT PROGRAM, COVID-19 AIRPORTS PROGRAMS, AND INFRASTRUCTURE INVESTMENT AND JOBS ACT PROGRAMS',
    'TRANSPORTATION_ASSISTANCE',
    'AIRPORT_INFRASTRUCTURE',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5V/5V-1 transportation-family review: additive federal airport assistance using net federal action obligations; COVID and IIJA remain provenance dimensions.',
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
)
ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)
DO NOTHING;


DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
            '20.205','20.500','20.507','20.509','20.525','20.106'
      )
      AND methodology_version = 'ANALYSIS-174B-5V-v2';

    IF v_count <> 6 THEN
        RAISE EXCEPTION
            'ETL-182 PROGRAM CLASSIFICATION FAILED: expected 6 rows; found %',
            v_count;
    END IF;

    RAISE NOTICE
        'ETL-182 PROGRAM CLASSIFICATION PASS: 6 programs';
END
$$;


-- ================================================================================================
-- 10. INSERT SIX PROGRAM-POLICY MAPPINGS
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
    x.source_program_code,
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    x.mapping_basis,
    'ANALYSIS-174B-5V-v2',
    2020,
    2024
FROM (
    VALUES
        (
            '20.205',
            'HIGHWAY_INFRASTRUCTURE',
            'ETL-174B-5V/5V-1: full Assistance Listing 20.205 scope, including Interior-administered Tribal Transportation Program activity, is additive highway infrastructure assistance.'
        ),
        (
            '20.500',
            'PUBLIC_TRANSIT',
            'ETL-174B-5V/5V-1: Federal Transit Capital Investment Grants are additive Washington public-transit assistance.'
        ),
        (
            '20.507',
            'PUBLIC_TRANSIT',
            'ETL-174B-5V/5V-1: Federal Transit Formula Grants are additive Washington public-transit assistance.'
        ),
        (
            '20.509',
            'PUBLIC_TRANSIT',
            'ETL-174B-5V/5V-1: Rural and Tribal Transit formula grants are additive Washington public-transit assistance.'
        ),
        (
            '20.525',
            'PUBLIC_TRANSIT',
            'ETL-174B-5V/5V-1: State of Good Repair grants are additive Washington public-transit assistance.'
        ),
        (
            '20.106',
            'AIRPORT_INFRASTRUCTURE',
            'ETL-174B-5V/5V-1: Airport Improvement, COVID-19 airport, and IIJA airport assistance are additive Washington airport infrastructure assistance.'
        )
) AS x (
    source_program_code,
    inflow_subfamily,
    mapping_basis
)
JOIN etl182_transportation_policy p
  ON p.inflow_subfamily = x.inflow_subfamily
ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)
DO NOTHING;


DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
            '20.205','20.500','20.507','20.509','20.525','20.106'
      )
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE';

    IF v_count <> 6 THEN
        RAISE EXCEPTION
            'ETL-182 MAPPING INSERT FAILED: expected 6 mappings; found %',
            v_count;
    END IF;

    RAISE NOTICE
        'ETL-182 MAPPING INSERT PASS: 6 INCLUDE_ADDITIVE mappings';
END
$$;


-- ================================================================================================
-- 11. SUBFAMILY ASSIGNMENT GUARD
-- ================================================================================================

DO $$
DECLARE
    v_bad integer;
BEGIN
    SELECT COUNT(*)
    INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.methodology_version = 'ANALYSIS-174B-5V-v2'
      AND m.source_program_code IN (
            '20.205','20.500','20.507','20.509','20.525','20.106'
      )
      AND NOT (
            (m.source_program_code = '20.205'
             AND p.inflow_subfamily = 'HIGHWAY_INFRASTRUCTURE')
         OR
            (m.source_program_code IN ('20.500','20.507','20.509','20.525')
             AND p.inflow_subfamily = 'PUBLIC_TRANSIT')
         OR
            (m.source_program_code = '20.106'
             AND p.inflow_subfamily = 'AIRPORT_INFRASTRUCTURE')
      );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-182 SUBFAMILY GUARD FAILED: % mappings assigned incorrectly',
            v_bad;
    END IF;

    RAISE NOTICE
        'ETL-182 SUBFAMILY GUARD PASS';
END
$$;


-- ================================================================================================
-- 12. INDEPENDENT PERSISTED-MAPPING DOLLAR CONTROL
-- ================================================================================================

DO $$
DECLARE
    v_transactions   bigint;
    v_programs       bigint;
    v_awards         bigint;
    v_total          numeric;
    v_covid          numeric;
    v_iija           numeric;
    v_extraordinary  numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT a.cfda_number),
        COUNT(
            DISTINCT COALESCE(
                NULLIF(a.award_id_fain, ''),
                NULLIF(a.award_id_uri, '')
            )
        ),
        COALESCE(SUM(a.federal_action_obligation), 0),
        COALESCE(
            SUM(CASE WHEN a.is_covid
                     THEN a.federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN a.is_iija
                     THEN a.federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN a.is_extraordinary
                     THEN a.federal_action_obligation ELSE 0 END),
            0
        )
    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extraordinary
    FROM analysis.v_certified_assistance_ledger a
    JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = a.cfda_number
     AND m.methodology_version = 'ANALYSIS-174B-5V-v2'
     AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
     AND (
            m.valid_from_fiscal_year IS NULL
            OR a.action_date_fiscal_year >= m.valid_from_fiscal_year
         )
     AND (
            m.valid_through_fiscal_year IS NULL
            OR a.action_date_fiscal_year <= m.valid_through_fiscal_year
         )
    WHERE a.reference_state_abbreviation = 'WA'
      AND a.action_date_fiscal_year BETWEEN 2020 AND 2024;

    IF v_transactions <> 9823
       OR v_programs <> 6
       OR v_awards <> 6074
       OR ABS(v_total - 12303575682.42::numeric) > 0.01
       OR ABS(v_covid - 3897266967.77::numeric) > 0.01
       OR ABS(v_iija - 4332494636.31::numeric) > 0.01
       OR ABS(v_extraordinary - 8310671261.57::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-182 MAPPED-DOLLAR CONTROL FAILED: tx=% programs=% awards=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_awards,
            v_total,
            v_covid,
            v_iija,
            v_extraordinary;
    END IF;

    RAISE NOTICE
        'ETL-182 MAPPED-DOLLAR CONTROL PASS: tx=% programs=% awards=% additive=% COVID=% IIJA=% extraordinary=%',
        v_transactions,
        v_programs,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extraordinary;
END
$$;


-- ================================================================================================
-- 13. SCOPE / POLICY CONTRACT GUARD
-- ================================================================================================

DO $$
DECLARE
    v_bad integer;
BEGIN
    SELECT COUNT(*)
    INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.methodology_version = 'ANALYSIS-174B-5V-v2'
      AND m.source_program_code IN (
            '20.205','20.500','20.507','20.509','20.525','20.106'
      )
      AND (
            m.valid_from_fiscal_year <> 2020
         OR m.valid_through_fiscal_year <> 2024
         OR p.valid_from_fiscal_year <> 2020
         OR p.valid_through_fiscal_year <> 2024
         OR p.accounting_measure <> 'NET_FEDERAL_ACTION_OBLIGATION'
         OR p.preferred_source <> 'USASPENDING_ASSISTANCE'
         OR p.allocation_source <> 'USASPENDING_ASSISTANCE'
         OR p.ledger_treatment <> 'INCLUDE'
      );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-182 POLICY CONTRACT GUARD FAILED: % rows violate expected contract',
            v_bad;
    END IF;

    RAISE NOTICE
        'ETL-182 POLICY CONTRACT GUARD PASS';
END
$$;


-- ================================================================================================
-- 14. HUMAN-READABLE PERSISTED POLICY OUTPUT
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo 'PERSISTED TRANSPORTATION ACCOUNTING POLICY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.source_program_code,
    c.source_program_title,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment,
    m.resolved_accounting_disposition,
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
 AND c.methodology_version = 'ANALYSIS-174B-5V-v2'
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.methodology_version = 'ANALYSIS-174B-5V-v2'
  AND m.source_program_code IN (
        '20.205','20.500','20.507','20.509','20.525','20.106'
  )
ORDER BY
    p.inflow_subfamily,
    m.source_program_code;


-- ================================================================================================
-- 15. FINAL CERTIFICATION
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-182 PASS - full six-program transportation population persisted as INCLUDE_ADDITIVE: 9,823 transactions / $12,303,575,682.42; Interior-administered 20.205 retained as transportation assistance; COVID and IIJA provenance preserved';
END
$$;

COMMIT;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-182 COMPLETE'
\echo '===================================================================================================='