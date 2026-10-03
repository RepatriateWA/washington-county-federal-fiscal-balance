/*
====================================================================================================
ETL-192A
SECTION 8 HOUSING ASSISTANCE PAYMENTS PROGRAM
PROJECT-BASED RENTAL ASSISTANCE (PBRA)
ASSISTANCE ACCOUNTING PROFILE
AL 14.195
====================================================================================================

Purpose:
    Profile Washington FY2020-FY2024 USAspending Assistance Listing 14.195
    for statewide federal-inflow accounting.

Primary accounting question:
    Is AL 14.195 a distinct federal rental-assistance inflow from the
    previously resolved Housing Choice Voucher program, AL 14.871?

Secondary questions:
    1. What is the exact certified focal population?
    2. What is the fiscal-year distribution?
    3. What HUD agencies/subagencies fund and award the assistance?
    4. What assistance mechanisms are represented?
    5. Who receives the assistance?
    6. Are obligations concentrated in particular awards or recipients?
    7. What is the positive/negative/zero transaction structure?
    8. What COVID, IIJA, and extraordinary provenance is present?
    9. Do descriptions indicate project-based rental assistance,
       tenant-based vouchers, HCV, or another mechanism?
   10. Does WCFFBP already contain a classification or policy mapping?
   11. Does the existing HCV policy provide evidence of an overlap pathway?

PROVENANCE RULE:
    COVID, IIJA, and extraordinary status are orthogonal reporting dimensions.

    A dollar classified as COVID, IIJA, or extraordinary is counted only
    once in the principal accounting ledger. Provenance tags permit later
    grouping and exclusion analyses; they are not additional inflow paths.

This script is READ ONLY.

It does NOT:
    - classify AL 14.195,
    - modify accounting policy,
    - infer county incidence,
    - allocate HUD assistance geographically,
    - assume recipient address equals economic incidence.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-192A - PBRA ASSISTANCE ACCOUNTING PROFILE'
\echo 'AL 14.195'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m192a_pbra;

CREATE TEMP TABLE m192a_pbra AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '14.195';


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

FROM m192a_pbra;


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

FROM m192a_pbra

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. FUNDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4A. FUNDING AGENCY PROFILE'
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

FROM m192a_pbra

GROUP BY
    funding_agency_name,
    funding_subagency_name

ORDER BY net_obligation DESC;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4B. AWARDING AGENCY PROFILE'
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

FROM m192a_pbra

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

FROM m192a_pbra

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. RECIPIENT CONCENTRATION

Top recipients are sufficient here. We are examining program structure,
not assigning county incidence.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TOP RECIPIENTS'
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
    ) AS net_obligation

FROM m192a_pbra

GROUP BY recipient_name

ORDER BY net_obligation DESC

LIMIT 30;


/*
====================================================================================================
7. AWARD CONCENTRATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TOP AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,

    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date,

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

FROM m192a_pbra

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )

ORDER BY net_obligation DESC

LIMIT 30;


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

FROM m192a_pbra

GROUP BY 1

ORDER BY 1;


/*
====================================================================================================
9. PROVENANCE PROFILE

This is deliberately explicit so IIJA can ultimately be grouped across
program families without becoming a second accounting path.
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

FROM m192a_pbra

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
10. SEMANTIC PROGRAM SCREEN

Purpose:
    Determine whether descriptions distinguish PBRA/project-based assistance
    from HCV/tenant-based voucher assistance.

Hits are evidence for review only.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. SEMANTIC PROGRAM SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH terms(term) AS
(
    VALUES
        ('PROJECT BASED'),
        ('PROJECT-BASED'),
        ('PBRA'),
        ('SECTION 8'),
        ('HOUSING ASSISTANCE PAYMENT'),
        ('HAP'),
        ('MULTIFAMILY'),
        ('RENTAL ASSISTANCE'),
        ('TENANT BASED'),
        ('TENANT-BASED'),
        ('HOUSING CHOICE'),
        ('VOUCHER'),
        ('HCV'),
        ('PUBLIC HOUSING'),
        ('CONTRACT RENEWAL'),
        ('RENEWAL')
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

    ROUND(
        SUM(b.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM terms t

JOIN m192a_pbra b
  ON
       UPPER(
           COALESCE(b.canonical_award_description, '')
       ) LIKE '%' || t.term || '%'

    OR UPPER(
           COALESCE(b.transaction_description, '')
       ) LIKE '%' || t.term || '%'

GROUP BY t.term

ORDER BY net_obligation DESC;


/*
====================================================================================================
11. DESCRIPTION PROFILE

Keep this bounded. We need representative semantics, not thousands of lines.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11A. TOP CANONICAL AWARD DESCRIPTIONS'
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
    ) AS net_obligation

FROM m192a_pbra

GROUP BY canonical_award_description

ORDER BY net_obligation DESC

LIMIT 20;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11B. TOP TRANSACTION DESCRIPTIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        transaction_description,
        '[NULL]'
    ) AS transaction_description,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m192a_pbra

GROUP BY transaction_description

ORDER BY net_obligation DESC

LIMIT 20;


/*
====================================================================================================
12. EXISTING AL 14.195 PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING AL 14.195 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '14.195'

ORDER BY
    methodology_version,
    federal_inflow_program_classification_id;


/*
====================================================================================================
13. EXISTING AL 14.195 POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXISTING AL 14.195 POLICY MAPPING'
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
  AND m.source_program_code = '14.195'

ORDER BY
    m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
14. EXISTING HCV / AL 14.871 POLICY

This is the key internal comparison.

We do not infer overlap merely because both programs provide rental assistance.
We want to establish whether WCFFBP has already accounted for 14.195 through
the HCV policy or whether they are separately identified assistance programs.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14A. EXISTING HCV / AL 14.871 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '14.871'

ORDER BY
    methodology_version,
    federal_inflow_program_classification_id;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14B. EXISTING HCV / AL 14.871 POLICY MAPPING'
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
  AND m.source_program_code = '14.871'

ORDER BY
    m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
15. HOUSING POLICY INVENTORY

Screen our own policy architecture for other housing/rental streams that could
create a plausible accounting-overlap pathway.

Returned rows are not presumed duplicates.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. EXISTING HOUSING / RENTAL POLICY INVENTORY'
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
           LIKE '%HOUSING%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%HOUSING%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%RENTAL%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%RENTAL%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%VOUCHER%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%VOUCHER%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
16. HCV / PBRA AWARD-ID COLLISION SCREEN

A shared award identifier would be important evidence of possible duplication.
No shared identifier would not alone prove independence, but it is a useful
mechanical screen.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. HCV / PBRA AWARD-ID COLLISION SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH pbra_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM m192a_pbra
),

hcv_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number = '14.871'
)

SELECT
    COUNT(*) AS shared_award_identifier_count

FROM pbra_awards p

JOIN hcv_awards h
  ON h.award_identifier = p.award_identifier

WHERE p.award_identifier IS NOT NULL;


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

FROM m192a_pbra;


DO $$
DECLARE
    v_tx      bigint;
    v_amount  numeric;
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

    FROM m192a_pbra;


    IF v_tx = 0 THEN

        RAISE EXCEPTION
            'ETL-192A focal population is empty';

    END IF;


    RAISE NOTICE
        'ETL-192A CLOSURE PASS: tx=% amount=%',
        v_tx,
        ROUND(v_amount, 2);

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-192A COMPLETE'
\echo 'AL 14.195 PBRA'
\echo 'Statewide accounting diagnostic only.'
\echo 'COVID / IIJA / extraordinary retained as orthogonal provenance dimensions.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;