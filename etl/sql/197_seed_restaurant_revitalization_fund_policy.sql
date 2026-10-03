/*
====================================================================================================
ETL-197
SEED RESTAURANT REVITALIZATION FUND ACCOUNTING POLICY

Assistance Listing:
    59.078 - Restaurant Revitalization Fund

Evidence:
    ETL-196A - Restaurant Revitalization Fund statewide accounting profile

Certified FY2020-FY2024 Washington control:
    Transactions        3,757
    Awards              3,491
    Recipients          3,252
    Net obligation      $918,909,395.35
    COVID               $918,909,395.35
    IIJA                          $0.00
    Extraordinary       $918,909,395.35

ETL-196A findings:
    - All transactions funded and awarded by the Small Business Administration.
    - All transactions use assistance type 06:
      direct payment for specified use / non-reimbursable financial aid.
    - Positive obligations:  $975,324,535.27
    - Negative adjustments:  -$56,415,139.92
    - Net obligation:         $918,909,395.35
    - 3,489 of 3,491 awards explicitly identify the
      Restaurant Revitalization Fund.
    - The remaining two awards explicitly describe direct restaurant-relief
      payments for payroll, rent, debt service, utilities, outdoor seating,
      supplies, and food/beverage costs.
    - No focal RRF award identifier appears under another Assistance Listing.
    - Same-recipient participation in other SBA programs does not establish
      duplicate federal dollars.
    - No existing WCFFBP principal source was identified that already accounts
      for these RRF federal transfers.

Accounting conclusion:
    USAspending AL 59.078 is the principal statewide accounting source for
    Restaurant Revitalization Fund assistance.

    Count the federal transfer once at net federal action obligation.

Critical double-count rule:
    Subsequent expenditures by recipient businesses financed from RRF awards
    are uses of the federal transfer and MUST NOT be counted as additional
    federal inflow.

Important:
    COVID / extraordinary status is an orthogonal provenance dimension.

    IIJA is not a second accounting path.

    Recipient geography does not by itself establish county economic incidence.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-197'
\echo 'SEED RESTAURANT REVITALIZATION FUND ACCOUNTING POLICY'
\echo 'AL 59.078'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD EXACT CERTIFIED AL 59.078 POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197_rrf;

CREATE TEMP TABLE m197_rrf AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '59.078';


ANALYZE m197_rrf;


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

FROM m197_rrf;


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
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_extraordinary
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

    FROM m197_rrf;


    IF v_tx <> 3757 THEN
        RAISE EXCEPTION
            'ETL-197 PRE-CONTROL FAILED: expected 3757 transactions; found %',
            v_tx;
    END IF;


    IF v_awards <> 3491 THEN
        RAISE EXCEPTION
            'ETL-197 PRE-CONTROL FAILED: expected 3491 awards; found %',
            v_awards;
    END IF;


    IF v_recip <> 3252 THEN
        RAISE EXCEPTION
            'ETL-197 PRE-CONTROL FAILED: expected 3252 recipients; found %',
            v_recip;
    END IF;


    IF ROUND(v_amount, 2) <> 918909395.35 THEN
        RAISE EXCEPTION
            'ETL-197 PRE-CONTROL FAILED: expected 918909395.35; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 918909395.35 THEN
        RAISE EXCEPTION
            'ETL-197 PRE-CONTROL FAILED: expected COVID 918909395.35; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-197 PRE-CONTROL FAILED: expected IIJA 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 918909395.35 THEN
        RAISE EXCEPTION
            'ETL-197 PRE-CONTROL FAILED: expected extraordinary 918909395.35; found %',
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-197 EXACT PRE-CONTROL PASS';

END
$$;


/*
====================================================================================================
3. TRANSACTION-SIGN CONTROL

ETL-196A established that net accounting is essential because RRF includes
material negative adjustments.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. TRANSACTION-SIGN CONTROL'
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

FROM m197_rrf

GROUP BY 1
ORDER BY 1;


DO $$
DECLARE
    v_positive numeric;
    v_negative numeric;
BEGIN

    SELECT
        COALESCE(SUM(federal_action_obligation)
            FILTER (WHERE federal_action_obligation > 0), 0),

        COALESCE(SUM(federal_action_obligation)
            FILTER (WHERE federal_action_obligation < 0), 0)

    INTO
        v_positive,
        v_negative

    FROM m197_rrf;


    IF ROUND(v_positive, 2) <> 975324535.27 THEN
        RAISE EXCEPTION
            'ETL-197 SIGN CONTROL FAILED: positive expected 975324535.27; found %',
            ROUND(v_positive, 2);
    END IF;


    IF ROUND(v_negative, 2) <> -56415139.92 THEN
        RAISE EXCEPTION
            'ETL-197 SIGN CONTROL FAILED: negative expected -56415139.92; found %',
            ROUND(v_negative, 2);
    END IF;


    IF ROUND(v_positive + v_negative, 2) <> 918909395.35 THEN
        RAISE EXCEPTION
            'ETL-197 SIGN CONTROL FAILED: net expected 918909395.35; found %',
            ROUND(v_positive + v_negative, 2);
    END IF;


    RAISE NOTICE
        'ETL-197 TRANSACTION-SIGN CONTROL PASS';

END
$$;


/*
====================================================================================================
4. PRE-EXISTING PROGRAM CLASSIFICATION / MAPPING GUARD
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
    inflow_family,
    inflow_subfamily,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '59.078'
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
  AND source_program_code = '59.078'
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
      AND source_program_code = '59.078'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '59.078'
      AND valid_through_fiscal_year IS NULL;


    IF v_classification_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-197 GUARD FAILED: AL 59.078 already has % current classification row(s)',
            v_classification_count;
    END IF;


    IF v_mapping_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-197 GUARD FAILED: AL 59.078 already has % current mapping row(s)',
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-197 PRE-EXISTING PROGRAM GUARD PASS';

END
$$;


/*
====================================================================================================
5. PRE-EXISTING SOURCE POLICY GUARD
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
    ledger_treatment,
    methodology_version

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'BUSINESS_ASSISTANCE'
  AND inflow_subfamily = 'RESTAURANT_REVITALIZATION_FUND'
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_policy_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy_count
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'BUSINESS_ASSISTANCE'
      AND inflow_subfamily = 'RESTAURANT_REVITALIZATION_FUND'
      AND valid_through_fiscal_year IS NULL;


    IF v_policy_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-197 GUARD FAILED: current RRF source policy already exists; count=%',
            v_policy_count;
    END IF;


    RAISE NOTICE
        'ETL-197 PRE-EXISTING SOURCE POLICY GUARD PASS';

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
    'BUSINESS_ASSISTANCE',

    'RESTAURANT_REVITALIZATION_FUND',

    'NET_FEDERAL_ACTION_OBLIGATION',

    'USASPENDING_ASSISTANCE',

    'UNRESOLVED',

    ARRAY[]::text[],

    'INCLUDE',

    'ETL-196A established that USAspending Assistance Listing 59.078 represents direct federal Restaurant Revitalization Fund assistance to Washington recipients. The certified FY2020-FY2024 population contains 3,757 transactions, 3,491 awards, 3,252 recipients, and $918,909,395.35 net federal action obligation. The population contains $975,324,535.27 positive obligations and -$56,415,139.92 negative adjustments, establishing net federal action obligation as the appropriate accounting measure. All net dollars are COVID/extraordinary and none are IIJA. Of 3,491 awards, 3,489 explicitly identify the Restaurant Revitalization Fund; the remaining two explicitly describe direct restaurant-relief payments for eligible business costs. No focal RRF award identifier appeared under another Assistance Listing. Some RRF recipients also participated in other SBA programs, but shared recipient identity does not establish duplicate federal dollars. No independent WCFFBP principal source was identified that already accounts for these RRF transfers. RRF awards therefore enter the statewide ledger additively. Subsequent expenditures by recipient businesses financed from RRF awards, including payroll, rent, utilities, debt service, supplies, construction, and food or beverage purchases, are downstream uses of the federal transfer and must not be counted as additional federal inflow. Recipient geography does not by itself establish county economic incidence.',

    'ANALYSIS-197-v1',

    2020,

    NULL
);


/*
====================================================================================================
7. CAPTURE AND CERTIFY SOURCE POLICY
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197_policy;

CREATE TEMP TABLE m197_policy AS

SELECT
    federal_inflow_source_policy_id

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'BUSINESS_ASSISTANCE'
  AND inflow_subfamily = 'RESTAURANT_REVITALIZATION_FUND'
  AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
  AND preferred_source = 'USASPENDING_ASSISTANCE'
  AND methodology_version = 'ANALYSIS-197-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m197_policy;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-197 POLICY-ID RESOLUTION FAILED: expected 1 row; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-197 SOURCE POLICY INSERT PASS';

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

FROM m197_policy p

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

    '59.078',

    'Restaurant Revitalization Fund',

    'BUSINESS_ASSISTANCE',

    'RESTAURANT_REVITALIZATION_FUND',

    'NONE',

    TRUE,

    TRUE,

    'ETL-196A reviewed the complete Washington FY2020-FY2024 AL 59.078 population. All transactions are SBA direct payments for specified use. The full $918,909,395.35 net obligation is COVID/extraordinary and $0 is IIJA. Award descriptions establish Restaurant Revitalization Fund semantics for the complete population. No focal award identifier appears under another Assistance Listing. Shared recipient participation in other SBA programs is not evidence of duplicate award dollars. No independently acquired WCFFBP principal source was identified that accounts for the same RRF transfer population. Downstream recipient expenditures financed by RRF awards are uses of these transfers and are not additional federal inflow.',

    'ANALYSIS-197-v1',

    2020,

    NULL
);


/*
====================================================================================================
9. CAPTURE AND CERTIFY PROGRAM CLASSIFICATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197_classification;

CREATE TEMP TABLE m197_classification AS

SELECT
    federal_inflow_program_classification_id

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '59.078'
  AND inflow_family = 'BUSINESS_ASSISTANCE'
  AND inflow_subfamily = 'RESTAURANT_REVITALIZATION_FUND'
  AND methodology_version = 'ANALYSIS-197-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m197_classification;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-197 CLASSIFICATION-ID RESOLUTION FAILED: expected 1 row; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-197 PROGRAM CLASSIFICATION INSERT PASS';

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

FROM m197_classification c

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

    '59.078',

    p.federal_inflow_source_policy_id,

    'INCLUDE_ADDITIVE',

    'ETL-196A identified no overlap pathway with another WCFFBP principal accounting source. AL 59.078 net federal action obligations therefore represent additive Restaurant Revitalization Fund inflow. Same-recipient participation in other SBA programs does not constitute duplicate-dollar evidence. Downstream expenditures financed from an RRF award are uses of the transfer and must not be counted again.',

    'ANALYSIS-197-v1',

    2020,

    NULL

FROM m197_policy p;


/*
====================================================================================================
11. CAPTURE AND CERTIFY MAPPING
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197_mapping;

CREATE TEMP TABLE m197_mapping AS

SELECT
    federal_inflow_program_policy_mapping_id

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '59.078'
  AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
  AND methodology_version = 'ANALYSIS-197-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m197_mapping;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-197 MAPPING-ID RESOLUTION FAILED: expected 1 row; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-197 PROGRAM MAPPING INSERT PASS';

END
$$;


SELECT
    m.federal_inflow_program_policy_mapping_id,
    p.source_system,
    p.source_program_code,
    p.federal_inflow_source_policy_id,
    p.resolved_accounting_disposition,
    p.methodology_version

FROM m197_mapping m

JOIN reference.federal_inflow_program_policy_mapping p
  ON p.federal_inflow_program_policy_mapping_id =
     m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
12. RECONSTRUCT EFFECTIVE ACCOUNTING DISPOSITION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197_effective;

CREATE TEMP TABLE m197_effective AS

SELECT
    l.*,

    pm.resolved_accounting_disposition,

    sp.federal_inflow_source_policy_id,
    sp.ledger_treatment,
    sp.preferred_source,
    sp.allocation_source

FROM m197_rrf l

LEFT JOIN reference.federal_inflow_program_policy_mapping pm
  ON pm.source_system = 'USASPENDING_ASSISTANCE'
 AND pm.source_program_code = l.cfda_number
 AND pm.valid_from_fiscal_year <= l.action_date_fiscal_year
 AND (
        pm.valid_through_fiscal_year IS NULL
        OR pm.valid_through_fiscal_year >= l.action_date_fiscal_year
     )

LEFT JOIN reference.federal_inflow_source_policy sp
  ON sp.federal_inflow_source_policy_id =
     pm.federal_inflow_source_policy_id;


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

FROM m197_effective

GROUP BY
    COALESCE(
        resolved_accounting_disposition,
        'UNRESOLVED'
    );


DO $$
DECLARE
    v_total_tx        bigint;
    v_additive_tx     bigint;
    v_total_amount    numeric;
    v_additive_amount numeric;
    v_unresolved_tx   bigint;
    v_bad_policy_tx   bigint;
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

    FROM m197_effective;


    IF v_total_tx <> 3757 THEN
        RAISE EXCEPTION
            'ETL-197 EFFECTIVE CONTROL FAILED: expected 3757 transactions; found %',
            v_total_tx;
    END IF;


    IF v_additive_tx <> 3757 THEN
        RAISE EXCEPTION
            'ETL-197 EFFECTIVE CONTROL FAILED: expected all 3757 transactions INCLUDE_ADDITIVE; found %',
            v_additive_tx;
    END IF;


    IF ROUND(v_total_amount, 2) <> 918909395.35 THEN
        RAISE EXCEPTION
            'ETL-197 EFFECTIVE CONTROL FAILED: expected total 918909395.35; found %',
            ROUND(v_total_amount, 2);
    END IF;


    IF ROUND(v_additive_amount, 2) <> 918909395.35 THEN
        RAISE EXCEPTION
            'ETL-197 EFFECTIVE CONTROL FAILED: expected additive 918909395.35; found %',
            ROUND(v_additive_amount, 2);
    END IF;


    IF v_unresolved_tx <> 0 THEN
        RAISE EXCEPTION
            'ETL-197 EFFECTIVE CONTROL FAILED: % transaction(s) unresolved',
            v_unresolved_tx;
    END IF;


    IF v_bad_policy_tx <> 0 THEN
        RAISE EXCEPTION
            'ETL-197 EFFECTIVE CONTROL FAILED: % transaction(s) resolved through unexpected policy attributes',
            v_bad_policy_tx;
    END IF;


    RAISE NOTICE
        'ETL-197 EFFECTIVE DISPOSITION PASS: all 3757 transactions / $918,909,395.35 INCLUDE_ADDITIVE';

END
$$;


/*
====================================================================================================
14. PROVENANCE PRESERVATION CONTROL
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

FROM m197_effective

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
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0)

    INTO
        v_covid,
        v_iija,
        v_extra

    FROM m197_effective;


    IF ROUND(v_covid, 2) <> 918909395.35
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 918909395.35
    THEN
        RAISE EXCEPTION
            'ETL-197 PROVENANCE CONTROL FAILED: COVID=% IIJA=% extraordinary=%',
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-197 PROVENANCE PRESERVATION PASS';

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
 AND pm.source_program_code = '59.078'
 AND pm.methodology_version = 'ANALYSIS-197-v1'
 AND pm.valid_through_fiscal_year IS NULL

JOIN reference.federal_inflow_program_classification pc
  ON pc.source_system = pm.source_system
 AND pc.source_program_code = pm.source_program_code
 AND pc.methodology_version = 'ANALYSIS-197-v1'
 AND pc.valid_through_fiscal_year IS NULL

WHERE sp.inflow_family = 'BUSINESS_ASSISTANCE'
  AND sp.inflow_subfamily = 'RESTAURANT_REVITALIZATION_FUND'
  AND sp.methodology_version = 'ANALYSIS-197-v1'
  AND sp.valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_policy_count         bigint;
    v_classification_count bigint;
    v_mapping_count        bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy_count
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'BUSINESS_ASSISTANCE'
      AND inflow_subfamily = 'RESTAURANT_REVITALIZATION_FUND'
      AND methodology_version = 'ANALYSIS-197-v1'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_classification_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '59.078'
      AND methodology_version = 'ANALYSIS-197-v1'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '59.078'
      AND methodology_version = 'ANALYSIS-197-v1'
      AND valid_through_fiscal_year IS NULL;


    IF v_policy_count <> 1
       OR v_classification_count <> 1
       OR v_mapping_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-197 PERSISTED OBJECT CERTIFICATION FAILED: policy=% classification=% mapping=%',
            v_policy_count,
            v_classification_count,
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-197 PERSISTED OBJECT CERTIFICATION PASS';

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
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m197_effective

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
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_extraordinary
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

    FROM m197_effective

    WHERE resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';


    IF v_tx <> 3757
       OR v_awards <> 3491
       OR v_recip <> 3252
       OR ROUND(v_amount, 2) <> 918909395.35
       OR ROUND(v_covid, 2) <> 918909395.35
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 918909395.35
    THEN
        RAISE EXCEPTION
            'ETL-197 FINAL CERTIFICATION FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-197 FINAL CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
17. COMMIT
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-197 CERTIFICATION COMPLETE'
\echo ''
\echo 'Accounting treatment:'
\echo '  BUSINESS_ASSISTANCE / RESTAURANT_REVITALIZATION_FUND'
\echo '  USASPENDING_ASSISTANCE'
\echo '  NET_FEDERAL_ACTION_OBLIGATION'
\echo '  INCLUDE_ADDITIVE'
\echo '  allocation_source = UNRESOLVED'
\echo ''
\echo 'Certified FY2020-FY2024 population:'
\echo '  3,757 transactions'
\echo '  3,491 awards'
\echo '  3,252 recipients'
\echo '  $918,909,395.35 net federal action obligation'
\echo '  $918,909,395.35 COVID / extraordinary'
\echo '  $0 IIJA'
\echo ''
\echo 'Double-count prohibition:'
\echo '  downstream expenditures financed by RRF awards are uses of the'
\echo '  federal transfer and are NOT a second federal inflow.'
\echo ''
\echo 'County economic incidence unresolved.'
\echo '===================================================================================================='
\echo ''

COMMIT;

\echo ''
\echo 'ETL-197 COMMIT COMPLETE'
\echo ''