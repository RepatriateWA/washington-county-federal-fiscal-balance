/*
====================================================================================================
ETL-194A
PBGC PENSION PLAN TERMINATION INSURANCE
STATEWIDE ACCOUNTING PROFILE

Assistance Listing:
    86.001 - Pension Plan Termination Insurance

Purpose:
    Profile Washington FY2020-FY2024 USAspending assistance transactions for
    AL 86.001 before making any WCFFBP accounting decision.

Questions:
    1. What does the approximately $989M population represent?
    2. Is it federal benefit/payment activity attributable to Washington?
    3. What is the fiscal-year and provenance structure?
    4. Is there a plausible overlap pathway with an independently acquired
       social-insurance accounting source already used by WCFFBP?
    5. Does the evidence support program-level accounting, or is a narrower
       transaction/award partition required?

No persistent database writes.
No accounting classification.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-194A'
\echo 'PBGC PENSION PLAN TERMINATION INSURANCE PROFILE'
\echo 'AL 86.001'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m194a_pbgc;

CREATE TEMP TABLE m194a_pbgc AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '86.001';


CREATE INDEX m194a_pbgc_award_idx
    ON m194a_pbgc (
        award_id_fain
    );

CREATE INDEX m194a_pbgc_fy_idx
    ON m194a_pbgc (
        action_date_fiscal_year
    );

ANALYZE m194a_pbgc;


/*
====================================================================================================
2. FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FOCAL CONTROL'
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

FROM m194a_pbgc;


/*
====================================================================================================
3. FISCAL-YEAR PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FISCAL-YEAR PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

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

FROM m194a_pbgc

GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. TRANSACTION-SIGN PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. TRANSACTION-SIGN PROFILE'
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

FROM m194a_pbgc

GROUP BY 1
ORDER BY 1;


/*
====================================================================================================
5. FUNDING / AWARDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. FUNDING / AWARDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    funding_agency_name,
    funding_subagency_name,
    awarding_agency_name,
    awarding_subagency_name,

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
    ) AS net_obligation

FROM m194a_pbgc

GROUP BY
    funding_agency_name,
    funding_subagency_name,
    awarding_agency_name,
    awarding_subagency_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
6. ASSISTANCE MECHANISM
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. ASSISTANCE MECHANISM'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    assistance_type_code,
    assistance_type_description,

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
    ) AS net_obligation

FROM m194a_pbgc

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
7. RECIPIENT PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    recipient_name,

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
    )::numeric, 2) AS covid_amount

FROM m194a_pbgc

GROUP BY recipient_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC
LIMIT 50;


/*
====================================================================================================
8. AWARD PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. AWARD PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier,

    MIN(recipient_name)
        AS recipient_name,

    COUNT(*) AS transaction_count,

    MIN(action_date)
        AS first_action_date,

    MAX(action_date)
        AS last_action_date,

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
    )::numeric, 2) AS extraordinary_amount,

    MIN(canonical_award_description)
        AS award_description

FROM m194a_pbgc

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )

ORDER BY ABS(SUM(federal_action_obligation)) DESC
LIMIT 100;


/*
====================================================================================================
9. PROVENANCE PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. COVID / IIJA / EXTRAORDINARY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    is_covid,
    is_iija,
    is_extraordinary,

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
    ) AS net_obligation

FROM m194a_pbgc

GROUP BY
    is_covid,
    is_iija,
    is_extraordinary

ORDER BY
    is_covid DESC,
    is_iija DESC,
    is_extraordinary DESC;


/*
====================================================================================================
10. DESCRIPTION / SEMANTIC SAMPLE

Distinct descriptions are more useful here than printing every transaction.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. DISTINCT AWARD / TRANSACTION DESCRIPTION SAMPLE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier,

    action_date,

    federal_action_obligation,

    recipient_name,

    transaction_description,

    canonical_award_description

FROM m194a_pbgc

WHERE
       NULLIF(TRIM(transaction_description), '') IS NOT NULL
    OR NULLIF(TRIM(canonical_award_description), '') IS NOT NULL

ORDER BY
    ABS(federal_action_obligation) DESC,
    action_date,
    assistance_transaction_id

LIMIT 100;


/*
====================================================================================================
11. SEMANTIC KEYWORD SCREEN

This is diagnostic only. Keyword hits do not determine accounting treatment.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. SEMANTIC KEYWORD SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH semantic AS
(
    SELECT
        *,

        LOWER(
            COALESCE(transaction_description, '')
            || ' '
            || COALESCE(canonical_award_description, '')
        ) AS semantic_text

    FROM m194a_pbgc
)

SELECT
    semantic_category,

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
    ) AS net_obligation

FROM
(
    SELECT
        semantic.*,

        CASE

            WHEN semantic_text ~
                'special financial assistance|american rescue plan|arpa'
                THEN 'SPECIAL_FINANCIAL_ASSISTANCE_ARPA'

            WHEN semantic_text ~
                'pension plan termination|termination insurance'
                THEN 'PENSION_PLAN_TERMINATION'

            WHEN semantic_text ~
                'pension benefit|retirement benefit|monthly benefit'
                THEN 'PENSION_RETIREMENT_BENEFIT'

            WHEN semantic_text ~
                'multiemployer|multi-employer'
                THEN 'MULTIEMPLOYER_PLAN'

            WHEN semantic_text ~
                'single.employer|single employer'
                THEN 'SINGLE_EMPLOYER_PLAN'

            WHEN semantic_text ~
                'participant|beneficiar|retiree'
                THEN 'PARTICIPANT_OR_BENEFICIARY'

            WHEN semantic_text ~
                'social security|ssa'
                THEN 'SOCIAL_SECURITY_REFERENCE'

            WHEN semantic_text ~
                'railroad retirement|railroad'
                THEN 'RAILROAD_REFERENCE'

            ELSE 'OTHER_OR_UNSPECIFIED'

        END AS semantic_category

    FROM semantic
) s

GROUP BY semantic_category

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
12. EXISTING AL 86.001 PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING AL 86.001 PROGRAM CLASSIFICATION'
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
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '86.001'

ORDER BY federal_inflow_program_classification_id;


/*
====================================================================================================
13. EXISTING AL 86.001 POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXISTING AL 86.001 PROGRAM POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.federal_inflow_source_policy_id,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping m

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '86.001'

ORDER BY m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
14. EXISTING SOCIAL-INSURANCE SOURCE POLICIES

The purpose is to expose possible principal-source relationships already
encoded in WCFFBP. This is not itself proof of overlap.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EXISTING SOCIAL-INSURANCE SOURCE POLICIES'
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
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_source_policy

WHERE
       UPPER(inflow_family) LIKE '%SOCIAL%'
    OR UPPER(inflow_family) LIKE '%RETIRE%'
    OR UPPER(inflow_family) LIKE '%PENSION%'
    OR UPPER(inflow_family) LIKE '%INCOME%'
    OR UPPER(inflow_subfamily) LIKE '%OASDI%'
    OR UPPER(inflow_subfamily) LIKE '%RAILROAD%'
    OR UPPER(inflow_subfamily) LIKE '%RETIRE%'
    OR UPPER(inflow_subfamily) LIKE '%PENSION%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
15. RELATED PROGRAM CLASSIFICATIONS

Look for already-classified SSA, RRB, pension, retirement, unemployment,
income-security, or other potentially relevant social-insurance streams.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. RELATED PROGRAM CLASSIFICATIONS'
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
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE
       UPPER(COALESCE(source_program_title, '')) LIKE '%PENSION%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%RETIRE%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%SOCIAL SECURITY%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%RAILROAD%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%RETIRE%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%PENSION%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%OASDI%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%RAILROAD%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%RETIRE%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%PENSION%'

ORDER BY
    source_system,
    source_program_code,
    federal_inflow_program_classification_id;


/*
====================================================================================================
16. SHARED AWARD IDENTIFIER SCREEN

As learned from ELC, shared award identifiers alone do not establish duplicate
inflow. This merely tells us whether the focal identifiers occur under another
Assistance Listing.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. SHARED AWARD IDENTIFIER SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM m194a_pbgc

    WHERE COALESCE(
              NULLIF(award_id_fain, ''),
              NULLIF(award_id_uri, '')
          ) IS NOT NULL
),

other_programs AS
(
    SELECT
        COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        ) AS award_identifier,

        l.cfda_number,

        COUNT(*) AS transaction_count,

        ROUND(
            SUM(l.federal_action_obligation)::numeric,
            2
        ) AS net_obligation

    FROM analysis.v_certified_assistance_ledger l

    JOIN focal_awards f
      ON f.award_identifier =
         COALESCE(
             NULLIF(l.award_id_fain, ''),
             NULLIF(l.award_id_uri, '')
         )

    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number <> '86.001'

    GROUP BY
        COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        ),
        l.cfda_number
)

SELECT
    award_identifier,
    cfda_number AS other_assistance_listing,
    transaction_count,
    net_obligation

FROM other_programs

ORDER BY
    ABS(net_obligation) DESC,
    award_identifier,
    cfda_number;


/*
====================================================================================================
17. CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. CLOSURE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS closure_transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS closure_award_count,

    COUNT(DISTINCT recipient_id)
        AS closure_recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS closure_net_obligation,

    ROUND(SUM(
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS closure_covid_amount,

    ROUND(SUM(
        CASE
            WHEN is_iija
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS closure_iija_amount,

    ROUND(SUM(
        CASE
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS closure_extraordinary_amount

FROM m194a_pbgc;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-194A COMPLETE'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;