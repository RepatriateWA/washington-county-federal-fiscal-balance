/*
====================================================================================================
ETL-191
HEAD START ASSISTANCE ACCOUNTING POLICY
AL 93.600
====================================================================================================

Purpose:
    Resolve Washington FY2020-FY2024 USAspending Assistance Listing 93.600
    (Head Start) for statewide federal-inflow accounting.

Evidence:
    ETL-190A established:

        transactions                 1,691
        awards                         214
        recipients                      52
        net obligation       $1,283,962,108.80
        COVID                  $570,416,931.19
        IIJA                              $0.00
        extraordinary          $570,416,931.19

Accounting decision:
    - Head Start is additive federal inflow.
    - USAspending assistance is the principal statewide accounting source.
    - Accounting measure is net federal action obligation.
    - Negative obligation adjustments remain in the net measure.
    - COVID / extraordinary provenance remains preserved.
    - County allocation remains unresolved.
    - No identified overlap pathway with another WCFFBP principal source.

Important double-count safeguard:
    Downstream expenditure, reimbursement, transfer, or service delivery
    using already-counted federal Head Start funds is not a second federal
    inflow.

    Early Head Start - Child Care Partnership awards reported under AL 93.600
    remain Head Start inflow and are not reclassified as CCDBG merely because
    the award description references child-care partnerships.

Methodology:
    ANALYSIS-191-v1

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-191 - HEAD START ASSISTANCE ACCOUNTING POLICY'
\echo 'AL 93.600'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. PRE-MIGRATION FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION FOCAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m191_head_start;

CREATE TEMP TABLE m191_head_start AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.600';


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

FROM m191_head_start;


DO $$
DECLARE
    v_tx      bigint;
    v_awards  bigint;
    v_recip   bigint;
    v_amount  numeric;
    v_covid   numeric;
    v_iija    numeric;
    v_extra   numeric;
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

        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

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

    FROM m191_head_start;


    IF v_tx <> 1691
       OR v_awards <> 214
       OR v_recip <> 52
       OR ROUND(v_amount, 2) <> 1283962108.80
       OR ROUND(v_covid, 2) <> 570416931.19
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 570416931.19 THEN

        RAISE EXCEPTION
            'ETL-191 focal control failed: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);

    END IF;


    RAISE NOTICE
        'ETL-191 PRE-MIGRATION FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
2. TRANSACTION-SIGN CONTROL

Preserve the net-obligation accounting semantics established by ETL-190A.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. TRANSACTION-SIGN CONTROL'
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

FROM m191_head_start

GROUP BY 1

ORDER BY 1;


DO $$
DECLARE
    v_negative_tx      bigint;
    v_negative_amount  numeric;
    v_positive_tx      bigint;
    v_positive_amount  numeric;
    v_zero_tx          bigint;
BEGIN

    SELECT
        COUNT(*) FILTER (
            WHERE federal_action_obligation < 0
        ),

        COALESCE(SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COUNT(*) FILTER (
            WHERE federal_action_obligation > 0
        ),

        COALESCE(SUM(
            CASE
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COUNT(*) FILTER (
            WHERE federal_action_obligation = 0
        )

    INTO
        v_negative_tx,
        v_negative_amount,
        v_positive_tx,
        v_positive_amount,
        v_zero_tx

    FROM m191_head_start;


    IF v_negative_tx <> 230
       OR ROUND(v_negative_amount, 2) <> -37909429.75
       OR v_positive_tx <> 879
       OR ROUND(v_positive_amount, 2) <> 1321871538.55
       OR v_zero_tx <> 582 THEN

        RAISE EXCEPTION
            'ETL-191 transaction-sign control failed';

    END IF;


    RAISE NOTICE
        'ETL-191 TRANSACTION-SIGN CONTROL PASS';

END
$$;


/*
====================================================================================================
3. PRE-EXISTING PROGRAM CLASSIFICATION CONTROL

ETL-190A established no existing classification for AL 93.600.
Fail closed if one appeared between profiling and migration.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. PRE-EXISTING PROGRAM CLASSIFICATION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.600';


    IF v_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-191 refuses to proceed: 93.600 already has % program classification row(s)',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-191 PRE-EXISTING PROGRAM CLASSIFICATION CONTROL PASS';

END
$$;


/*
====================================================================================================
4. PRE-EXISTING PROGRAM POLICY MAPPING CONTROL

ETL-190A established no existing policy mapping for AL 93.600.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PRE-EXISTING PROGRAM POLICY MAPPING CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.600';


    IF v_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-191 refuses to proceed: 93.600 already has % program-policy mapping row(s)',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-191 PRE-EXISTING PROGRAM POLICY MAPPING CONTROL PASS';

END
$$;


/*
====================================================================================================
5. INSERT HEAD START SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. INSERT HEAD START SOURCE POLICY'
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
    'EARLY_CHILDHOOD_ASSISTANCE',
    'HEAD_START',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'ETL-190A established AL 93.600 as federal Head Start and Early Head Start project-grant assistance awarded by HHS Administration for Children and Families to Washington Head Start delivery organizations. No identified overlap pathway exists with another WCFFBP principal accounting source. USAspending net federal action obligation is therefore the preferred statewide accounting measure. Negative obligation adjustments remain in the net measure. COVID and extraordinary provenance is retained. Early Head Start-Child Care Partnership awards reported under AL 93.600 remain Head Start inflow and are not reclassified as CCDBG solely because the award description references child-care partnerships. Downstream expenditure, reimbursement, transfer, or service delivery using already-counted Head Start dollars is not a second federal inflow. County allocation remains unresolved.',

    'ANALYSIS-191-v1',
    2020,
    2024

WHERE NOT EXISTS
(
    SELECT 1

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'EARLY_CHILDHOOD_ASSISTANCE'
      AND inflow_subfamily = 'HEAD_START'
      AND methodology_version = 'ANALYSIS-191-v1'
);


/*
====================================================================================================
6. SOURCE POLICY PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. SOURCE POLICY PERSISTENCE CONTROL'
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

WHERE inflow_family = 'EARLY_CHILDHOOD_ASSISTANCE'
  AND inflow_subfamily = 'HEAD_START'
  AND methodology_version = 'ANALYSIS-191-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'EARLY_CHILDHOOD_ASSISTANCE'
      AND inflow_subfamily = 'HEAD_START'
      AND methodology_version = 'ANALYSIS-191-v1';


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-191 expected exactly one Head Start source policy; found %',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-191 SOURCE POLICY PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
7. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. INSERT PROGRAM CLASSIFICATION'
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
    '93.600',
    'Head Start',
    'EARLY_CHILDHOOD_ASSISTANCE',
    'HEAD_START',
    'NONE',
    true,
    true,

    'ETL-190A profiled Washington FY2020-FY2024 AL 93.600: 1,691 transactions, 214 awards, 52 recipients, and $1,283,962,108.80 net federal action obligations. All observations are project grants; awarding activity is HHS Administration for Children and Families. Descriptions identify Head Start, Early Head Start, Migrant/Seasonal Head Start, AIAN Head Start, Early Head Start-Child Care Partnerships, and COVID/ARPA supplements. No identified overlap pathway exists with another WCFFBP principal accounting source. Child-care partnership terminology does not by itself imply duplication with CCDBG.',

    'ANALYSIS-191-v1',
    2020,
    2024
);


/*
====================================================================================================
8. PROGRAM CLASSIFICATION PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. PROGRAM CLASSIFICATION PERSISTENCE CONTROL'
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
  AND source_program_code = '93.600'
  AND methodology_version = 'ANALYSIS-191-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.600'
      AND methodology_version = 'ANALYSIS-191-v1'
      AND inflow_family = 'EARLY_CHILDHOOD_ASSISTANCE'
      AND inflow_subfamily = 'HEAD_START'
      AND overlap_risk = 'NONE'
      AND covid_relevance = true
      AND extraordinary_relevance = true;


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-191 program classification persistence failed';

    END IF;


    RAISE NOTICE
        'ETL-191 PROGRAM CLASSIFICATION PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
9. INSERT PROGRAM POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. INSERT PROGRAM POLICY MAPPING'
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
    '93.600',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'ETL-190A established AL 93.600 as additive Head Start federal assistance with no identified overlap pathway to another WCFFBP principal accounting source. USAspending net federal action obligations are used for statewide accounting. COVID and extraordinary provenance is preserved. Early Head Start-Child Care Partnership descriptions remain part of AL 93.600 and do not constitute a second CCDBG accounting path.',

    'ANALYSIS-191-v1',
    2020,
    2024

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'EARLY_CHILDHOOD_ASSISTANCE'
  AND p.inflow_subfamily = 'HEAD_START'
  AND p.methodology_version = 'ANALYSIS-191-v1';


/*
====================================================================================================
10. PROGRAM POLICY MAPPING PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. PROGRAM POLICY MAPPING PERSISTENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id
     = m.federal_inflow_source_policy_id

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '93.600'
  AND m.methodology_version = 'ANALYSIS-191-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id
         = m.federal_inflow_source_policy_id

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '93.600'
      AND m.methodology_version = 'ANALYSIS-191-v1'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND p.inflow_family = 'EARLY_CHILDHOOD_ASSISTANCE'
      AND p.inflow_subfamily = 'HEAD_START'
      AND p.accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND p.preferred_source = 'USASPENDING_ASSISTANCE'
      AND p.allocation_source = 'UNRESOLVED'
      AND p.ledger_treatment = 'INCLUDE';


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-191 program-policy mapping persistence failed';

    END IF;


    RAISE NOTICE
        'ETL-191 PROGRAM POLICY MAPPING PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
11. CCDBG NON-INTERFERENCE CONTROL

Head Start child-care partnership language must not alter the already
established accounting treatment for AL 93.575.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. CCDBG NON-INTERFERENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    methodology_version

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.575';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.575'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE';


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-191 CCDBG non-interference control failed: expected one INCLUDE_ADDITIVE mapping for 93.575, found %',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-191 CCDBG NON-INTERFERENCE PASS';

END
$$;


/*
====================================================================================================
12. EFFECTIVE HEAD START RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EFFECTIVE HEAD START RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m191_effective;

CREATE TEMP TABLE m191_effective AS

SELECT
    h.assistance_transaction_id,
    h.federal_action_obligation,
    h.is_covid,
    h.is_iija,
    h.is_extraordinary,

    m.resolved_accounting_disposition
        AS accounting_disposition

FROM m191_head_start h

LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = '93.600'
 AND m.methodology_version = 'ANALYSIS-191-v1';


SELECT
    accounting_disposition,

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
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m191_effective

GROUP BY accounting_disposition

ORDER BY accounting_disposition;


/*
====================================================================================================
13. EFFECTIVE RESOLUTION HARD CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EFFECTIVE RESOLUTION HARD CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_rows       bigint;
    v_distinct   bigint;
    v_additive   bigint;
    v_null       bigint;
    v_amount     numeric;
    v_covid      numeric;
    v_extra      numeric;
BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT assistance_transaction_id
        ),

        COUNT(*) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ),

        COUNT(*) FILTER (
            WHERE accounting_disposition IS NULL
        ),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                 AND is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                 AND is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_rows,
        v_distinct,
        v_additive,
        v_null,
        v_amount,
        v_covid,
        v_extra

    FROM m191_effective;


    IF v_rows <> 1691
       OR v_distinct <> 1691
       OR v_additive <> 1691
       OR v_null <> 0
       OR ROUND(v_amount, 2) <> 1283962108.80
       OR ROUND(v_covid, 2) <> 570416931.19
       OR ROUND(v_extra, 2) <> 570416931.19 THEN

        RAISE EXCEPTION
            'ETL-191 effective resolution failed: rows %, distinct %, additive %, null %, amount %, COVID %, extraordinary %',
            v_rows,
            v_distinct,
            v_additive,
            v_null,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_extra, 2);

    END IF;


    RAISE NOTICE
        'ETL-191 EFFECTIVE RESOLUTION HARD CONTROL PASS';

END
$$;


/*
====================================================================================================
14. FINAL CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. FINAL CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS focal_transactions,

    COUNT(
        DISTINCT assistance_transaction_id
    ) AS distinct_focal_transactions,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS focal_net_obligation,

    COUNT(*) FILTER (
        WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
    ) AS additive_transactions,

    ROUND(SUM(
        CASE
            WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS additive_net_obligation

FROM m191_effective;


DO $$
BEGIN

    RAISE NOTICE
        'ETL-191 HARD CERTIFICATION PASS';

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-191 COMPLETE'
\echo ''
\echo 'Expected accounting result:'
\echo '  AL 93.600 focal amount          $1,283,962,108.80'
\echo '  INCLUDE_ADDITIVE                $1,283,962,108.80'
\echo '  COVID / extraordinary             $570,416,931.19'
\echo '  IIJA                                         $0.00'
\echo '  Overlap risk                                NONE'
\echo '  County-incidence decision                   NONE'
\echo '===================================================================================================='
\echo ''

COMMIT;