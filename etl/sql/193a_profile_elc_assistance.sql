/*
====================================================================================================
ETL-193A
EPIDEMIOLOGY AND LABORATORY CAPACITY FOR INFECTIOUS DISEASES (ELC)
ASSISTANCE ACCOUNTING PROFILE
AL 93.323
====================================================================================================

Purpose:
    Profile Washington FY2020-FY2024 USAspending Assistance Listing 93.323
    for statewide federal-inflow accounting.

Primary accounting question:
    Is AL 93.323 a genuine additive federal public-health inflow, or is there
    a plausible accounting overlap with another WCFFBP principal source?

Special concern:
    Preliminary residual analysis indicates that nearly the entire AL 93.323
    population is COVID / extraordinary funding.

    COVID provenance does NOT itself imply duplication. The purpose of this
    diagnostic is to identify an actual accounting overlap pathway, if one
    exists.

PROVENANCE RULE:
    COVID, IIJA, and extraordinary status are orthogonal reporting dimensions.

    A dollar classified as COVID, IIJA, or extraordinary is counted only once
    in the principal accounting ledger. Provenance tags permit later grouping
    and exclusion analyses; they are not additional inflow paths.

This script is READ ONLY.

It does NOT:
    - classify AL 93.323,
    - modify accounting policy,
    - infer county incidence,
    - allocate public-health assistance geographically,
    - assume recipient address equals economic incidence.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-193A - ELC ASSISTANCE ACCOUNTING PROFILE'
\echo 'AL 93.323'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m193a_elc;

CREATE TEMP TABLE m193a_elc AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.323';


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

FROM m193a_elc;


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

FROM m193a_elc

GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. FUNDING / AWARDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4A. FUNDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(funding_agency_name, '[NULL]')
        AS funding_agency_name,

    COALESCE(funding_subagency_name, '[NULL]')
        AS funding_subagency_name,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193a_elc

GROUP BY
    funding_agency_name,
    funding_subagency_name

ORDER BY net_obligation DESC;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4B. AWARDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(awarding_agency_name, '[NULL]')
        AS awarding_agency_name,

    COALESCE(awarding_subagency_name, '[NULL]')
        AS awarding_subagency_name,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193a_elc

GROUP BY
    awarding_agency_name,
    awarding_subagency_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
5. ASSISTANCE TYPE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. ASSISTANCE-TYPE PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(assistance_type_code, '[NULL]')
        AS assistance_type_code,

    COALESCE(assistance_type_description, '[NULL]')
        AS assistance_type_description,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193a_elc

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. RECIPIENT PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(recipient_name, '[NULL]')
        AS recipient_name,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

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

FROM m193a_elc

GROUP BY recipient_name

ORDER BY net_obligation DESC

LIMIT 30;


/*
====================================================================================================
7. AWARD PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. AWARD PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,

    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date,

    COUNT(*) AS transaction_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

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

FROM m193a_elc

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )

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
        WHEN federal_action_obligation > 0 THEN 'POSITIVE'
        WHEN federal_action_obligation < 0 THEN 'NEGATIVE'
        ELSE 'ZERO'
    END AS obligation_sign,

    COUNT(*) AS transaction_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193a_elc

GROUP BY 1
ORDER BY 1;


/*
====================================================================================================
9. PROVENANCE PROFILE

Keep COVID / IIJA / extraordinary explicit at transaction level.
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

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193a_elc

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
10. COVID / PUBLIC-HEALTH SEMANTIC SCREEN

Purpose:
    Identify the major semantic components of AL 93.323.

These are evidence categories only. They do not alter accounting.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. COVID / PUBLIC-HEALTH SEMANTIC SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH terms(term) AS
(
    VALUES
        ('COVID'),
        ('CORONAVIRUS'),
        ('SARS-COV-2'),
        ('TESTING'),
        ('LABORATORY'),
        ('LABORATORIES'),
        ('EPIDEMIOLOGY'),
        ('SURVEILLANCE'),
        ('CONTACT TRACING'),
        ('VACCINE'),
        ('VACCINATION'),
        ('IMMUNIZATION'),
        ('GENOMIC'),
        ('SEQUENCING'),
        ('SCHOOL'),
        ('SCHOOLS'),
        ('ELC'),
        ('INFECTIOUS DISEASE'),
        ('HEALTH DISPARITIES'),
        ('NURSING HOME')
)

SELECT
    t.term AS semantic_term,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(b.award_id_fain, ''),
            NULLIF(b.award_id_uri, '')
        )
    ) AS award_count,

    ROUND(SUM(b.federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM terms t

JOIN m193a_elc b
  ON
       UPPER(COALESCE(b.canonical_award_description, ''))
           LIKE '%' || t.term || '%'

    OR UPPER(COALESCE(b.transaction_description, ''))
           LIKE '%' || t.term || '%'

GROUP BY t.term

ORDER BY net_obligation DESC;


/*
====================================================================================================
11. DESCRIPTION PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11A. TOP CANONICAL AWARD DESCRIPTIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(canonical_award_description, '[NULL]')
        AS canonical_award_description,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193a_elc

GROUP BY canonical_award_description

ORDER BY net_obligation DESC

LIMIT 25;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11B. TOP TRANSACTION DESCRIPTIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(transaction_description, '[NULL]')
        AS transaction_description,

    COUNT(*) AS transaction_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193a_elc

GROUP BY transaction_description

ORDER BY net_obligation DESC

LIMIT 30;


/*
====================================================================================================
12. EXISTING AL 93.323 CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING AL 93.323 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '93.323'

ORDER BY
    methodology_version,
    federal_inflow_program_classification_id;


/*
====================================================================================================
13. EXISTING AL 93.323 POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXISTING AL 93.323 POLICY MAPPING'
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
  AND m.source_program_code = '93.323'

ORDER BY
    m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
14. EXISTING HHS / CDC / PUBLIC-HEALTH POLICY INVENTORY

Purpose:
    Search WCFFBP's existing policy architecture for plausible independent
    accounting sources or related assistance streams.

Returned rows are NOT presumed duplicates.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EXISTING HHS / CDC / PUBLIC-HEALTH POLICY INVENTORY'
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
           LIKE '%HEALTH%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%HEALTH%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%DISEASE%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%DISEASE%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%RESEARCH%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%RESEARCH%'

    OR UPPER(COALESCE(preferred_source, ''))
           LIKE '%CDC%'

    OR UPPER(COALESCE(preferred_source, ''))
           LIKE '%HHS%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
15. RELATED HHS / CDC PROGRAM CLASSIFICATION INVENTORY

This screens other classified USAspending programs for nearby program families.
It is intentionally broad and diagnostic only.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. RELATED PROGRAM CLASSIFICATION INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'

  AND
  (
       source_program_code LIKE '93.%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%HEALTH%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%HEALTH%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%DISEASE%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%DISEASE%'
  )

ORDER BY
    source_program_code,
    federal_inflow_program_classification_id;


/*
====================================================================================================
16. CROSS-PROGRAM AWARD-ID COLLISION SCREEN

Purpose:
    Determine whether any AL 93.323 award identifier also appears under another
    Assistance Listing in the certified Washington FY2020-FY2024 ledger.

A collision would require investigation.
Zero collisions would materially reduce mechanical duplication concern.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16A. CROSS-PROGRAM AWARD-ID COLLISION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH elc_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM m193a_elc
),

other_awards AS
(
    SELECT DISTINCT
        cfda_number,

        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number <> '93.323'
)

SELECT
    COUNT(DISTINCT e.award_identifier)
        AS elc_awards_colliding_elsewhere,

    COUNT(DISTINCT o.cfda_number)
        AS other_programs_involved

FROM elc_awards e

JOIN other_awards o
  ON o.award_identifier = e.award_identifier

WHERE e.award_identifier IS NOT NULL;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16B. CROSS-PROGRAM AWARD-ID COLLISION DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

WITH elc_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM m193a_elc
),

other_awards AS
(
    SELECT
        cfda_number,

        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier,

        COUNT(*) AS transaction_count,

        ROUND(
            SUM(federal_action_obligation)::numeric,
            2
        ) AS net_obligation

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number <> '93.323'

    GROUP BY
        cfda_number,
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
)

SELECT
    e.award_identifier,
    o.cfda_number AS other_program_code,
    o.transaction_count,
    o.net_obligation

FROM elc_awards e

JOIN other_awards o
  ON o.award_identifier = e.award_identifier

WHERE e.award_identifier IS NOT NULL

ORDER BY
    ABS(o.net_obligation) DESC,
    e.award_identifier

LIMIT 50;


/*
====================================================================================================
17. OTHER COVID / EXTRAORDINARY ASSISTANCE PROGRAMS

Purpose:
    Put ELC into the context of already classified COVID/extraordinary
    USAspending assistance.

This does NOT imply overlap.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. EXISTING COVID / EXTRAORDINARY PROGRAM CLASSIFICATIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND (
        covid_relevance = true
        OR extraordinary_relevance = true
      )

ORDER BY
    source_program_code,
    methodology_version;


/*
====================================================================================================
18. CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. CLOSURE CONTROL'
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

FROM m193a_elc;


DO $$
DECLARE
    v_tx      bigint;
    v_amount  numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_amount

    FROM m193a_elc;


    IF v_tx = 0 THEN
        RAISE EXCEPTION
            'ETL-193A focal population is empty';
    END IF;


    RAISE NOTICE
        'ETL-193A CLOSURE PASS: tx=% amount=%',
        v_tx,
        ROUND(v_amount, 2);
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-193A COMPLETE'
\echo 'AL 93.323 ELC'
\echo 'Statewide accounting diagnostic only.'
\echo 'COVID / IIJA / extraordinary retained as orthogonal provenance dimensions.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;