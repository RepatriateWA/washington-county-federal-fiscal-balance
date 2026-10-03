/*
====================================================================================================
ETL-196A
RESTAURANT REVITALIZATION FUND STATEWIDE ACCOUNTING PROFILE

Assistance Listing:
    59.078 - Restaurant Revitalization Fund

Purpose:
    Profile Washington FY2020-FY2024 USAspending assistance transactions for
    AL 59.078 before making a WCFFBP accounting decision.

Primary questions:
    1. What is the exact certified statewide population?
    2. What federal transfer mechanism do these observations represent?
    3. Is the population entirely COVID / extraordinary?
    4. Are negative adjustments or zero-dollar records material?
    5. Is there evidence that AL 59.078 overlaps another Assistance Listing,
       award population, or existing WCFFBP principal accounting source?
    6. Can AL 59.078 safely receive one program-level accounting disposition?

Important:
    This diagnostic tests federal-transfer accounting.

    It does NOT infer county economic incidence from recipient geography.

    COVID and extraordinary provenance remain orthogonal to accounting
    disposition.

No persistent database writes.
No accounting classification.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-196A'
\echo 'RESTAURANT REVITALIZATION FUND STATEWIDE ACCOUNTING PROFILE'
\echo 'AL 59.078'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m196a_rrf;

CREATE TEMP TABLE m196a_rrf AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '59.078';


ANALYZE m196a_rrf;


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

FROM m196a_rrf;


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
            WHEN is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m196a_rrf

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

FROM m196a_rrf

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

FROM m196a_rrf

GROUP BY
    funding_agency_name,
    funding_subagency_name,
    awarding_agency_name,
    awarding_subagency_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
6. ASSISTANCE MECHANISM PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. ASSISTANCE MECHANISM PROFILE'
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

FROM m196a_rrf

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
7. PROVENANCE PARTITION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. COVID / IIJA / EXTRAORDINARY PARTITION'
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

FROM m196a_rrf

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
8. RECIPIENT CONCENTRATION

Top recipients only. Recipient identity is useful for semantic validation,
not county-incidence inference.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TOP RECIPIENTS'
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
    ) AS net_obligation

FROM m196a_rrf

GROUP BY recipient_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC

LIMIT 30;


/*
====================================================================================================
9. AWARD-LEVEL DISTRIBUTION

Rather than print every award, summarize award magnitudes and adjustment
behavior.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m196a_awards;

CREATE TEMP TABLE m196a_awards AS

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
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS covid_amount,

    BOOL_OR(is_covid)
        AS has_covid,

    BOOL_OR(is_iija)
        AS has_iija,

    BOOL_OR(is_extraordinary)
        AS has_extraordinary,

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

FROM m196a_rrf

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    );


ANALYZE m196a_awards;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9A. AWARD-LEVEL CONTROL'
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
        WHERE net_obligation = 0
    ) AS zero_net_awards

FROM m196a_awards;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9B. AWARD-SIZE DISTRIBUTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    CASE
        WHEN net_obligation < 0
            THEN 'NEGATIVE_NET'

        WHEN net_obligation = 0
            THEN 'ZERO_NET'

        WHEN net_obligation <= 50000
            THEN '01 <= $50K'

        WHEN net_obligation <= 150000
            THEN '02 $50K-$150K'

        WHEN net_obligation <= 500000
            THEN '03 $150K-$500K'

        WHEN net_obligation <= 1000000
            THEN '04 $500K-$1M'

        WHEN net_obligation <= 5000000
            THEN '05 $1M-$5M'

        ELSE '06 > $5M'
    END AS award_size_band,

    COUNT(*) AS award_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation

FROM m196a_awards

GROUP BY 1
ORDER BY 1;


/*
====================================================================================================
10. LARGEST AWARDS / DESCRIPTION EVIDENCE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. LARGEST AWARDS / DESCRIPTION EVIDENCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    award_identifier,
    recipient_name,
    transaction_count,
    first_action_date,
    last_action_date,

    ROUND(net_obligation::numeric, 2)
        AS net_obligation,

    has_covid,
    has_iija,
    has_extraordinary,

    LEFT(
        COALESCE(
            award_descriptions,
            transaction_descriptions,
            ''
        ),
        2000
    ) AS evidence_excerpt

FROM m196a_awards

ORDER BY ABS(net_obligation) DESC

LIMIT 50;


/*
====================================================================================================
11. DESCRIPTION SEMANTIC SCREEN

Discovery only. Not an accounting classification.

We want to establish whether descriptions consistently identify RRF and
COVID-pandemic restaurant relief, and whether anything appears to represent
a materially different program.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. DESCRIPTION SEMANTIC SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH semantic AS
(
    SELECT
        *,

        LOWER(
            COALESCE(award_descriptions, '')
            || ' '
            || COALESCE(transaction_descriptions, '')
        ) AS semantic_text

    FROM m196a_awards
)

SELECT
    CASE

        WHEN
               semantic_text LIKE '%restaurant revitalization%'
            OR semantic_text LIKE '%restaurant revitalisation%'
        THEN 'EXPLICIT_RRF'

        WHEN
               semantic_text LIKE '%american rescue plan%'
            OR semantic_text LIKE '%arpa%'
            OR semantic_text LIKE '%covid%'
            OR semantic_text LIKE '%coronavirus%'
        THEN 'PANDEMIC_RELIEF_OTHER_WORDING'

        WHEN TRIM(semantic_text) = ''
        THEN 'NO_DESCRIPTION'

        ELSE 'OTHER_DESCRIPTION'

    END AS semantic_class,

    COUNT(*) AS award_count,

    SUM(transaction_count)
        AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation

FROM semantic

GROUP BY 1

ORDER BY ABS(SUM(net_obligation)) DESC;


/*
====================================================================================================
12. NON-RRF / SPARSE DESCRIPTION REVIEW

Print only awards not explicitly identified as Restaurant Revitalization Fund
by description. These are the only semantic exceptions requiring human review.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. NON-RRF / SPARSE DESCRIPTION REVIEW'
\echo '----------------------------------------------------------------------------------------------------'

WITH semantic AS
(
    SELECT
        *,

        LOWER(
            COALESCE(award_descriptions, '')
            || ' '
            || COALESCE(transaction_descriptions, '')
        ) AS semantic_text

    FROM m196a_awards
)

SELECT
    award_identifier,
    recipient_name,
    transaction_count,

    ROUND(net_obligation::numeric, 2)
        AS net_obligation,

    LEFT(
        COALESCE(
            award_descriptions,
            transaction_descriptions,
            ''
        ),
        2500
    ) AS evidence_excerpt

FROM semantic

WHERE semantic_text NOT LIKE '%restaurant revitalization%'
  AND semantic_text NOT LIKE '%restaurant revitalisation%'

ORDER BY ABS(net_obligation) DESC

LIMIT 100;


/*
====================================================================================================
13. SHARED AWARD IDENTIFIER SCREEN

Question:
    Do any AL 59.078 award identifiers also appear under another Assistance
    Listing in the Washington FY2020-FY2024 certified ledger?

Shared IDs would trigger further review; absence substantially lowers
USAspending-internal duplicate risk.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. SHARED AWARD IDENTIFIER SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT
        award_identifier

    FROM m196a_awards

    WHERE award_identifier IS NOT NULL
),

other_programs AS
(
    SELECT
        COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        ) AS award_identifier,

        l.cfda_number
            AS other_assistance_listing,

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
      AND l.cfda_number <> '59.078'

    GROUP BY
        COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        ),
        l.cfda_number
)

SELECT *
FROM other_programs

ORDER BY
    ABS(net_obligation) DESC,
    award_identifier,
    other_assistance_listing;


/*
====================================================================================================
14. EXISTING AL 59.078 CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EXISTING AL 59.078 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '59.078'

ORDER BY federal_inflow_program_classification_id;


/*
====================================================================================================
15. EXISTING AL 59.078 POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. EXISTING AL 59.078 PROGRAM POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '59.078'

ORDER BY federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
16. EXISTING POTENTIALLY RELATED SBA / BUSINESS-RELIEF CLASSIFICATIONS

Discovery only.

We are looking for existing accounting treatment of other SBA pandemic
assistance streams that might establish an overlap pathway or a useful
methodological precedent.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. RELATED SBA / BUSINESS-RELIEF PROGRAM CLASSIFICATIONS'
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
       UPPER(COALESCE(source_program_title, '')) LIKE '%RESTAURANT%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%SMALL BUSINESS%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%PAYCHECK%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%ECONOMIC INJURY%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%SHUTTERED%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%BUSINESS%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%BUSINESS%'

ORDER BY
    source_system,
    source_program_code,
    federal_inflow_program_classification_id;


/*
====================================================================================================
17. EXISTING POTENTIALLY RELATED SOURCE POLICIES
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. RELATED SOURCE POLICIES'
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
       UPPER(COALESCE(inflow_family, '')) LIKE '%BUSINESS%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%BUSINESS%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%PANDEMIC%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%PANDEMIC%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%ECONOMIC%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%ECONOMIC%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%RESTAURANT%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%RESTAURANT%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
18. SAME RECIPIENT / OTHER SBA PROGRAM SCREEN

Recipient overlap does NOT establish duplicate dollars.

This screen simply tells us whether RRF recipients also received other SBA
assistance programs. We deliberately aggregate by other Assistance Listing
rather than printing thousands of recipient rows.

A positive result is expected conceptually and is not itself an accounting
problem.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. SAME RECIPIENT / OTHER SBA PROGRAM SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_recipients AS
(
    SELECT DISTINCT recipient_id
    FROM m196a_rrf
    WHERE recipient_id IS NOT NULL
)

SELECT
    l.cfda_number
        AS other_assistance_listing,

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
  AND l.cfda_number <> '59.078'

  AND (
         UPPER(COALESCE(l.funding_agency_name, ''))
             LIKE '%SMALL BUSINESS%'

      OR UPPER(COALESCE(l.awarding_agency_name, ''))
             LIKE '%SMALL BUSINESS%'
  )

GROUP BY l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC

LIMIT 100;


/*
====================================================================================================
19. FINAL CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '19. FINAL CLOSURE CONTROL'
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

FROM m196a_rrf;


/*
====================================================================================================
20. NO-WRITE CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-196A COMPLETE'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;