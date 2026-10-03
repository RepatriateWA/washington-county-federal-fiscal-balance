/*
====================================================================================================
ETL-190A
HEAD START ASSISTANCE ACCOUNTING PROFILE
AL 93.600
====================================================================================================

Purpose:
    Profile Washington FY2020-FY2024 USAspending Assistance Listing 93.600
    for statewide federal-inflow accounting.

Questions:
    1. What is the exact certified focal population?
    2. What federal agencies fund/award it?
    3. What assistance mechanism is represented?
    4. Who receives the awards?
    5. Are obligations positive, negative, or zero?
    6. What COVID / IIJA / extraordinary provenance exists?
    7. What do the award/transaction descriptions say?
    8. Is there evidence of a plausible overlap pathway with an independently
       acquired WCFFBP principal accounting source?

This script is READ ONLY.

It does NOT:
    - classify the program,
    - write accounting policy,
    - infer county economic incidence,
    - decide additive treatment.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-190A - HEAD START ASSISTANCE ACCOUNTING PROFILE'
\echo 'AL 93.600'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m190a_head_start;

CREATE TEMP TABLE m190a_head_start AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.600';


/*
====================================================================================================
2. HARD FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. HARD FOCAL CONTROL'
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
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS extraordinary_amount

FROM m190a_head_start;


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

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS extraordinary_amount

FROM m190a_head_start

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. FUNDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FUNDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        funding_agency_name,
        '[NULL]'
    ) AS funding_agency_name,

    COALESCE(
        funding_subagency_name,
        '[NULL]'
    ) AS funding_subagency_name,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m190a_head_start

GROUP BY
    funding_agency_name,
    funding_subagency_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
5. AWARDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. AWARDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        awarding_agency_name,
        '[NULL]'
    ) AS awarding_agency_name,

    COALESCE(
        awarding_subagency_name,
        '[NULL]'
    ) AS awarding_subagency_name,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m190a_head_start

GROUP BY
    awarding_agency_name,
    awarding_subagency_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. ASSISTANCE-TYPE PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. ASSISTANCE-TYPE PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        assistance_type_code,
        '[NULL]'
    ) AS assistance_type_code,

    COALESCE(
        assistance_type_description,
        '[NULL]'
    ) AS assistance_type_description,

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

FROM m190a_head_start

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY net_obligation DESC;


/*
====================================================================================================
7. TOP RECIPIENTS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TOP RECIPIENTS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        recipient_name,
        '[NULL]'
    ) AS recipient_name,

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
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount

FROM m190a_head_start

GROUP BY recipient_name

ORDER BY net_obligation DESC

LIMIT 40;


/*
====================================================================================================
8. TRANSACTION SIGN PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TRANSACTION SIGN PROFILE'
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

FROM m190a_head_start

GROUP BY 1

ORDER BY 1;


/*
====================================================================================================
9. PROVENANCE PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. COVID / IIJA / EXTRAORDINARY PROVENANCE'
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

FROM m190a_head_start

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
10. DESCRIPTION SEMANTIC SEARCH
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. DESCRIPTION SEMANTIC SEARCH'
\echo '----------------------------------------------------------------------------------------------------'

WITH terms(term) AS
(
    VALUES
        ('HEAD START'),
        ('EARLY HEAD START'),
        ('CHILD CARE'),
        ('CHILDCARE'),
        ('CCDBG'),
        ('CHILD CARE AND DEVELOPMENT'),
        ('TANF'),
        ('SOCIAL SERVICES BLOCK GRANT'),
        ('SSBG'),
        ('MEDICAID'),
        ('MEDICARE'),
        ('COVID'),
        ('CORONAVIRUS'),
        ('CARES'),
        ('AMERICAN RESCUE'),
        ('ARPA'),
        ('DISASTER'),
        ('REIMBURSE'),
        ('PASS THROUGH'),
        ('PASS-THROUGH')
)

SELECT
    t.term AS semantic_term,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(h.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM terms t

JOIN m190a_head_start h
  ON
       UPPER(
           COALESCE(h.canonical_award_description, '')
       ) LIKE '%' || t.term || '%'

    OR UPPER(
           COALESCE(h.transaction_description, '')
       ) LIKE '%' || t.term || '%'

GROUP BY t.term

ORDER BY net_obligation DESC;


/*
====================================================================================================
11. DESCRIPTION VALUE PROFILE

Show all description values when cardinality is manageable.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. CANONICAL AWARD DESCRIPTION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        canonical_award_description,
        '[NULL]'
    ) AS canonical_award_description,

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
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount

FROM m190a_head_start

GROUP BY canonical_award_description

ORDER BY net_obligation DESC

LIMIT 60;


/*
====================================================================================================
12. EXISTING WCFFBP PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING WCFFBP PROGRAM CLASSIFICATION'
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
  AND source_program_code = '93.600'

ORDER BY
    methodology_version,
    federal_inflow_program_classification_id;


/*
====================================================================================================
13. EXISTING PROGRAM POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXISTING PROGRAM POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.methodology_version AS policy_methodology_version

FROM reference.federal_inflow_program_policy_mapping m

LEFT JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id
     = m.federal_inflow_source_policy_id

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '93.600'

ORDER BY
    m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
14. POSSIBLE OVERLAP-POLICY SEARCH

This does NOT assert overlap.
It simply inventories existing WCFFBP policies whose terminology could
conceivably intersect with Head Start / early-childhood assistance.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. POSSIBLE OVERLAP-POLICY SEARCH'
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
    methodology_version

FROM reference.federal_inflow_source_policy

WHERE
       UPPER(COALESCE(inflow_family, ''))
           LIKE '%CHILD%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%CHILD%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%EDUCATION%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%EDUCATION%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%TANF%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%TANF%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%SOCIAL%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%SOCIAL%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
15. FISCAL-YEAR CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. FISCAL-YEAR CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

WITH fy AS
(
    SELECT
        action_date_fiscal_year AS fiscal_year,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation)
            AS net_obligation
    FROM m190a_head_start
    GROUP BY action_date_fiscal_year
)

SELECT
    SUM(transaction_count)
        AS reconstructed_transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS reconstructed_net_obligation

FROM fy;


/*
====================================================================================================
16. FINAL CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FINAL CLOSURE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS closure_transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS closure_net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS closure_covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS closure_iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS closure_extraordinary_amount

FROM m190a_head_start;


DO $$
DECLARE
    v_tx       bigint;
    v_amount   numeric;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_tx,
        v_amount

    FROM m190a_head_start;


    IF v_tx = 0 THEN

        RAISE EXCEPTION
            'ETL-190A focal population is empty';

    END IF;


    RAISE NOTICE
        'ETL-190A CLOSURE PASS: tx=% amount=%',
        v_tx,
        ROUND(v_amount, 2);

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-190A COMPLETE'
\echo 'AL 93.600 Head Start'
\echo 'Statewide accounting diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;