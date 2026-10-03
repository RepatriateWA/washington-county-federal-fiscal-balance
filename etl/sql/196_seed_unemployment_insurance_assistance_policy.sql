/*
====================================================================================================
ETL-196
SEED UNEMPLOYMENT INSURANCE ASSISTANCE ACCOUNTING POLICY

Assistance Listing:
    17.225 - Unemployment Insurance

Evidence:
    ETL-195A - initial AL 17.225 semantic/accounting profile
    ETL-195B - award-component partition and overlap screen

Certified FY2020-FY2024 Washington control:
    Transactions          201
    Awards                 26
    Recipients              2
    Net obligation         $937,828,270.83
    COVID                  $380,145,955.79
    IIJA                             $0.00
    Extraordinary          $380,145,955.79

ETL-195B component evidence:
    UI_INTEGRITY_FRAUD_EQUITY     $280,748,277.50
    UI_ADMINISTRATION             $164,635,629.00
    SHORT_TIME_COMPENSATION       $136,698,109.79
    COVID_PANDEMIC_UI             $132,739,982.00
    OTHER_IDENTIFIED_UI           $119,259,741.92
    RESEA                          $44,678,488.00
    TRADE_ADJUSTMENT_BENEFITS      $32,347,968.62
    initially unresolved           $26,720,074.00
                                 -----------------
    TOTAL                         $937,828,270.83

Accounting conclusion:
    AL 17.225 represents federal transfers supporting Washington's
    unemployment-compensation system and related UI activities.

    No independent WCFFBP principal accounting source was identified that
    already accounts for these AL 17.225 federal transfers.

    No focal award identifier was found under another Assistance Listing
    in the ETL-195B cross-program award screen.

    Therefore AL 17.225 is additive at the federal-transfer level.

Critical double-count rule:
    AL 17.225 includes grants that may finance unemployment-benefit payments
    as well as program administration and related activities.

    Subsequent unemployment-benefit payments or other downstream
    disbursements financed by these federal transfers MUST NOT be counted
    as a second federal inflow.

Important:
    This policy establishes statewide federal-inflow accounting treatment.

    It does NOT establish beneficiary incidence.

    It does NOT establish county incidence.

    Recipient geography must not be interpreted as claimant geography.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-196'
\echo 'SEED UNEMPLOYMENT INSURANCE ASSISTANCE ACCOUNTING POLICY'
\echo 'AL 17.225'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD EXACT CERTIFIED AL 17.225 POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m196_ui;

CREATE TEMP TABLE m196_ui AS

SELECT
    *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '17.225';


ANALYZE m196_ui;


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

FROM m196_ui;


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

    FROM m196_ui;


    IF v_tx <> 201 THEN
        RAISE EXCEPTION
            'ETL-196 PRE-CONTROL FAILED: expected 201 transactions; found %',
            v_tx;
    END IF;


    IF v_awards <> 26 THEN
        RAISE EXCEPTION
            'ETL-196 PRE-CONTROL FAILED: expected 26 awards; found %',
            v_awards;
    END IF;


    IF v_recip <> 2 THEN
        RAISE EXCEPTION
            'ETL-196 PRE-CONTROL FAILED: expected 2 recipients; found %',
            v_recip;
    END IF;


    IF ROUND(v_amount, 2) <> 937828270.83 THEN
        RAISE EXCEPTION
            'ETL-196 PRE-CONTROL FAILED: expected 937828270.83; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 380145955.79 THEN
        RAISE EXCEPTION
            'ETL-196 PRE-CONTROL FAILED: expected COVID 380145955.79; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-196 PRE-CONTROL FAILED: expected IIJA 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 380145955.79 THEN
        RAISE EXCEPTION
            'ETL-196 PRE-CONTROL FAILED: expected extraordinary 380145955.79; found %',
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-196 EXACT PRE-CONTROL PASS';

END
$$;


/*
====================================================================================================
3. FISCAL-YEAR CONTROL

Preserve the FY distribution before changing reference policy state.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FISCAL-YEAR CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year
        AS fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

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
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m196_ui

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. PRE-EXISTING PROGRAM CLASSIFICATION / MAPPING GUARD

Fail closed rather than silently creating a second current classification.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PRE-EXISTING PROGRAM CLASSIFICATION / MAPPING GUARD'
\echo '----------------------------------------------------------------------------------------------------'

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
  AND source_program_code = '17.225'
  AND valid_through_fiscal_year IS NULL;


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '17.225'
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_classification_count bigint;
    v_mapping_count        bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_classification_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '17.225'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '17.225'
      AND valid_through_fiscal_year IS NULL;


    IF v_classification_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-196 GUARD FAILED: AL 17.225 already has % current classification row(s)',
            v_classification_count;
    END IF;


    IF v_mapping_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-196 GUARD FAILED: AL 17.225 already has % current mapping row(s)',
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-196 PRE-EXISTING PROGRAM GUARD PASS';

END
$$;


/*
====================================================================================================
5. PRE-EXISTING SOURCE POLICY GUARD

A prior interrupted run must not silently create duplicate policy rows.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. PRE-EXISTING SOURCE POLICY GUARD'
\echo '----------------------------------------------------------------------------------------------------'

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

WHERE inflow_family = 'UNEMPLOYMENT_ASSISTANCE'
  AND inflow_subfamily = 'STATE_UNEMPLOYMENT_INSURANCE'
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_policy_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy_count
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'UNEMPLOYMENT_ASSISTANCE'
      AND inflow_subfamily = 'STATE_UNEMPLOYMENT_INSURANCE'
      AND valid_through_fiscal_year IS NULL;


    IF v_policy_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-196 GUARD FAILED: current UI source policy already exists; count=%',
            v_policy_count;
    END IF;


    RAISE NOTICE
        'ETL-196 PRE-EXISTING SOURCE POLICY GUARD PASS';

END
$$;


/*
====================================================================================================
6. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. INSERT SOURCE POLICY'
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

VALUES
(
    'UNEMPLOYMENT_ASSISTANCE',

    'STATE_UNEMPLOYMENT_INSURANCE',

    'NET_FEDERAL_ACTION_OBLIGATION',

    'USASPENDING_ASSISTANCE',

    'UNRESOLVED',

    ARRAY[]::text[],

    'INCLUDE',

    'ETL-195A and ETL-195B established that USAspending Assistance Listing 17.225 represents federal transfers supporting Washington''s unemployment-compensation system and related UI activities. FY2020-FY2024 certified control: 201 transactions, 26 awards, 2 recipients, and $937,828,270.83 net federal action obligation. ETL-195B partitioned the population into UI administration; UI integrity, fraud, equity, and system activities; short-time compensation; temporary COVID pandemic UI programs; RESEA; Trade Adjustment benefit support; other identified UI; and two individually reviewed awards totaling $26,720,074.00. No independent WCFFBP principal source was identified that already accounts for these federal transfers, and the cross-Assistance-Listing award-identifier screen returned zero collisions. AL 17.225 therefore enters the statewide ledger additively at net federal action obligation. Some AL 17.225 grants finance unemployment-benefit payments as well as administration. Subsequent claimant benefit payments or other downstream disbursements financed by these federal transfers must not be counted as a second federal inflow. The $23,720,074 Families First Act award and $3,000,000 UI outreach/access award were individually reviewed and did not establish a separate principal-source overlap pathway. COVID and extraordinary status remain transaction-level provenance dimensions. IIJA is not a second accounting path. Statewide beneficiary incidence and county incidence remain unresolved.',

    'ANALYSIS-196-v1',

    2020,

    NULL
);


/*
====================================================================================================
7. CAPTURE SOURCE POLICY ID
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m196_policy;

CREATE TEMP TABLE m196_policy AS

SELECT
    federal_inflow_source_policy_id

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'UNEMPLOYMENT_ASSISTANCE'
  AND inflow_subfamily = 'STATE_UNEMPLOYMENT_INSURANCE'
  AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
  AND preferred_source = 'USASPENDING_ASSISTANCE'
  AND methodology_version = 'ANALYSIS-196-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m196_policy;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-196 POLICY-ID RESOLUTION FAILED: expected 1 row; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-196 SOURCE POLICY INSERT PASS';

END
$$;


SELECT
    p.federal_inflow_source_policy_id,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    s.overlapping_sources,
    s.ledger_treatment,
    s.methodology_version

FROM m196_policy p

JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id;


/*
====================================================================================================
8. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. INSERT PROGRAM CLASSIFICATION'
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

VALUES
(
    'USASPENDING_ASSISTANCE',

    '17.225',

    'Unemployment Insurance',

    'UNEMPLOYMENT_ASSISTANCE',

    'STATE_UNEMPLOYMENT_INSURANCE',

    'NONE',

    TRUE,

    TRUE,

    'ETL-195A and ETL-195B reviewed the complete Washington FY2020-FY2024 AL 17.225 population. The program is heterogeneous but all observed components represent federal transfers into Washington''s UI system or closely related federal UI activities. ETL-195B found no award identifier shared with another Assistance Listing and no independently acquired WCFFBP principal source accounting for the same transfer population. COVID/extraordinary activity is preserved separately at transaction level. The initially unresolved $23,720,074 Families First Act award and $3,000,000 UI outreach/access award were individually reviewed and do not establish a separate overlap pathway. Downstream unemployment-benefit payments financed by these federal transfers are not a second federal inflow.',

    'ANALYSIS-196-v1',

    2020,

    NULL
);


/*
====================================================================================================
9. CAPTURE PROGRAM CLASSIFICATION ID
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m196_classification;

CREATE TEMP TABLE m196_classification AS

SELECT
    federal_inflow_program_classification_id

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '17.225'
  AND inflow_family = 'UNEMPLOYMENT_ASSISTANCE'
  AND inflow_subfamily = 'STATE_UNEMPLOYMENT_INSURANCE'
  AND methodology_version = 'ANALYSIS-196-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m196_classification;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-196 CLASSIFICATION-ID RESOLUTION FAILED: expected 1 row; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-196 PROGRAM CLASSIFICATION INSERT PASS';

END
$$;


SELECT
    c.federal_inflow_program_classification_id,
    p.source_system,
    p.source_program_code,
    p.source_program_title,
    p.inflow_family,
    p.inflow_subfamily,
    p.overlap_risk,
    p.covid_relevance,
    p.extraordinary_relevance,
    p.methodology_version

FROM m196_classification c

JOIN reference.federal_inflow_program_classification p
  ON p.federal_inflow_program_classification_id =
     c.federal_inflow_program_classification_id;


/*
====================================================================================================
10. INSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. INSERT PROGRAM -> POLICY MAPPING'
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

    '17.225',

    p.federal_inflow_source_policy_id,

    'INCLUDE_ADDITIVE',

    'ETL-195A/195B found no identified overlap pathway with another WCFFBP principal accounting source. USAspending AL 17.225 net federal action obligations are therefore additive federal inflow. This disposition applies to the federal transfer only. Subsequent unemployment-benefit payments and other downstream disbursements financed by the same transfer must not be counted again.',

    'ANALYSIS-196-v1',

    2020,

    NULL

FROM m196_policy p;


/*
====================================================================================================
11. CAPTURE MAPPING ID
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m196_mapping;

CREATE TEMP TABLE m196_mapping AS

SELECT
    federal_inflow_program_policy_mapping_id

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '17.225'
  AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
  AND methodology_version = 'ANALYSIS-196-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m196_mapping;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-196 MAPPING-ID RESOLUTION FAILED: expected 1 row; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-196 PROGRAM MAPPING INSERT PASS';

END
$$;


SELECT
    m.federal_inflow_program_policy_mapping_id,
    p.source_system,
    p.source_program_code,
    p.federal_inflow_source_policy_id,
    p.resolved_accounting_disposition,
    p.methodology_version

FROM m196_mapping m

JOIN reference.federal_inflow_program_policy_mapping p
  ON p.federal_inflow_program_policy_mapping_id =
     m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
12. RECONSTRUCT EFFECTIVE ACCOUNTING DISPOSITION

Do not assume the insert means the ledger resolves correctly.

Reconstruct the effective program-level disposition from persisted reference
objects.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m196_effective;

CREATE TEMP TABLE m196_effective AS

SELECT
    l.*,

    pcm.resolved_accounting_disposition,

    sp.federal_inflow_source_policy_id,
    sp.ledger_treatment,
    sp.preferred_source,
    sp.allocation_source

FROM m196_ui l

LEFT JOIN reference.federal_inflow_program_policy_mapping pcm
  ON pcm.source_system = 'USASPENDING_ASSISTANCE'
 AND pcm.source_program_code = l.cfda_number
 AND pcm.valid_from_fiscal_year <= l.action_date_fiscal_year
 AND (
        pcm.valid_through_fiscal_year IS NULL
        OR pcm.valid_through_fiscal_year >= l.action_date_fiscal_year
     )

LEFT JOIN reference.federal_inflow_source_policy sp
  ON sp.federal_inflow_source_policy_id =
     pcm.federal_inflow_source_policy_id;


/*
====================================================================================================
13. EFFECTIVE DISPOSITION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EFFECTIVE DISPOSITION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        resolved_accounting_disposition,
        'UNRESOLVED'
    ) AS resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

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

FROM m196_effective

GROUP BY
    COALESCE(
        resolved_accounting_disposition,
        'UNRESOLVED'
    )

ORDER BY resolved_accounting_disposition;


DO $$
DECLARE
    v_total_tx         bigint;
    v_additive_tx      bigint;
    v_total_amount     numeric;
    v_additive_amount  numeric;
    v_unresolved_tx    bigint;
    v_bad_policy_tx    bigint;
BEGIN

    SELECT
        COUNT(*),

        COUNT(*) FILTER
        (
            WHERE resolved_accounting_disposition =
                  'INCLUDE_ADDITIVE'
        ),

        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(SUM(federal_action_obligation) FILTER
        (
            WHERE resolved_accounting_disposition =
                  'INCLUDE_ADDITIVE'
        ), 0),

        COUNT(*) FILTER
        (
            WHERE resolved_accounting_disposition IS NULL
        ),

        COUNT(*) FILTER
        (
            WHERE resolved_accounting_disposition =
                  'INCLUDE_ADDITIVE'
              AND (
                     ledger_treatment <> 'INCLUDE'
                  OR preferred_source <> 'USASPENDING_ASSISTANCE'
                  OR allocation_source <> 'UNRESOLVED'
              )
        )

    INTO
        v_total_tx,
        v_additive_tx,
        v_total_amount,
        v_additive_amount,
        v_unresolved_tx,
        v_bad_policy_tx

    FROM m196_effective;


    IF v_total_tx <> 201 THEN
        RAISE EXCEPTION
            'ETL-196 EFFECTIVE CONTROL FAILED: expected 201 total transactions; found %',
            v_total_tx;
    END IF;


    IF v_additive_tx <> 201 THEN
        RAISE EXCEPTION
            'ETL-196 EFFECTIVE CONTROL FAILED: expected all 201 transactions INCLUDE_ADDITIVE; found %',
            v_additive_tx;
    END IF;


    IF ROUND(v_total_amount, 2) <> 937828270.83 THEN
        RAISE EXCEPTION
            'ETL-196 EFFECTIVE CONTROL FAILED: total amount expected 937828270.83; found %',
            ROUND(v_total_amount, 2);
    END IF;


    IF ROUND(v_additive_amount, 2) <> 937828270.83 THEN
        RAISE EXCEPTION
            'ETL-196 EFFECTIVE CONTROL FAILED: additive amount expected 937828270.83; found %',
            ROUND(v_additive_amount, 2);
    END IF;


    IF v_unresolved_tx <> 0 THEN
        RAISE EXCEPTION
            'ETL-196 EFFECTIVE CONTROL FAILED: % transaction(s) remain unresolved',
            v_unresolved_tx;
    END IF;


    IF v_bad_policy_tx <> 0 THEN
        RAISE EXCEPTION
            'ETL-196 EFFECTIVE CONTROL FAILED: % transaction(s) resolved through unexpected policy attributes',
            v_bad_policy_tx;
    END IF;


    RAISE NOTICE
        'ETL-196 EFFECTIVE DISPOSITION PASS: all 201 transactions / $937,828,270.83 INCLUDE_ADDITIVE';

END
$$;


/*
====================================================================================================
14. PROVENANCE PRESERVATION CONTROL

IIJA, COVID, and extraordinary are orthogonal reporting dimensions.
They must not be altered by accounting classification.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. PROVENANCE PRESERVATION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    is_covid,
    is_iija,
    is_extraordinary,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m196_effective

GROUP BY
    is_covid,
    is_iija,
    is_extraordinary

ORDER BY
    is_covid DESC,
    is_iija DESC,
    is_extraordinary DESC;


DO $$
DECLARE
    v_covid numeric;
    v_iija  numeric;
    v_extra numeric;
BEGIN

    SELECT
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
        v_covid,
        v_iija,
        v_extra

    FROM m196_effective;


    IF ROUND(v_covid, 2) <> 380145955.79
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 380145955.79
    THEN
        RAISE EXCEPTION
            'ETL-196 PROVENANCE CONTROL FAILED: COVID=% IIJA=% extraordinary=%',
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-196 PROVENANCE PRESERVATION PASS';

END
$$;


/*
====================================================================================================
15. PERSISTED OBJECT CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. PERSISTED OBJECT CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    sp.federal_inflow_source_policy_id,
    sp.inflow_family,
    sp.inflow_subfamily,
    sp.accounting_measure,
    sp.preferred_source,
    sp.allocation_source,
    sp.overlapping_sources,
    sp.ledger_treatment,
    sp.methodology_version,

    pc.federal_inflow_program_classification_id,
    pc.source_program_code,
    pc.source_program_title,
    pc.overlap_risk,
    pc.covid_relevance,
    pc.extraordinary_relevance,

    pm.federal_inflow_program_policy_mapping_id,
    pm.resolved_accounting_disposition

FROM reference.federal_inflow_source_policy sp

JOIN reference.federal_inflow_program_policy_mapping pm
  ON pm.federal_inflow_source_policy_id =
     sp.federal_inflow_source_policy_id
 AND pm.source_system = 'USASPENDING_ASSISTANCE'
 AND pm.source_program_code = '17.225'
 AND pm.methodology_version = 'ANALYSIS-196-v1'
 AND pm.valid_through_fiscal_year IS NULL

JOIN reference.federal_inflow_program_classification pc
  ON pc.source_system = pm.source_system
 AND pc.source_program_code = pm.source_program_code
 AND pc.methodology_version = 'ANALYSIS-196-v1'
 AND pc.valid_through_fiscal_year IS NULL

WHERE sp.inflow_family = 'UNEMPLOYMENT_ASSISTANCE'
  AND sp.inflow_subfamily = 'STATE_UNEMPLOYMENT_INSURANCE'
  AND sp.methodology_version = 'ANALYSIS-196-v1'
  AND sp.valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_policy_count        bigint;
    v_classification_count bigint;
    v_mapping_count       bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy_count
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'UNEMPLOYMENT_ASSISTANCE'
      AND inflow_subfamily = 'STATE_UNEMPLOYMENT_INSURANCE'
      AND methodology_version = 'ANALYSIS-196-v1'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_classification_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '17.225'
      AND methodology_version = 'ANALYSIS-196-v1'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '17.225'
      AND methodology_version = 'ANALYSIS-196-v1'
      AND valid_through_fiscal_year IS NULL;


    IF v_policy_count <> 1
       OR v_classification_count <> 1
       OR v_mapping_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-196 PERSISTED OBJECT CERTIFICATION FAILED: policy=% classification=% mapping=%',
            v_policy_count,
            v_classification_count,
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-196 PERSISTED OBJECT CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
16. FINAL EXACT ACCOUNTING CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FINAL EXACT ACCOUNTING CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,

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

FROM m196_effective

GROUP BY resolved_accounting_disposition;


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

    FROM m196_effective

    WHERE resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';


    IF v_tx <> 201
       OR v_awards <> 26
       OR v_recip <> 2
       OR ROUND(v_amount, 2) <> 937828270.83
       OR ROUND(v_covid, 2) <> 380145955.79
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 380145955.79
    THEN
        RAISE EXCEPTION
            'ETL-196 FINAL CERTIFICATION FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-196 FINAL CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
17. COMMIT
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-196 CERTIFICATION COMPLETE'
\echo ''
\echo 'Accounting treatment:'
\echo '  UNEMPLOYMENT_ASSISTANCE / STATE_UNEMPLOYMENT_INSURANCE'
\echo '  USASPENDING_ASSISTANCE'
\echo '  NET_FEDERAL_ACTION_OBLIGATION'
\echo '  INCLUDE_ADDITIVE'
\echo '  allocation_source = UNRESOLVED'
\echo ''
\echo 'Certified FY2020-FY2024 population:'
\echo '  201 transactions'
\echo '   26 awards'
\echo '    2 recipients'
\echo '  $937,828,270.83 net federal action obligation'
\echo '  $380,145,955.79 COVID / extraordinary'
\echo '  $0 IIJA'
\echo ''
\echo 'Double-count prohibition:'
\echo '  downstream unemployment-benefit payments or other disbursements financed'
\echo '  by these federal transfers are NOT a second federal inflow.'
\echo ''
\echo 'Statewide beneficiary incidence unresolved.'
\echo 'County incidence unresolved.'
\echo '===================================================================================================='
\echo ''

COMMIT;

\echo ''
\echo 'ETL-196 COMMIT COMPLETE'
\echo ''