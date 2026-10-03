/*
====================================================================================================
ETL-199A
CHILD CARE MANDATORY AND MATCHING FUNDS OF THE CHILD CARE AND DEVELOPMENT FUND
STATEWIDE ACCOUNTING PROFILE

Assistance Listing:
    93.596 - Child Care Mandatory and Matching Funds of the Child Care and
             Development Fund

Purpose:
    Determine whether AL 93.596 is a distinct additive federal child-care
    assistance stream for WCFFBP statewide accounting.

Primary accounting questions:
    1. Does AL 93.596 have any award-ID collision with AL 93.575
       Child Care and Development Block Grant?

    2. Does AL 93.596 have any award-ID collision with another Assistance
       Listing?

    3. Does the transaction/award evidence support treating 93.596 as a
       distinct mandatory/matching CCDF federal funding stream?

    4. Is there evidence in the certified transaction data that would require
       reconciliation with TANF before inclusion?

Important:
    Related program purpose, common administration, common recipients, or
    participation in the broader CCDF structure does NOT by itself establish
    duplicate dollars.

    TANF transfers into child care must not be counted twice. This diagnostic
    therefore examines the relationship but does not presume either duplication
    or independence.

No persistent database writes.
No accounting classification.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-199A'
\echo 'CHILD CARE MANDATORY / MATCHING FUNDS STATEWIDE ACCOUNTING PROFILE'
\echo 'AL 93.596'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m199a_focal;

CREATE TEMP TABLE m199a_focal AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.596';


ANALYZE m199a_focal;


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

FROM m199a_focal;


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
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m199a_focal

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
        WHEN federal_action_obligation > 0 THEN 'POSITIVE'
        WHEN federal_action_obligation < 0 THEN 'NEGATIVE'
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

FROM m199a_focal

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

FROM m199a_focal

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

FROM m199a_focal

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

FROM m199a_focal

GROUP BY
    recipient_id,
    recipient_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
8. BUILD AWARD PROFILE
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m199a_awards;

CREATE TEMP TABLE m199a_awards AS

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

    SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0
        END
    ) AS iija_amount,

    SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0
        END
    ) AS extraordinary_amount,

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

FROM m199a_focal

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    );


ANALYZE m199a_awards;


/*
====================================================================================================
9. COMPLETE AWARD EVIDENCE

Expected to remain compact enough to print in full.
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

    ROUND(net_obligation::numeric, 2)
        AS net_obligation,

    ROUND(covid_amount::numeric, 2)
        AS covid_amount,

    ROUND(iija_amount::numeric, 2)
        AS iija_amount,

    ROUND(extraordinary_amount::numeric, 2)
        AS extraordinary_amount,

    LEFT(
        COALESCE(
            award_descriptions,
            transaction_descriptions,
            ''
        ),
        4000
    ) AS evidence_excerpt

FROM m199a_awards

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

    ROUND(
        SUM(iija_amount)::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(extraordinary_amount)::numeric,
        2
    ) AS extraordinary_amount,

    COUNT(*) FILTER
    (
        WHERE negative_transaction_count > 0
    ) AS awards_with_negative_adjustments,

    COUNT(*) FILTER
    (
        WHERE net_obligation < 0
    ) AS negative_net_awards

FROM m199a_awards;


/*
====================================================================================================
11. DIRECT 93.596 VS 93.575 AWARD-ID COLLISION

This is the primary CCDF duplicate-dollar test.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. DIRECT 93.596 VS 93.575 AWARD-ID COLLISION'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT award_identifier
    FROM m199a_awards
    WHERE award_identifier IS NOT NULL
),

ccdbg_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number = '93.575'
)

SELECT
    COUNT(*) AS shared_award_identifier_count

FROM focal_awards f

JOIN ccdbg_awards c
  ON c.award_identifier = f.award_identifier;


/*
====================================================================================================
12. SHARED AWARD IDENTIFIER SCREEN — ALL OTHER ASSISTANCE LISTINGS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. SHARED AWARD IDENTIFIER SCREEN - ALL OTHER ASSISTANCE LISTINGS'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT award_identifier
    FROM m199a_awards
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
  AND l.cfda_number <> '93.596'

GROUP BY
    f.award_identifier,
    l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC;


/*
====================================================================================================
13. CHILD-CARE / TANF PROGRAM NEIGHBORHOOD

Discovery only.

This intentionally includes the already-classified CCDBG and TANF programs.
Related program identity is not duplicate-dollar evidence.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. CHILD-CARE / TANF PROGRAM NEIGHBORHOOD'
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
         l.cfda_number IN
         (
             '93.575',
             '93.596',
             '93.558'
         )

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%CHILD CARE%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%CHILDCARE%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%TEMPORARY ASSISTANCE FOR NEEDY FAMILIES%'
  )

GROUP BY l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC;


/*
====================================================================================================
14. SAME-RECIPIENT RELATED-PROGRAM SCREEN

Shared recipients are weak evidence only.

This identifies other child-care/TANF programs administered by the same focal
recipient entities.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. SAME-RECIPIENT RELATED-PROGRAM SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_recipients AS
(
    SELECT DISTINCT recipient_id
    FROM m199a_focal
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
  AND l.cfda_number <> '93.596'

  AND
  (
         l.cfda_number IN
         (
             '93.575',
             '93.558'
         )

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%CHILD CARE%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%CHILDCARE%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%TEMPORARY ASSISTANCE FOR NEEDY FAMILIES%'
  )

GROUP BY l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC;


/*
====================================================================================================
15. DESCRIPTION SCREEN FOR TRANSFER / TANF / MANDATORY / MATCHING LANGUAGE

This does NOT prove accounting treatment.

It tells us whether the transaction evidence itself contains language that
would justify a deeper TANF-transfer reconciliation.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. DESCRIPTION SCREEN FOR TRANSFER / TANF / MANDATORY / MATCHING LANGUAGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier,

    action_date,

    ROUND(
        federal_action_obligation::numeric,
        2
    ) AS federal_action_obligation,

    LEFT(
        COALESCE(
            NULLIF(TRIM(transaction_description), ''),
            NULLIF(TRIM(canonical_award_description), ''),
            ''
        ),
        1000
    ) AS description

FROM m199a_focal

WHERE
       UPPER(COALESCE(transaction_description, ''))
           LIKE '%TANF%'

    OR UPPER(COALESCE(canonical_award_description, ''))
           LIKE '%TANF%'

    OR UPPER(COALESCE(transaction_description, ''))
           LIKE '%TRANSFER%'

    OR UPPER(COALESCE(canonical_award_description, ''))
           LIKE '%TRANSFER%'

    OR UPPER(COALESCE(transaction_description, ''))
           LIKE '%MANDATORY%'

    OR UPPER(COALESCE(canonical_award_description, ''))
           LIKE '%MANDATORY%'

    OR UPPER(COALESCE(transaction_description, ''))
           LIKE '%MATCHING%'

    OR UPPER(COALESCE(canonical_award_description, ''))
           LIKE '%MATCHING%'

ORDER BY
    action_date,
    award_identifier;


/*
====================================================================================================
16. EXISTING 93.596 CLASSIFICATION / MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16A. EXISTING AL 93.596 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '93.596'

ORDER BY federal_inflow_program_classification_id;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16B. EXISTING AL 93.596 PROGRAM POLICY MAPPING'
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
  AND source_program_code = '93.596'

ORDER BY federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
17. EXISTING RELATED PROGRAM CLASSIFICATIONS

Recover the WCFFBP treatment of:
    93.575 CCDBG
    93.558 TANF
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. EXISTING RELATED PROGRAM CLASSIFICATIONS'
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
  AND source_program_code IN
      (
          '93.575',
          '93.558'
      )

ORDER BY source_program_code;


/*
====================================================================================================
18. EXISTING RELATED SOURCE POLICIES
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. EXISTING RELATED SOURCE POLICIES'
\echo '----------------------------------------------------------------------------------------------------'

SELECT DISTINCT
    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN
      (
          '93.575',
          '93.558'
      )

ORDER BY
    p.inflow_family,
    p.inflow_subfamily;


/*
====================================================================================================
19. CROSS-LISTING SUMMARY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '19. CROSS-LISTING SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT award_identifier
    FROM m199a_awards
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
      AND l.cfda_number <> '93.596'
)

SELECT
    COUNT(DISTINCT award_identifier)
        AS focal_awards_cross_listed_elsewhere,

    COUNT(*)
        AS award_program_cross_listings

FROM cross_listed;


/*
====================================================================================================
20. FINAL FOCAL CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '20. FINAL FOCAL CLOSURE'
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

FROM m199a_focal;


/*
====================================================================================================
21. NO-WRITE CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-199A COMPLETE'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;