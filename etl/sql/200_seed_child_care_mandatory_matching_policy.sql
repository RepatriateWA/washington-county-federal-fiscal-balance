\echo ''
\echo '===================================================================================================='
\echo 'ETL-200'
\echo 'SEED CHILD CARE MANDATORY / MATCHING FUNDS ACCOUNTING POLICY'
\echo 'AL 93.596'
\echo '===================================================================================================='
\echo ''

\set ON_ERROR_STOP on

BEGIN;


/*
====================================================================================================
PURPOSE

Persist the WCFFBP statewide accounting treatment for:

    Assistance Listing 93.596
    CHILD CARE MANDATORY AND MATCHING FUNDS
    OF THE CHILD CARE AND DEVELOPMENT FUND

Accounting decision
-------------------
Resolved disposition : INCLUDE_ADDITIVE
Accounting measure   : NET_FEDERAL_ACTION_OBLIGATION
Preferred source     : USASPENDING_ASSISTANCE
County allocation    : UNRESOLVED
Methodology          : ANALYSIS-200-v1

ETL-199A / ETL-199B controls
----------------------------
    Transactions      : 950
    Awards            : 271
    Recipients        : 28
    Net obligation    : $718,504,226.60
    COVID             : $19,429.00
    IIJA              : $0.00
    Extraordinary     : $19,429.00

ETL-199B cross-list reconciliation
----------------------------------
Seven focal award identifiers also occur under other Assistance Listings.

AL 93.596 dollars in those seven awards:
    $365,607.59

ETL-199B found:
    0 nonzero same-award / same-date / same-amount
    cross-program transaction collisions.

The evidence supports treating the shared identifiers as administrative /
P.L. 102-477 cross-listing rather than duplicate federal dollars.

Double-count firewall
---------------------
AL 93.596 mandatory/matching CCDF obligations are distinct from:
    AL 93.575 discretionary CCDBG obligations; and
    AL 93.558 TANF obligations.

Common administration, recipients, P.L. 102-477 plans, or award identifiers
do not by themselves establish duplicate federal dollars.

Downstream expenditures, benefits, or transfers financed by these federal
obligations must not be counted as a second federal inflow.

This migration makes no county-incidence inference.

IMPORTANT IMPLEMENTATION NOTE
-----------------------------
All transaction-level controls below use:

    analysis.v_certified_assistance_ledger

and the exact field names proven by ETL-199B.

Persistent writes are confined to the reference policy/classification tables.
====================================================================================================
*/


