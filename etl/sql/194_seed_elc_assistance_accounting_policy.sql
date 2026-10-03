/*
====================================================================================================
ETL-194
SEED ELC ASSISTANCE ACCOUNTING POLICY
AL 93.323
EPIDEMIOLOGY AND LABORATORY CAPACITY FOR INFECTIOUS DISEASES
====================================================================================================

Purpose:
    Establish the WCFFBP statewide accounting treatment for Washington
    FY2020-FY2024 USAspending Assistance Listing 93.323:

        Epidemiology and Laboratory Capacity for Infectious Diseases (ELC)

Evidence:
    ETL-193A profiled the AL 93.323 population.

    ETL-193B investigated cross-program award-identifier collisions and found
    that CDC award identifiers may span multiple Assistance Listings.

Accounting conclusion:
    Shared CDC award identifiers do not, by themselves, represent duplicate
    federal inflow.

    For AL 93.323, ETL-193B found:

        - no nonzero same-award + same-date + same-absolute-obligation
          collisions across Assistance Listings;

        - no same-award + same-signed-obligation collisions across Assistance
          Listings even when action date was ignored;

        - one weaker $25,000 absolute-dollar coincidence across two Assistance
          Listings on different dates, insufficient to establish duplication.

    The observed cross-AL structure is therefore treated as component-level
    program accounting within shared CDC award instruments rather than evidence
    that AL 93.323 obligations are duplicated.

Principal accounting treatment:

    inflow_family:
        PUBLIC_HEALTH_ASSISTANCE

    inflow_subfamily:
        EPIDEMIOLOGY_LABORATORY_CAPACITY

    accounting_measure:
        NET_FEDERAL_ACTION_OBLIGATION

    preferred_source:
        USASPENDING_ASSISTANCE

    allocation_source:
        UNRESOLVED

    overlap_risk:
        NONE

    ledger_treatment:
        INCLUDE

    resolved_accounting_disposition:
        INCLUDE_ADDITIVE

Provenance:
    COVID and extraordinary status remain orthogonal reporting dimensions.
    IIJA remains separately controlled.

Important:
    Inclusion here applies to the federal obligation represented by AL 93.323.
    Downstream expenditures, transfers, subawards, reimbursements, or other
    uses of an already-counted federal obligation are not second federal
    inflows.

County incidence remains unresolved.

This migration is intentionally limited to AL 93.323. It does not establish
accounting treatment for any other CDC or HHS Assistance Listing.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-194 - SEED ELC ASSISTANCE ACCOUNTING POLICY'
\echo 'AL 93.323'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m194_elc;

CREATE TEMP TABLE m194_elc AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.323';


/*
====================================================================================================
2. EXACT PRE-MIGRATION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. EXACT PRE-MIGRATION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    COUNT(DISTINCT recipient_id)
        AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN is_iija
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m194_elc;


DO $$
DECLARE
    v_tx       bigint;
    v_awards   bigint;
    v_recip    bigint;
    v_amount   numeric;
    v_covid    numeric;
    v_iija     numeric;
    v_extra    numeric;
BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            )
        ),

        COUNT(DISTINCT recipient_id),

        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_tx,
        v_awards,
        v_recip,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m194_elc;


    IF v_tx <> 360 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-CONTROL FAILED: expected 360 transactions; found %',
            v_tx;
    END IF;


    IF v_awards <> 12 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-CONTROL FAILED: expected 12 awards; found %',
            v_awards;
    END IF;


    IF v_recip <> 5 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-CONTROL FAILED: expected 5 recipients; found %',
            v_recip;
    END IF;


    IF ROUND(v_amount, 2) <> 990041302.24 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-CONTROL FAILED: expected net obligation 990041302.24; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 987883249.28 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-CONTROL FAILED: expected COVID amount 987883249.28; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-CONTROL FAILED: expected IIJA amount 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 987883249.28 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-CONTROL FAILED: expected extraordinary amount 987883249.28; found %',
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-194 PRE-CONTROL PASS: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
        v_tx,
        v_awards,
        v_recip,
        ROUND(v_amount, 2),
        ROUND(v_covid, 2),
        ROUND(v_iija, 2),
        ROUND(v_extra, 2);

END
$$;


/*
====================================================================================================
3. FISCAL-YEAR CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FISCAL-YEAR CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN is_iija
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m194_elc

GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. TRANSACTION-SIGN CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. TRANSACTION-SIGN CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    CASE
        WHEN federal_action_obligation > 0
            THEN 'POSITIVE'

        WHEN federal_action_obligation < 0
            THEN 'NEGATIVE'

        ELSE 'ZERO'
    END AS obligation_sign,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m194_elc

GROUP BY 1
ORDER BY 1;


/*
====================================================================================================
5. PRE-EXISTING POLICY GUARD

Migration 194 is intended to create the AL 93.323 treatment once.

Fail closed if an active AL 93.323 classification or mapping already exists.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. PRE-EXISTING POLICY GUARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.323'
  AND valid_through_fiscal_year IS NULL;


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.323'
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_class_count bigint;
    v_map_count   bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_class_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.323'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_map_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.323'
      AND valid_through_fiscal_year IS NULL;


    IF v_class_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-EXISTING POLICY GUARD FAILED: active AL 93.323 classification already exists';
    END IF;


    IF v_map_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-194 PRE-EXISTING POLICY GUARD FAILED: active AL 93.323 policy mapping already exists';
    END IF;


    RAISE NOTICE
        'ETL-194 PRE-EXISTING POLICY GUARD PASS';

END
$$;


/*
====================================================================================================
6. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. INSERT ELC SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_source_policy
(
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

SELECT
    'PUBLIC_HEALTH_ASSISTANCE',

    'EPIDEMIOLOGY_LABORATORY_CAPACITY',

    'NET_FEDERAL_ACTION_OBLIGATION',

    'USASPENDING_ASSISTANCE',

    'UNRESOLVED',

    ARRAY[]::text[],

    'INCLUDE',

    'AL 93.323 Epidemiology and Laboratory Capacity for Infectious Diseases. '
    ||
    'ETL-193A established the Washington FY2020-FY2024 focal population and '
    ||
    'identified shared CDC award identifiers across multiple Assistance Listings. '
    ||
    'ETL-193B reconciled those collisions. Shared CDC award identifiers were found '
    ||
    'to represent multi-program/component award structures rather than evidence of '
    ||
    'duplicate AL 93.323 federal obligations. ETL-193B found no nonzero same-award, '
    ||
    'same-date, same-absolute-obligation collision across Assistance Listings and '
    ||
    'no same-award, same-signed-obligation collision across Assistance Listings '
    ||
    'even when action date was ignored. One weaker $25,000 absolute-dollar '
    ||
    'coincidence occurred on different dates and does not establish duplication. '
    ||
    'USAspending net federal action obligation is therefore the principal statewide '
    ||
    'accounting measure for this assistance stream. COVID and extraordinary status '
    ||
    'remain orthogonal provenance dimensions. IIJA remains separately controlled. '
    ||
    'Downstream expenditures, transfers, subawards, reimbursements, or other uses '
    ||
    'of these already-counted obligations are not additional federal inflows. '
    ||
    'County incidence remains unresolved.',

    'ANALYSIS-194-v1',

    2020,

    NULL

WHERE NOT EXISTS
(
    SELECT 1

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'PUBLIC_HEALTH_ASSISTANCE'
      AND inflow_subfamily = 'EPIDEMIOLOGY_LABORATORY_CAPACITY'
      AND methodology_version = 'ANALYSIS-194-v1'
);


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
    valid_through_fiscal_year

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'PUBLIC_HEALTH_ASSISTANCE'
  AND inflow_subfamily = 'EPIDEMIOLOGY_LABORATORY_CAPACITY'
  AND methodology_version = 'ANALYSIS-194-v1';


/*
====================================================================================================
7. ASSERT SOURCE POLICY
====================================================================================================
*/

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'PUBLIC_HEALTH_ASSISTANCE'
      AND inflow_subfamily = 'EPIDEMIOLOGY_LABORATORY_CAPACITY'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND allocation_source = 'UNRESOLVED'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-194-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year IS NULL;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-194 SOURCE POLICY ASSERTION FAILED: expected exactly 1 policy; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-194 SOURCE POLICY ASSERTION PASS';

