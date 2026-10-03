/*
====================================================================================================
ETL-198A
FEMA INDIVIDUAL AND HOUSEHOLD PROGRAM - OTHER NEEDS ASSISTANCE
STATEWIDE ACCOUNTING PROFILE

Assistance Listing:
    97.050 - Presidential Declared Disaster Assistance to Individuals and
             Households - Other Needs

Purpose:
    Profile Washington FY2020-FY2024 USAspending assistance transactions for
    AL 97.050 before making a WCFFBP accounting decision.

Known residual control from ETL-197A:
    Transactions                 15
    Awards                        2
    Recipients                    2
    Net obligation      $731,476,459.87
    COVID               $731,476,459.87
    IIJA                           $0.00
    Extraordinary       $731,476,459.87

Primary accounting question:
    Is AL 97.050 a distinct FEMA Individual/Household assistance stream, or
    does any plausible duplicate-dollar pathway exist with:

        97.036 - FEMA Public Assistance
        other FEMA disaster Assistance Listings
        another existing WCFFBP principal accounting source?

Important:
    Shared disaster declarations, recipients, COVID provenance, or FEMA agency
    identity do NOT by themselves establish duplicate dollars.

    Shared award identifiers or evidence that the same federal transfer is
    represented through multiple accounting paths WOULD require reconciliation.

No persistent database writes.
No accounting classification.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-198A'
\echo 'FEMA IHP OTHER NEEDS ASSISTANCE STATEWIDE ACCOUNTING PROFILE'
\echo 'AL 97.050'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m198a_focal;

CREATE TEMP TABLE m198a_focal AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '97.050';


ANALYZE m198a_focal;


/*
====================================================================================================
2. EXACT FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. EXACT FOCAL CONTROL'
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

FROM m198a_focal;


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

    FROM m198a_focal;


    IF v_tx <> 15
       OR v_awards <> 2
       OR v_recip <> 2
       OR ROUND(v_amount, 2) <> 731476459.87
       OR ROUND(v_covid, 2) <> 731476459.87
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 731476459.87
    THEN
        RAISE EXCEPTION
            'ETL-198A FOCAL CONTROL FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-198A EXACT FOCAL CONTROL PASS';

END
$$;


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
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS covid_amount

FROM m198a_focal

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

FROM m198a_focal

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

FROM m198a_focal

GROUP BY
    funding_agency_name,
    funding_subagency_name,
    awarding_agency_name,
    awarding_subagency_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
6. ASSISTANCE-MECHANISM PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. ASSISTANCE-MECHANISM PROFILE'
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

FROM m198a_focal

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
    recipient_id,
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
    ) AS net_obligation

FROM m198a_focal

GROUP BY
    recipient_id,
    recipient_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
8. BUILD AWARD-LEVEL PROFILE
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m198a_awards;

CREATE TEMP TABLE m198a_awards AS

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier,

    MIN(recipient_name)
        AS recipient_name,

    COUNT(*) AS transaction_count,

    COUNT(*) FILTER
    (
        WHERE federal_action_obligation > 0
    ) AS positive_transaction_count,

    COUNT(*) FILTER
    (
        WHERE federal_action_obligation < 0
    ) AS negative_transaction_count,

    COUNT(*) FILTER
    (
        WHERE federal_action_obligation = 0
    ) AS zero_transaction_count,

    MIN(action_date)
        AS first_action_date,

    MAX(action_date)
        AS last_action_date,

    SUM(federal_action_obligation)
        AS net_obligation,

    SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0
        END
    ) AS covid_amount,

    STRING_AGG(
        DISTINCT NULLIF(TRIM(canonical_award_description), ''),
        ' || '
        ORDER BY NULLIF(TRIM(canonical_award_description), '')
    ) AS award_descriptions,

    STRING_AGG(
        DISTINCT NULLIF(TRIM(transaction_description), ''),
        ' || '
        ORDER BY NULLIF(TRIM(transaction_description), '')
    ) AS transaction_descriptions

FROM m198a_focal

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    );


ANALYZE m198a_awards;


/*
====================================================================================================
9. COMPLETE AWARD EVIDENCE

Only two awards exist. Print both.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. COMPLETE AWARD EVIDENCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    award_identifier,
    recipient_name,
    transaction_count,
    positive_transaction_count,
    negative_transaction_count,
    zero_transaction_count,
    first_action_date,
    last_action_date,

    ROUND(
        net_obligation::numeric,
        2
    ) AS net_obligation,

    ROUND(
        covid_amount::numeric,
        2
    ) AS covid_amount,

    LEFT(
        COALESCE(
            award_descriptions,
            transaction_descriptions,
            ''
        ),
        4000
    ) AS evidence_excerpt

FROM m198a_awards

ORDER BY ABS(net_obligation) DESC;


/*
====================================================================================================
10. AWARD-LEVEL CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. AWARD-LEVEL CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS award_count,

    SUM(transaction_count)
        AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(covid_amount)::numeric,
        2
    ) AS covid_amount,

    COUNT(*) FILTER
    (
        WHERE negative_transaction_count > 0
    ) AS awards_with_negative_adjustments,

    COUNT(*) FILTER
    (
        WHERE net_obligation < 0
    ) AS negative_net_awards

FROM m198a_awards;


/*
====================================================================================================
11. SHARED AWARD IDENTIFIER SCREEN — ALL OTHER ASSISTANCE LISTINGS

This is the strongest internal duplicate-dollar screen.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. SHARED AWARD IDENTIFIER SCREEN - ALL OTHER ASSISTANCE LISTINGS'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT award_identifier
    FROM m198a_awards
    WHERE award_identifier IS NOT NULL
)

SELECT
    f.award_identifier,

    l.cfda_number
        AS other_assistance_listing,

    MIN(l.cfda_title)
        AS other_program_title,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM focal_awards f

JOIN analysis.v_certified_assistance_ledger l
  ON f.award_identifier =
     COALESCE(
         NULLIF(l.award_id_fain, ''),
         NULLIF(l.award_id_uri, '')
     )

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number <> '97.050'

GROUP BY
    f.award_identifier,
    l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC;


/*
====================================================================================================
12. DIRECT 97.050 VS 97.036 AWARD-ID COLLISION CONTROL

AL 97.036 FEMA Public Assistance is already INCLUDE_ADDITIVE in WCFFBP.

A shared award identifier here would be a material warning.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. DIRECT 97.050 VS 97.036 AWARD-ID COLLISION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT award_identifier
    FROM m198a_awards
    WHERE award_identifier IS NOT NULL
),

public_assistance_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number = '97.036'
)

SELECT
    COUNT(*) AS shared_award_identifier_count

FROM focal_awards f

JOIN public_assistance_awards p
  ON p.award_identifier = f.award_identifier;


/*
====================================================================================================
13. FEMA DISASTER PROGRAM NEIGHBORHOOD

Discovery only.

Separate FEMA Assistance Listings may serve the same disaster while funding
different statutory/programmatic purposes. Presence in this table is not
duplicate-dollar evidence.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. FEMA DISASTER PROGRAM NEIGHBORHOOD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    l.cfda_number
        AS assistance_listing,

    MIN(l.cfda_title)
        AS program_title,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        )
    ) AS award_count,

    COUNT(DISTINCT l.recipient_id)
        AS recipient_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN l.is_covid
             THEN l.federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN l.is_extraordinary
             THEN l.federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM analysis.v_certified_assistance_ledger l

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024

  AND
  (
         l.cfda_number LIKE '97.%'

      OR UPPER(COALESCE(l.funding_agency_name, ''))
             LIKE '%FEDERAL EMERGENCY MANAGEMENT%'

      OR UPPER(COALESCE(l.awarding_agency_name, ''))
             LIKE '%FEDERAL EMERGENCY MANAGEMENT%'
  )

GROUP BY l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC

LIMIT 100;


/*
====================================================================================================
14. SAME RECIPIENT / FEMA PROGRAM SCREEN

Shared recipients do not establish duplicate dollars.

This tells us whether the focal recipients also administer other FEMA streams.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. SAME RECIPIENT / FEMA PROGRAM SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_recipients AS
(
    SELECT DISTINCT recipient_id
    FROM m198a_focal
    WHERE recipient_id IS NOT NULL
)

SELECT
    l.cfda_number
        AS other_assistance_listing,

    MIN(l.cfda_title)
        AS other_program_title,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        )
    ) AS award_count,

    COUNT(DISTINCT l.recipient_id)
        AS shared_recipient_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM analysis.v_certified_assistance_ledger l

JOIN focal_recipients r
  ON r.recipient_id = l.recipient_id

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number <> '97.050'

  AND
  (
         l.cfda_number LIKE '97.%'

      OR UPPER(COALESCE(l.funding_agency_name, ''))
             LIKE '%FEDERAL EMERGENCY MANAGEMENT%'

      OR UPPER(COALESCE(l.awarding_agency_name, ''))
             LIKE '%FEDERAL EMERGENCY MANAGEMENT%'
  )

GROUP BY l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC;


/*
====================================================================================================
15. EXISTING 97.050 CLASSIFICATION / MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15A. EXISTING AL 97.050 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '97.050'

ORDER BY federal_inflow_program_classification_id;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15B. EXISTING AL 97.050 PROGRAM POLICY MAPPING'
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

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '97.050'

ORDER BY federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
16. EXISTING FEMA / DISASTER PROGRAM CLASSIFICATIONS

We particularly want to recover the already-persisted 97.036 treatment.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. EXISTING FEMA / DISASTER PROGRAM CLASSIFICATIONS'
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

WHERE source_system = 'USASPENDING_ASSISTANCE'

  AND
  (
         source_program_code LIKE '97.%'
      OR UPPER(COALESCE(source_program_title, ''))
             LIKE '%FEMA%'
      OR UPPER(COALESCE(source_program_title, ''))
             LIKE '%DISASTER%'
      OR UPPER(COALESCE(inflow_family, ''))
             LIKE '%DISASTER%'
      OR UPPER(COALESCE(inflow_subfamily, ''))
             LIKE '%DISASTER%'
  )

ORDER BY
    source_program_code,
    federal_inflow_program_classification_id;


/*
====================================================================================================
17. EXISTING FEMA / DISASTER SOURCE POLICIES
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. EXISTING FEMA / DISASTER SOURCE POLICIES'
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

WHERE
       UPPER(COALESCE(inflow_family, ''))
           LIKE '%DISASTER%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%DISASTER%'

    OR UPPER(COALESCE(inflow_family, ''))
           LIKE '%FEMA%'

    OR UPPER(COALESCE(inflow_subfamily, ''))
           LIKE '%FEMA%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
18. CROSS-LISTING SUMMARY CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. CROSS-LISTING SUMMARY CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT award_identifier
    FROM m198a_awards
    WHERE award_identifier IS NOT NULL
),

cross_listed AS
(
    SELECT DISTINCT
        f.award_identifier,
        l.cfda_number

    FROM focal_awards f

    JOIN analysis.v_certified_assistance_ledger l
      ON f.award_identifier =
         COALESCE(
             NULLIF(l.award_id_fain, ''),
             NULLIF(l.award_id_uri, '')
         )

    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number <> '97.050'
)

SELECT
    COUNT(DISTINCT award_identifier)
        AS focal_awards_cross_listed_elsewhere,

    COUNT(*)
        AS award_program_cross_listings

FROM cross_listed;


/*
====================================================================================================
19. FINAL FOCAL CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '19. FINAL FOCAL CLOSURE CONTROL'
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

FROM m198a_focal;


/*
====================================================================================================
20. NO-WRITE CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-198A COMPLETE'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;