/*
====================================================================================================
1. BUILD CERTIFIED FOCAL POPULATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. BUILD CERTIFIED AL 93.596 FOCAL POPULATION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m200_focal;

CREATE TEMP TABLE m200_focal AS
SELECT
    l.*,

    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ) AS diagnostic_award_identifier

FROM analysis.v_certified_assistance_ledger AS l

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number = '93.596';

ANALYZE m200_focal;


/*
====================================================================================================
2. PRE-MIGRATION HARD CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. PRE-MIGRATION HARD CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT diagnostic_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT recipient_id
    ) AS recipient_count,

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

FROM m200_focal;


/*
====================================================================================================
3. FAIL-CLOSED PRE-MIGRATION ASSERTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FAIL-CLOSED PRE-MIGRATION ASSERTION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_tx             bigint;
    v_awards         bigint;
    v_recipients     bigint;
    v_net            numeric;
    v_covid          numeric;
    v_iija           numeric;
    v_extraordinary  numeric;

BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT diagnostic_award_identifier
        ),

        COUNT(
            DISTINCT recipient_id
        ),

        ROUND(
            SUM(federal_action_obligation)::numeric,
            2
        ),

        ROUND(SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric, 2),

        ROUND(SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric, 2),

        ROUND(SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric, 2)

    INTO
        v_tx,
        v_awards,
        v_recipients,
        v_net,
        v_covid,
        v_iija,
        v_extraordinary

    FROM m200_focal;


    IF v_tx <> 950 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected 950 transactions, found %',
            v_tx;
    END IF;


    IF v_awards <> 271 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected 271 awards, found %',
            v_awards;
    END IF;


    IF v_recipients <> 28 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected 28 recipients, found %',
            v_recipients;
    END IF;


    IF v_net <> 718504226.60 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected net obligation 718504226.60, found %',
            v_net;
    END IF;


    IF v_covid <> 19429.00 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected COVID amount 19429.00, found %',
            v_covid;
    END IF;


    IF v_iija <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected IIJA amount 0.00, found %',
            v_iija;
    END IF;


    IF v_extraordinary <> 19429.00 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected extraordinary amount 19429.00, found %',
            v_extraordinary;
    END IF;


    RAISE NOTICE
        'ETL-200 PASS: pre-migration hard control reproduced exactly.';

END
$$;


/*
====================================================================================================
4. PRE-MIGRATION COLLISION GUARD

Migration 200 must not silently coexist with another classification or
mapping for AL 93.596.

The failed earlier ETL-200 execution never reached an INSERT, so these
counts should both be zero.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PRE-MIGRATION EXISTING 93.596 CLASSIFICATION / MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    methodology_version
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.596'
ORDER BY federal_inflow_program_classification_id;


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.596'
ORDER BY federal_inflow_program_policy_mapping_id;


DO $$
DECLARE
    v_classification_count bigint;
    v_mapping_count        bigint;

BEGIN

    SELECT COUNT(*)
    INTO v_classification_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.596';


    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.596';


    IF v_classification_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: AL 93.596 already has % program classification row(s). Review before proceeding.',
            v_classification_count;
    END IF;


    IF v_mapping_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: AL 93.596 already has % program-policy mapping row(s). Review before proceeding.',
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-200 PASS: no pre-existing AL 93.596 classification or mapping.';

END
$$;


/*
====================================================================================================
5. SEED SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. SEED SOURCE POLICY'
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
    'CHILD_CARE_ASSISTANCE',

    'CHILD_CARE_MANDATORY_MATCHING',

    'NET_FEDERAL_ACTION_OBLIGATION',

    'USASPENDING_ASSISTANCE',

    'UNRESOLVED',

    ARRAY[]::text[],

    'INCLUDE',

    'USAspending assistance transactions are the principal statewide accounting source for AL 93.596. ETL-199B reconciled seven cross-listed award identifiers and found zero nonzero same-award/same-date/same-amount cross-program transaction collisions. Shared P.L. 102-477 administration does not establish duplicate federal dollars. AL 93.596 mandatory/matching CCDF obligations are accounted separately from AL 93.575 discretionary CCDBG and AL 93.558 TANF obligations. Downstream uses of these federal transfers are not additional federal inflows.',

    'ANALYSIS-200-v1',

    2020,

    2024

WHERE NOT EXISTS
(
    SELECT 1
    FROM reference.federal_inflow_source_policy

    WHERE inflow_family =
          'CHILD_CARE_ASSISTANCE'

      AND inflow_subfamily =
          'CHILD_CARE_MANDATORY_MATCHING'

      AND methodology_version =
          'ANALYSIS-200-v1'
);


\echo ''
\echo 'Source-policy rows inserted:'
SELECT COUNT(*) AS analysis_200_source_policy_count
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'CHILD_CARE_ASSISTANCE'
  AND inflow_subfamily = 'CHILD_CARE_MANDATORY_MATCHING'
  AND methodology_version = 'ANALYSIS-200-v1';


/*
====================================================================================================
6. RESOLVE AND ASSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. RESOLVE SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m200_policy;

CREATE TEMP TABLE m200_policy AS
SELECT
    federal_inflow_source_policy_id
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'CHILD_CARE_ASSISTANCE'
  AND inflow_subfamily = 'CHILD_CARE_MANDATORY_MATCHING'
  AND methodology_version = 'ANALYSIS-200-v1';


SELECT *
FROM m200_policy;


DO $$
DECLARE
    v_count bigint;

BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m200_policy;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected exactly one ANALYSIS-200-v1 source policy, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-200 PASS: exactly one source policy resolved.';

END
$$;


/*
====================================================================================================
7. SEED PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. SEED PROGRAM CLASSIFICATION'
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

    '93.596',

    'CHILD CARE MANDATORY AND MATCHING FUNDS OF THE CHILD CARE AND DEVELOPMENT FUND',

    'CHILD_CARE_ASSISTANCE',

    'CHILD_CARE_MANDATORY_MATCHING',

    'LOW',

    TRUE,

    TRUE,

    'ETL-199A and ETL-199B establish AL 93.596 as a distinct federal child-care assistance stream. Seven award identifiers are cross-listed with other Assistance Listings under P.L. 102-477 and related administration, but ETL-199B found zero nonzero same-award/same-date/same-amount cross-program collisions. Transaction descriptions distinguish mandatory/tribal entitlement CCDF funds from AL 93.575 discretionary CCDBG and AL 93.558 TANF. Cross-listing therefore warrants LOW provenance overlap risk but not duplicate-dollar exclusion.',

    'ANALYSIS-200-v1',

    2020,

    2024

WHERE NOT EXISTS
(
    SELECT 1
    FROM reference.federal_inflow_program_classification

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND source_program_code =
          '93.596'

      AND methodology_version =
          'ANALYSIS-200-v1'
);


/*
====================================================================================================
8. SEED PROGRAM POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. SEED PROGRAM POLICY MAPPING'
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

    '93.596',

    p.federal_inflow_source_policy_id,

    'INCLUDE_ADDITIVE',

    'AL 93.596 is a distinct additive federal child-care assistance stream. ETL-199B found no duplicate-dollar transaction collision with AL 93.575, AL 93.558, or other cross-listed programs. Common P.L. 102-477 award identifiers reflect integrated administration and do not by themselves establish duplicate federal obligations. Downstream uses of these funds must not be counted as a second federal inflow.',

    'ANALYSIS-200-v1',

    2020,

    2024

FROM m200_policy AS p

WHERE NOT EXISTS
(
    SELECT 1
    FROM reference.federal_inflow_program_policy_mapping AS existing

    WHERE existing.source_system =
          'USASPENDING_ASSISTANCE'

      AND existing.source_program_code =
          '93.596'

      AND existing.methodology_version =
          'ANALYSIS-200-v1'
);


/*
====================================================================================================
9. POST-MIGRATION POLICY RECORD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. POST-MIGRATION SOURCE POLICY'
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

WHERE inflow_family =
      'CHILD_CARE_ASSISTANCE'

  AND inflow_subfamily =
      'CHILD_CARE_MANDATORY_MATCHING'

  AND methodology_version =
      'ANALYSIS-200-v1';


/*
====================================================================================================
10. POST-MIGRATION PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. POST-MIGRATION PROGRAM CLASSIFICATION'
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

WHERE source_system =
      'USASPENDING_ASSISTANCE'

  AND source_program_code =
      '93.596'

  AND methodology_version =
      'ANALYSIS-200-v1';


/*
====================================================================================================
11. POST-MIGRATION PROGRAM POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. POST-MIGRATION PROGRAM POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

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

WHERE source_system =
      'USASPENDING_ASSISTANCE'

  AND source_program_code =
      '93.596'

  AND methodology_version =
      'ANALYSIS-200-v1';


/*
====================================================================================================
12. EFFECTIVE ACCOUNTING DISPOSITION

Reconstruct directly from the certified focal population plus the newly
persisted program-policy mapping.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EFFECTIVE ACCOUNTING DISPOSITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.resolved_accounting_disposition,

    COUNT(*)
        AS transaction_count,

    COUNT(
        DISTINCT f.diagnostic_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT f.recipient_id
    ) AS recipient_count,

    ROUND(
        SUM(f.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN f.is_covid
                THEN f.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN f.is_iija
                THEN f.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN f.is_extraordinary
                THEN f.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m200_focal AS f

CROSS JOIN reference.federal_inflow_program_policy_mapping AS m

WHERE m.source_system =
      'USASPENDING_ASSISTANCE'

  AND m.source_program_code =
      '93.596'

  AND m.methodology_version =
      'ANALYSIS-200-v1'

GROUP BY
    m.resolved_accounting_disposition;


/*
====================================================================================================
13. INDEPENDENT POST-MIGRATION CERTIFICATION

This section reconstructs the accounting result from the certified ledger
again rather than trusting the earlier temporary-table totals alone.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. INDEPENDENT POST-MIGRATION CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_policy_count           bigint;
    v_classification_count   bigint;
    v_mapping_count          bigint;

    v_tx                     bigint;
    v_awards                 bigint;
    v_recipients             bigint;

    v_net                    numeric;
    v_covid                  numeric;
    v_iija                   numeric;
    v_extraordinary          numeric;

    v_disposition            text;
    v_overlap_risk           text;
    v_ledger_treatment       text;

BEGIN

    /*
    -----------------------------------------------------------------------------------------------
    Policy cardinality
    -----------------------------------------------------------------------------------------------
    */

    SELECT COUNT(*)
    INTO v_policy_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family =
          'CHILD_CARE_ASSISTANCE'

      AND inflow_subfamily =
          'CHILD_CARE_MANDATORY_MATCHING'

      AND methodology_version =
          'ANALYSIS-200-v1';


    IF v_policy_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected one source policy, found %',
            v_policy_count;
    END IF;


    /*
    -----------------------------------------------------------------------------------------------
    Classification cardinality
    -----------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),
        MIN(overlap_risk)

    INTO
        v_classification_count,
        v_overlap_risk

    FROM reference.federal_inflow_program_classification

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND source_program_code =
          '93.596'

      AND methodology_version =
          'ANALYSIS-200-v1';


    IF v_classification_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected one program classification, found %',
            v_classification_count;
    END IF;


    IF v_overlap_risk <> 'LOW' THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected overlap risk LOW, found %',
            v_overlap_risk;
    END IF;


    /*
    -----------------------------------------------------------------------------------------------
    Mapping cardinality and disposition
    -----------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),
        MIN(resolved_accounting_disposition)

    INTO
        v_mapping_count,
        v_disposition

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND source_program_code =
          '93.596'

      AND methodology_version =
          'ANALYSIS-200-v1';


    IF v_mapping_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected one program-policy mapping, found %',
            v_mapping_count;
    END IF;


    IF v_disposition <> 'INCLUDE_ADDITIVE' THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected INCLUDE_ADDITIVE, found %',
            v_disposition;
    END IF;


    /*
    -----------------------------------------------------------------------------------------------
    Ledger treatment
    -----------------------------------------------------------------------------------------------
    */

    SELECT MIN(p.ledger_treatment)
    INTO v_ledger_treatment

    FROM reference.federal_inflow_source_policy AS p

    JOIN reference.federal_inflow_program_policy_mapping AS m
      ON m.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id

    WHERE m.source_system =
          'USASPENDING_ASSISTANCE'

      AND m.source_program_code =
          '93.596'

      AND m.methodology_version =
          'ANALYSIS-200-v1'

      AND p.methodology_version =
          'ANALYSIS-200-v1';


    IF v_ledger_treatment <> 'INCLUDE' THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: expected source-policy ledger treatment INCLUDE, found %',
            v_ledger_treatment;
    END IF;


    /*
    -----------------------------------------------------------------------------------------------
    Independent certified-ledger reconstruction
    -----------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT COALESCE(
                NULLIF(l.award_id_fain, ''),
                NULLIF(l.award_id_uri, '')
            )
        ),

        COUNT(
            DISTINCT l.recipient_id
        ),

        ROUND(
            SUM(l.federal_action_obligation)::numeric,
            2
        ),

        ROUND(SUM(
            CASE
                WHEN l.is_covid
                    THEN l.federal_action_obligation
                ELSE 0
            END
        )::numeric, 2),

        ROUND(SUM(
            CASE
                WHEN l.is_iija
                    THEN l.federal_action_obligation
                ELSE 0
            END
        )::numeric, 2),

        ROUND(SUM(
            CASE
                WHEN l.is_extraordinary
                    THEN l.federal_action_obligation
                ELSE 0
            END
        )::numeric, 2)

    INTO
        v_tx,
        v_awards,
        v_recipients,
        v_net,
        v_covid,
        v_iija,
        v_extraordinary

    FROM analysis.v_certified_assistance_ledger AS l

    JOIN reference.federal_inflow_program_policy_mapping AS m
      ON m.source_system =
         'USASPENDING_ASSISTANCE'

     AND m.source_program_code =
         l.cfda_number

     AND m.methodology_version =
         'ANALYSIS-200-v1'

     AND m.resolved_accounting_disposition =
         'INCLUDE_ADDITIVE'

    WHERE l.reference_state_abbreviation = 'WA'

      AND l.action_date_fiscal_year
          BETWEEN 2020 AND 2024

      AND l.cfda_number = '93.596';


    IF v_tx <> 950
       OR v_awards <> 271
       OR v_recipients <> 28
       OR v_net <> 718504226.60
       OR v_covid <> 19429.00
       OR v_iija <> 0.00
       OR v_extraordinary <> 19429.00
    THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: independent certification failed. tx=%, awards=%, recipients=%, net=%, covid=%, iija=%, extraordinary=%',
            v_tx,
            v_awards,
            v_recipients,
            v_net,
            v_covid,
            v_iija,
            v_extraordinary;
    END IF;


    RAISE NOTICE
        'ETL-200 PASS: independent accounting certification reproduced 950 transactions / 271 awards / 28 recipients / $718,504,226.60.';

END
$$;


/*
====================================================================================================
14. FINAL CERTIFIED LEDGER RECONSTRUCTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. FINAL CERTIFIED LEDGER RECONSTRUCTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.resolved_accounting_disposition,

    COUNT(*)
        AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        )
    ) AS award_count,

    COUNT(
        DISTINCT l.recipient_id
    ) AS recipient_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN l.is_covid
                THEN l.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN l.is_iija
                THEN l.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN l.is_extraordinary
                THEN l.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM analysis.v_certified_assistance_ledger AS l

JOIN reference.federal_inflow_program_policy_mapping AS m
  ON m.source_system =
     'USASPENDING_ASSISTANCE'

 AND m.source_program_code =
     l.cfda_number

 AND m.methodology_version =
     'ANALYSIS-200-v1'

WHERE l.reference_state_abbreviation = 'WA'

  AND l.action_date_fiscal_year
      BETWEEN 2020 AND 2024

  AND l.cfda_number = '93.596'

GROUP BY
    m.resolved_accounting_disposition;


/*
====================================================================================================
15. FINAL POLICY CHAIN

Show the complete classification -> mapping -> source-policy chain.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. FINAL POLICY CHAIN'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    c.source_system,
    c.source_program_code,
    c.source_program_title,

    c.inflow_family,
    c.inflow_subfamily,

    c.overlap_risk,

    m.resolved_accounting_disposition,

    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment,

    c.methodology_version
        AS classification_methodology,

    m.methodology_version
        AS mapping_methodology,

    p.methodology_version
        AS policy_methodology

FROM reference.federal_inflow_program_classification AS c

JOIN reference.federal_inflow_program_policy_mapping AS m
  ON m.source_system =
     c.source_system

 AND m.source_program_code =
     c.source_program_code

 AND m.methodology_version =
     'ANALYSIS-200-v1'

JOIN reference.federal_inflow_source_policy AS p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id

WHERE c.source_system =
      'USASPENDING_ASSISTANCE'

  AND c.source_program_code =
      '93.596'

  AND c.methodology_version =
      'ANALYSIS-200-v1';


/*
====================================================================================================
16. FINAL FAIL-CLOSED COMMIT GATE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FINAL FAIL-CLOSED COMMIT GATE'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_chain_count bigint;

BEGIN

    SELECT COUNT(*)
    INTO v_chain_count

    FROM reference.federal_inflow_program_classification AS c

    JOIN reference.federal_inflow_program_policy_mapping AS m
      ON m.source_system =
         c.source_system

     AND m.source_program_code =
         c.source_program_code

    JOIN reference.federal_inflow_source_policy AS p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id

    WHERE c.source_system =
          'USASPENDING_ASSISTANCE'

      AND c.source_program_code =
          '93.596'

      AND c.methodology_version =
          'ANALYSIS-200-v1'

      AND m.methodology_version =
          'ANALYSIS-200-v1'

      AND p.methodology_version =
          'ANALYSIS-200-v1'

      AND c.inflow_family =
          'CHILD_CARE_ASSISTANCE'

      AND c.inflow_subfamily =
          'CHILD_CARE_MANDATORY_MATCHING'

      AND c.overlap_risk =
          'LOW'

      AND m.resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'

      AND p.accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'

      AND p.preferred_source =
          'USASPENDING_ASSISTANCE'

      AND p.allocation_source =
          'UNRESOLVED'

      AND p.ledger_treatment =
          'INCLUDE';


    IF v_chain_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-200 FAIL: final policy-chain gate expected exactly one valid chain, found %',
            v_chain_count;
    END IF;


    RAISE NOTICE
        'ETL-200 PASS: final policy-chain commit gate satisfied.';

END
$$;


/*
====================================================================================================
17. COMMIT
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-200 PASS'
\echo ''
\echo 'AL 93.596 accounting treatment certified.'
\echo ''
\echo 'Resolved disposition : INCLUDE_ADDITIVE'
\echo 'Overlap risk         : LOW'
\echo 'Statewide amount     : $718,504,226.60'
\echo 'COVID                : $19,429.00'
\echo 'IIJA                 : $0.00'
\echo 'Extraordinary        : $19,429.00'
\echo 'County allocation    : UNRESOLVED'
\echo ''
\echo 'Double-count firewall:'
\echo '  - AL 93.596 mandatory/matching CCDF is distinct from AL 93.575 discretionary CCDBG.'
\echo '  - AL 93.596 is distinct from AL 93.558 TANF.'
\echo '  - Common P.L. 102-477 administration or award identifiers do not establish duplicate dollars.'
\echo '  - Downstream uses of these federal transfers are not additional federal inflows.'
\echo '===================================================================================================='
\echo ''

COMMIT;

\echo ''
\echo 'ETL-200 COMMIT COMPLETE'
\echo ''