END
$$;


/*
====================================================================================================
8. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. INSERT AL 93.323 PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_classification
(
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

SELECT
    'USASPENDING_ASSISTANCE',

    '93.323',

    'Epidemiology and Laboratory Capacity for Infectious Diseases',

    'PUBLIC_HEALTH_ASSISTANCE',

    'EPIDEMIOLOGY_LABORATORY_CAPACITY',

    'NONE',

    TRUE,

    TRUE,

    'ETL-193A profiled AL 93.323 and ETL-193B reconciled its shared CDC award '
    ||
    'identifiers against other Washington Assistance Listings. Award-ID sharing '
    ||
    'was not accompanied by nonzero same-award/same-date/same-absolute-obligation '
    ||
    'duplication. No same-award/same-signed-obligation collision was found across '
    ||
    'Assistance Listings even when date was ignored. AL 93.323 is therefore '
    ||
    'classified as a distinct additive public-health assistance stream. COVID '
    ||
    'and extraordinary funding remain transaction-level provenance dimensions.',

    'ANALYSIS-194-v1',

    2020,

    NULL

WHERE NOT EXISTS
(
    SELECT 1

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.323'
      AND methodology_version = 'ANALYSIS-194-v1'
);


SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.323'
  AND methodology_version = 'ANALYSIS-194-v1';


/*
====================================================================================================
9. ASSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.323'
      AND inflow_family = 'PUBLIC_HEALTH_ASSISTANCE'
      AND inflow_subfamily = 'EPIDEMIOLOGY_LABORATORY_CAPACITY'
      AND overlap_risk = 'NONE'
      AND covid_relevance = TRUE
      AND extraordinary_relevance = TRUE
      AND methodology_version = 'ANALYSIS-194-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year IS NULL;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-194 PROGRAM CLASSIFICATION ASSERTION FAILED: expected exactly 1 classification; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-194 PROGRAM CLASSIFICATION ASSERTION PASS';

END
$$;


/*
====================================================================================================
10. INSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. INSERT AL 93.323 PROGRAM POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_policy_mapping
(
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

    '93.323',

    p.federal_inflow_source_policy_id,

    'INCLUDE_ADDITIVE',

    'AL 93.323 is included additively using USAspending net federal action '
    ||
    'obligations. ETL-193B found no evidence that its nonzero obligation events '
    ||
    'are duplicated under other Assistance Listings despite shared CDC award '
    ||
    'identifiers. Downstream uses of these already-counted obligations are not '
    ||
    'second federal inflows.',

    'ANALYSIS-194-v1',

    2020,

    NULL

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'PUBLIC_HEALTH_ASSISTANCE'
  AND p.inflow_subfamily = 'EPIDEMIOLOGY_LABORATORY_CAPACITY'
  AND p.methodology_version = 'ANALYSIS-194-v1'

  AND NOT EXISTS
  (
      SELECT 1

      FROM reference.federal_inflow_program_policy_mapping m

      WHERE m.source_system = 'USASPENDING_ASSISTANCE'
        AND m.source_program_code = '93.323'
        AND m.methodology_version = 'ANALYSIS-194-v1'
  );


SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.federal_inflow_source_policy_id,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping m

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '93.323'
  AND m.methodology_version = 'ANALYSIS-194-v1';


/*
====================================================================================================
11. ASSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '93.323'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND m.methodology_version = 'ANALYSIS-194-v1'
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year IS NULL

      AND p.inflow_family = 'PUBLIC_HEALTH_ASSISTANCE'
      AND p.inflow_subfamily = 'EPIDEMIOLOGY_LABORATORY_CAPACITY'
      AND p.accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND p.preferred_source = 'USASPENDING_ASSISTANCE'
      AND p.ledger_treatment = 'INCLUDE';


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-194 PROGRAM POLICY MAPPING ASSERTION FAILED: expected exactly 1 mapping; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-194 PROGRAM POLICY MAPPING ASSERTION PASS';

END
$$;


/*
====================================================================================================
12. EFFECTIVE ACCOUNTING RESOLUTION

Reconstruct disposition independently from the program-policy mapping.

No reliance on a cached result from the INSERT statements.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EFFECTIVE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m194_effective;

CREATE TEMP TABLE m194_effective AS

SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year,
    l.cfda_number,
    l.federal_action_obligation,
    l.is_covid,
    l.is_iija,
    l.is_extraordinary,

    m.resolved_accounting_disposition,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment

FROM analysis.v_certified_assistance_ledger l

LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = l.cfda_number
 AND l.action_date_fiscal_year >= m.valid_from_fiscal_year
 AND (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= m.valid_through_fiscal_year
     )

LEFT JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
 AND l.action_date_fiscal_year >= p.valid_from_fiscal_year
 AND (
        p.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= p.valid_through_fiscal_year
     )

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number = '93.323';


SELECT
    COALESCE(
        resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_disposition,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN is_iija
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m194_effective

GROUP BY
    COALESCE(
        resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    )

ORDER BY effective_disposition;


/*
====================================================================================================
13. EXACT POST-MIGRATION CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXACT POST-MIGRATION CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_tx          bigint;
    v_amount      numeric;
    v_covid       numeric;
    v_iija        numeric;
    v_extra       numeric;
    v_unresolved  bigint;
    v_policy_id   bigint;
BEGIN

    SELECT
        COUNT(*),

        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COUNT(*) FILTER
        (
            WHERE resolved_accounting_disposition IS DISTINCT FROM
                  'INCLUDE_ADDITIVE'
        ),

        MIN(federal_inflow_source_policy_id)

    INTO
        v_tx,
        v_amount,
        v_covid,
        v_iija,
        v_extra,
        v_unresolved,
        v_policy_id

    FROM m194_effective;


    IF v_tx <> 360 THEN
        RAISE EXCEPTION
            'ETL-194 POST-CONTROL FAILED: expected 360 transactions; found %',
            v_tx;
    END IF;


    IF ROUND(v_amount, 2) <> 990041302.24 THEN
        RAISE EXCEPTION
            'ETL-194 POST-CONTROL FAILED: expected amount 990041302.24; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 987883249.28 THEN
        RAISE EXCEPTION
            'ETL-194 POST-CONTROL FAILED: expected COVID 987883249.28; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-194 POST-CONTROL FAILED: expected IIJA 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 987883249.28 THEN
        RAISE EXCEPTION
            'ETL-194 POST-CONTROL FAILED: expected extraordinary 987883249.28; found %',
            ROUND(v_extra, 2);
    END IF;


    IF v_unresolved <> 0 THEN
        RAISE EXCEPTION
            'ETL-194 POST-CONTROL FAILED: % focal transactions are not INCLUDE_ADDITIVE',
            v_unresolved;
    END IF;


    IF v_policy_id IS NULL THEN
        RAISE EXCEPTION
            'ETL-194 POST-CONTROL FAILED: source policy ID is NULL';
    END IF;


    RAISE NOTICE
        'ETL-194 POST-CONTROL PASS: tx=% amount=% COVID=% IIJA=% extraordinary=% policy_id=%',
        v_tx,
        ROUND(v_amount, 2),
        ROUND(v_covid, 2),
        ROUND(v_iija, 2),
        ROUND(v_extra, 2),
        v_policy_id;

END
$$;


/*
====================================================================================================
14. FISCAL-YEAR POST-MIGRATION BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. FISCAL-YEAR POST-MIGRATION BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN is_iija
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m194_effective

GROUP BY
    action_date_fiscal_year,
    resolved_accounting_disposition

ORDER BY
    action_date_fiscal_year,
    resolved_accounting_disposition;


/*
====================================================================================================
15. FINAL PERSISTED-OBJECT CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. FINAL PERSISTED-OBJECT CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.methodology_version,

    c.federal_inflow_program_classification_id,
    c.source_program_code,
    c.source_program_title,
    c.overlap_risk,
    c.covid_relevance,
    c.extraordinary_relevance,
    c.methodology_version
        AS classification_methodology_version,

    m.federal_inflow_program_policy_mapping_id,
    m.resolved_accounting_disposition,
    m.methodology_version
        AS mapping_methodology_version

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id

JOIN reference.federal_inflow_program_classification c
  ON c.source_system = m.source_system
 AND c.source_program_code = m.source_program_code
 AND c.methodology_version = 'ANALYSIS-194-v1'

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '93.323'
  AND m.methodology_version = 'ANALYSIS-194-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id

    JOIN reference.federal_inflow_program_classification c
      ON c.source_system = m.source_system
     AND c.source_program_code = m.source_program_code
     AND c.methodology_version = 'ANALYSIS-194-v1'

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '93.323'
      AND m.methodology_version = 'ANALYSIS-194-v1'

      AND m.resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'

      AND p.inflow_family =
          'PUBLIC_HEALTH_ASSISTANCE'

      AND p.inflow_subfamily =
          'EPIDEMIOLOGY_LABORATORY_CAPACITY'

      AND p.accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'

      AND p.preferred_source =
          'USASPENDING_ASSISTANCE'

      AND p.allocation_source =
          'UNRESOLVED'

      AND p.ledger_treatment =
          'INCLUDE'

      AND c.overlap_risk =
          'NONE'

      AND c.covid_relevance =
          TRUE

      AND c.extraordinary_relevance =
          TRUE;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-194 FINAL CERTIFICATION FAILED: expected exactly 1 complete ELC policy chain; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-194 FINAL CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
16. COMMIT
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-194 CERTIFICATION COMPLETE'
\echo ''
\echo 'AL 93.323'
\echo 'Epidemiology and Laboratory Capacity for Infectious Diseases'
\echo ''
\echo 'Accounting treatment:'
\echo '  PUBLIC_HEALTH_ASSISTANCE'
\echo '  EPIDEMIOLOGY_LABORATORY_CAPACITY'
\echo '  NET_FEDERAL_ACTION_OBLIGATION'
\echo '  USASPENDING_ASSISTANCE'
\echo '  INCLUDE_ADDITIVE'
\echo ''
\echo 'Exact FY2020-FY2024 focal control:'
\echo '  Transactions       360'
\echo '  Awards               12'
\echo '  Recipients            5'
\echo '  Net obligation   $990,041,302.24'
\echo '  COVID            $987,883,249.28'
\echo '  IIJA                       $0.00'
\echo '  Extraordinary     $987,883,249.28'
\echo ''
\echo 'ETL-193B cross-AL award reconciliation incorporated.'
\echo 'County incidence remains unresolved.'
\echo '===================================================================================================='
\echo ''

COMMIT;

\echo ''
\echo 'ETL-194 COMMIT COMPLETE'
\echo ''