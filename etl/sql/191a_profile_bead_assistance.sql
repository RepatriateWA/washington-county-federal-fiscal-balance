/*
====================================================================================================
ETL-191A
BROADBAND EQUITY, ACCESS, AND DEPLOYMENT (BEAD)
ASSISTANCE ACCOUNTING PROFILE
AL 11.035
====================================================================================================

Purpose:
    Profile Washington FY2020-FY2024 USAspending Assistance Listing 11.035
    for statewide federal-inflow accounting.

Primary questions:
    1. What is the exact certified focal population?
    2. Is the ~$1.228B concentrated in one/few awards or broadly distributed?
    3. In what fiscal year(s) was the federal obligation recorded?
    4. What assistance mechanism is represented?
    5. Who is the recipient?
    6. What do award and transaction descriptions say?
    7. Are there negative or zero-dollar adjustments?
    8. How completely is the population tagged IIJA / extraordinary?
    9. Does the data suggest an overlap pathway with another WCFFBP
       principal accounting source?
   10. Does the award structure raise a timing/recognition issue that should
       be preserved separately from the obligation-based accounting measure?

This script is READ ONLY.

It does NOT:
    - classify BEAD,
    - write accounting policy,
    - decide expenditure recognition,
    - infer county incidence,
    - allocate broadband dollars geographically.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-191A - BEAD ASSISTANCE ACCOUNTING PROFILE'
\echo 'AL 11.035'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m191a_bead;

CREATE TEMP TABLE m191a_bead AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '11.035';


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

FROM m191a_bead;


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

FROM m191a_bead

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. ACTION-DATE CONCENTRATION

BEAD may contain a very large obligation action. Show individual action dates.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. ACTION-DATE CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date,

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

FROM m191a_bead

GROUP BY action_date

ORDER BY
    net_obligation DESC,
    action_date;


/*
====================================================================================================
5. AWARD CONCENTRATION

Show every award if cardinality is small.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. AWARD CONCENTRATION'
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

FROM m191a_bead

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. FUNDING / AWARDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6A. FUNDING AGENCY PROFILE'
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

FROM m191a_bead

GROUP BY
    funding_agency_name,
    funding_subagency_name

ORDER BY net_obligation DESC;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6B. AWARDING AGENCY PROFILE'
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

FROM m191a_bead

GROUP BY
    awarding_agency_name,
    awarding_subagency_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
7. ASSISTANCE TYPE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. ASSISTANCE-TYPE PROFILE'
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

FROM m191a_bead

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY net_obligation DESC;


/*
====================================================================================================
8. RECIPIENT PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. RECIPIENT PROFILE'
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

    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m191a_bead

GROUP BY recipient_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
9. TRANSACTION SIGN PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TRANSACTION SIGN PROFILE'
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

FROM m191a_bead

GROUP BY 1

ORDER BY 1;


/*
====================================================================================================
10. INDIVIDUAL TRANSACTION PROFILE

BEAD is expected to have low transaction cardinality. Showing all transactions
will tell us whether the large amount is one initial obligation, later
supplements, administrative actions, or some combination.

====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. INDIVIDUAL TRANSACTION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    assistance_transaction_id,
    action_date,
    action_date_fiscal_year AS fiscal_year,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,

    recipient_name,

    ROUND(
        federal_action_obligation::numeric,
        2
    ) AS federal_action_obligation,

    is_covid,
    is_iija,
    is_extraordinary,

    canonical_award_description,
    transaction_description

FROM m191a_bead

ORDER BY
    action_date,
    assistance_transaction_id;


/*
====================================================================================================
11. PROVENANCE PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. COVID / IIJA / EXTRAORDINARY PROVENANCE'
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

FROM m191a_bead

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
12. DESCRIPTION PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. CANONICAL AWARD DESCRIPTION PROFILE'
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

FROM m191a_bead

GROUP BY canonical_award_description

ORDER BY net_obligation DESC;


/*
====================================================================================================
13. TRANSACTION-DESCRIPTION PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. TRANSACTION-DESCRIPTION PROFILE'
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

FROM m191a_bead

GROUP BY transaction_description

ORDER BY net_obligation DESC;


/*
====================================================================================================
14. SEMANTIC TIMING / FUNDING SEARCH

These terms may distinguish:
    - initial planning grants,
    - implementation awards,
    - allocation/authorization language,
    - actual reimbursement/payment language.

A hit does not itself determine accounting treatment.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. SEMANTIC TIMING / FUNDING SEARCH'
\echo '----------------------------------------------------------------------------------------------------'

WITH terms(term) AS
(
    VALUES
        ('PLANNING'),
        ('INITIAL PROPOSAL'),
        ('FINAL PROPOSAL'),
        ('IMPLEMENTATION'),
        ('ALLOCATION'),
        ('ALLOCATED'),
        ('OBLIGATION'),
        ('OBLIGATED'),
        ('REIMBURSEMENT'),
        ('REIMBURSE'),
        ('EXPENDITURE'),
        ('EXPENDED'),
        ('DRAW'),
        ('DISBURSE'),
        ('SUBGRANT'),
        ('SUBAWARD'),
        ('BROADBAND'),
        ('BEAD'),
        ('INFRASTRUCTURE INVESTMENT'),
        ('IIJA'),
        ('BIPARTISAN INFRASTRUCTURE')
)

SELECT
    t.term AS semantic_term,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(b.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM terms t

JOIN m191a_bead b
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
15. EXISTING WCFFBP PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. EXISTING WCFFBP PROGRAM CLASSIFICATION'
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
  AND source_program_code = '11.035'

ORDER BY
    methodology_version,
    federal_inflow_program_classification_id;


/*
====================================================================================================
16. EXISTING PROGRAM POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. EXISTING PROGRAM POLICY MAPPING'
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
  AND m.source_program_code = '11.035'

ORDER BY
    m.federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
17. POSSIBLE BROADBAND / INFRASTRUCTURE POLICY OVERLAP SEARCH

This is only a screen of our own existing accounting-policy inventory.
It does not assert that any returned policy overlaps BEAD.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. POSSIBLE BROADBAND / INFRASTRUCTURE POLICY OVERLAP SEARCH'
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
           LIKE '%BROADBAND%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%BROADBAND%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%INFRASTRUCTURE%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%INFRASTRUCTURE%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%ECONOMIC DEVELOPMENT%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%ECONOMIC DEVELOPMENT%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


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

FROM m191a_bead;


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

    FROM m191a_bead;


    IF v_tx = 0 THEN

        RAISE EXCEPTION
            'ETL-191A focal population is empty';

    END IF;


    RAISE NOTICE
        'ETL-191A CLOSURE PASS: tx=% amount=%',
        v_tx,
        ROUND(v_amount, 2);

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-191A COMPLETE'
\echo 'AL 11.035 Broadband Equity, Access, and Deployment'
\echo 'Statewide accounting diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No expenditure-recognition decision.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;