/*
================================================================================
Migration 181
Persist SNAP 10.551 Assistance Accounting Policy
================================================================================

Project:
Washington County Federal Fiscal Balance Project (WCFFBP)

Purpose
-------
Persist the accounting treatment established by ETL-174B-5S for:

    10.551  Supplemental Nutrition Assistance Program (SNAP)

Scope
-----
Washington
FY2020-FY2024
USAspending assistance transactions only

Accounting decision
-------------------
10.551 is classified:

    INCLUDE_ADDITIVE

Accounting measure:

    NET_FEDERAL_ACTION_OBLIGATION

Evidence
--------
ETL-174B-5S established:

    transactions              59
    programs                   1
    annual awards              5
    recipients                 1
    total obligations          11,879,986,141.72
    COVID-tagged                9,549,726,843.52
    non-COVID                   2,330,259,298.20
    IIJA                                    0.00

All transactions were awarded to:

    DEPARTMENT OF SOCIAL & HEALTH SERVICES

There is one annual Washington award for each FY2020-FY2024.

Transaction descriptions are limited to:

    SUPPLEMENTAL NUTRITION ASSISTANCE PROGRAM
    SNAP EBT BENEFITS

USAspending separately reports SNAP administrative matching grants under
Assistance Listing 10.561, supporting treatment of 10.551 as the benefit
funding stream rather than the ordinary administrative matching stream.

USDA/FNS FNS-388 / FNS-388A were identified as desirable authoritative
external validation sources for benefit issuance. Historical Washington
submission values for FY2020-FY2024 were not publicly retrieved during this
stage and therefore are NOT substituted or imputed.

COVID treatment
---------------
COVID is funding provenance, not accounting disposition.

COVID-tagged 10.551 transactions remain INCLUDE_ADDITIVE and retain their
independent COVID / extraordinary classifications.

Important
---------
This migration does NOT classify:
    10.561
    any other USDA program
    any other nutrition program

No blanket USDA, FNS, SNAP-family, or 10.* rule is created.

Methodology version:
    ANALYSIS-174B-5S-v1
================================================================================
*/

BEGIN;


-- ================================================================================================
-- 1. HARD SOURCE POPULATION PRECHECK
-- ================================================================================================

DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_awards       bigint;
    v_recipients   bigint;
    v_total        numeric;
    v_covid        numeric;
    v_non_covid    numeric;
    v_iija         numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)),
        COUNT(DISTINCT recipient_name),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(
                CASE WHEN is_covid
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        ),
        COALESCE(
            SUM(
                CASE WHEN NOT is_covid
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        ),
        COALESCE(
            SUM(
                CASE WHEN is_iija
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        )
    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_recipients,
        v_total,
        v_covid,
        v_non_covid,
        v_iija
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number = '10.551';

    IF v_transactions <> 59 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected 59 transactions; found %',
            v_transactions;
    END IF;

    IF v_programs <> 1 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected 1 program; found %',
            v_programs;
    END IF;

    IF v_awards <> 5 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected 5 annual awards; found %',
            v_awards;
    END IF;

    IF v_recipients <> 1 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected 1 recipient; found %',
            v_recipients;
    END IF;

    IF ABS(v_total - 11879986141.72::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected total 11879986141.72; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 9549726843.52::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected COVID 9549726843.52; found %',
            v_covid;
    END IF;

    IF ABS(v_non_covid - 2330259298.20::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected non-COVID 2330259298.20; found %',
            v_non_covid;
    END IF;

    IF ABS(v_iija) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-181 PRECHECK FAILED: expected IIJA 0; found %',
            v_iija;
    END IF;

    RAISE NOTICE
        'ETL-181 PRECHECK PASS: programs=% transactions=% awards=% recipients=% total=% COVID=% non-COVID=% IIJA=%',
        v_programs,
        v_transactions,
        v_awards,
        v_recipients,
        v_total,
        v_covid,
        v_non_covid,
        v_iija;
END
$$;


-- ================================================================================================
-- 2. GUARD AGAINST PREEXISTING ETL-181 SOURCE POLICY
--
-- federal_inflow_source_policy does NOT have the composite uniqueness constraint
-- used by federal_inflow_program_policy_mapping. Therefore do not use ON CONFLICT
-- here. Fail explicitly if this methodology has already been persisted.
-- ================================================================================================

DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'NUTRITION_ASSISTANCE'
      AND inflow_subfamily = 'SNAP_BENEFITS'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND methodology_version = 'ANALYSIS-174B-5S-v1';

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-181 GUARD FAILED: SNAP source policy already exists (% rows)',
            v_count;
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
    'NUTRITION_ASSISTANCE',
    'SNAP_BENEFITS',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'ETL-174B-5S established Assistance Listing 10.551 as five annual Washington SNAP benefit awards to the Department of Social & Health Services for FY2020-FY2024. Transaction descriptions identify the stream as Supplemental Nutrition Assistance Program / SNAP EBT Benefits. SNAP administrative matching grants are separately represented under Assistance Listing 10.561. USDA/FNS FNS-388 and FNS-388A were identified as desirable external benefit-issuance validation sources, but historical Washington FY2020-FY2024 submission values were not publicly retrieved and are not substituted or imputed. COVID remains an independent funding-provenance dimension.',
    'ANALYSIS-174B-5S-v1',
    2020,
    2024
);


-- ================================================================================================
-- 4. CAPTURE SOURCE POLICY ID
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl181_policy;

CREATE TEMP TABLE etl181_policy AS
SELECT
    federal_inflow_source_policy_id
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'NUTRITION_ASSISTANCE'
  AND inflow_subfamily = 'SNAP_BENEFITS'
  AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
  AND methodology_version = 'ANALYSIS-174B-5S-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM etl181_policy;

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-181 POLICY-ID FAILED: expected exactly 1 source policy; found %',
            v_count;
    END IF;
END
$$;


-- ================================================================================================
-- 5. PROGRAM CLASSIFICATION GUARD
-- ================================================================================================

DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.551'
      AND methodology_version = 'ANALYSIS-174B-5S-v1';

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-181 GUARD FAILED: 10.551 program classification already exists (% rows)',
            v_count;
    END IF;
END
$$;


-- ================================================================================================
-- 6. INSERT PROGRAM CLASSIFICATION
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
VALUES (
    'USASPENDING_ASSISTANCE',
    '10.551',
    'SUPPLEMENTAL NUTRITION ASSISTANCE PROGRAM',
    'NUTRITION_ASSISTANCE',
    'SNAP_BENEFITS',
    'LOW',
    TRUE,
    TRUE,
    'ETL-174B-5S identified 10.551 as five annual Washington SNAP benefit awards to DSHS totaling $11,879,986,141.72 for FY2020-FY2024. Later transaction descriptions explicitly identify SNAP EBT BENEFITS. Ordinary SNAP administrative matching grants are separately represented by Assistance Listing 10.561. COVID-tagged benefit obligations remain additive and retain independent funding provenance.',
    'ANALYSIS-174B-5S-v1',
    2020,
    2024
);


-- ================================================================================================
-- 7. PROGRAM-POLICY MAPPING GUARD
-- ================================================================================================

DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.551'
      AND methodology_version = 'ANALYSIS-174B-5S-v1';

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-181 GUARD FAILED: 10.551 program-policy mapping already exists (% rows)',
            v_count;
    END IF;
END
$$;


-- ================================================================================================
-- 8. INSERT PROGRAM-POLICY MAPPING
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
    '10.551',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'ETL-174B-5S established 10.551 as Washington SNAP benefit funding rather than the separately reported SNAP administrative matching stream. Include net federal action obligations as additive federal inflow. Preserve COVID provenance independently.',
    'ANALYSIS-174B-5S-v1',
    2020,
    2024
FROM etl181_policy p
ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)
DO NOTHING;


-- ================================================================================================
-- 9. VERIFY PERSISTED CLASSIFICATION AND MAPPING
-- ================================================================================================

DO $$
DECLARE
    v_classifications bigint;
    v_mappings        bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_classifications
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.551'
      AND methodology_version = 'ANALYSIS-174B-5S-v1';

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.551'
      AND methodology_version = 'ANALYSIS-174B-5S-v1'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE';

    IF v_classifications <> 1 THEN
        RAISE EXCEPTION
            'ETL-181 VERIFY FAILED: expected 1 program classification; found %',
            v_classifications;
    END IF;

    IF v_mappings <> 1 THEN
        RAISE EXCEPTION
            'ETL-181 VERIFY FAILED: expected 1 INCLUDE_ADDITIVE mapping; found %',
            v_mappings;
    END IF;
END
$$;


-- ================================================================================================
-- 10. VERIFY MAPPED DOLLARS
-- ================================================================================================

DO $$
DECLARE
    v_transactions bigint;
    v_total        numeric;
    v_covid        numeric;
    v_wrong        bigint;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(l.federal_action_obligation), 0),
        COALESCE(
            SUM(
                CASE WHEN l.is_covid
                     THEN l.federal_action_obligation
                     ELSE 0
                END
            ),
            0
        ),
        COUNT(*) FILTER (
            WHERE m.resolved_accounting_disposition <> 'INCLUDE_ADDITIVE'
               OR m.methodology_version <> 'ANALYSIS-174B-5S-v1'
        )
    INTO
        v_transactions,
        v_total,
        v_covid,
        v_wrong
    FROM analysis.v_certified_assistance_ledger l
    JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = l.cfda_number
     AND l.action_date_fiscal_year >= m.valid_from_fiscal_year
     AND l.action_date_fiscal_year <= m.valid_through_fiscal_year
     AND m.methodology_version = 'ANALYSIS-174B-5S-v1'
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number = '10.551';

    IF v_transactions <> 59 THEN
        RAISE EXCEPTION
            'ETL-181 MAPPED-DOLLAR FAILED: expected 59 transactions; found %',
            v_transactions;
    END IF;

    IF ABS(v_total - 11879986141.72::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-181 MAPPED-DOLLAR FAILED: expected 11879986141.72; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 9549726843.52::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-181 MAPPED-DOLLAR FAILED: expected COVID 9549726843.52; found %',
            v_covid;
    END IF;

    IF v_wrong <> 0 THEN
        RAISE EXCEPTION
            'ETL-181 MAPPED-DOLLAR FAILED: % transactions have unexpected disposition/methodology',
            v_wrong;
    END IF;

    RAISE NOTICE
        'ETL-181 MAPPED-DOLLAR PASS: transactions=% additive=% COVID=%',
        v_transactions,
        v_total,
        v_covid;
END
$$;


-- ================================================================================================
-- 11. SCOPE GUARD
--
-- Ensure this methodology classified no program other than 10.551.
-- ================================================================================================

DO $$
DECLARE
    v_other_programs bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_other_programs
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-174B-5S-v1'
      AND source_program_code <> '10.551';

    IF v_other_programs <> 0 THEN
        RAISE EXCEPTION
            'ETL-181 SCOPE FAILED: methodology unexpectedly maps % other programs',
            v_other_programs;
    END IF;
END
$$;


-- ================================================================================================
-- 12. FY2025+ GUARD
-- ================================================================================================

DO $$
DECLARE
    v_future_rows bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_future_rows
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.551'
      AND methodology_version = 'ANALYSIS-174B-5S-v1'
      AND (
            valid_from_fiscal_year > 2024
         OR valid_through_fiscal_year > 2024
      );

    IF v_future_rows <> 0 THEN
        RAISE EXCEPTION
            'ETL-181 FY-SCOPE FAILED: found % mappings extending beyond FY2024',
            v_future_rows;
    END IF;
END
$$;


-- ================================================================================================
-- 13. HUMAN-READABLE RESULT
-- ================================================================================================

SELECT
    m.source_program_code,
    c.source_program_title,
    m.resolved_accounting_disposition,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
JOIN reference.federal_inflow_program_classification c
  ON c.source_system = m.source_system
 AND c.source_program_code = m.source_program_code
 AND c.methodology_version = m.methodology_version
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '10.551'
  AND m.methodology_version = 'ANALYSIS-174B-5S-v1';


-- ================================================================================================
-- 14. COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-181 PASS - SNAP 10.551 persisted as INCLUDE_ADDITIVE; FY2020-FY2024 only; COVID provenance preserved independently';
END
$$;


COMMIT;