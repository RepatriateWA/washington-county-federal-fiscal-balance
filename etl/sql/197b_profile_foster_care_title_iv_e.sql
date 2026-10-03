/*
====================================================================================================
ETL-197B
FOSTER CARE TITLE IV-E STATEWIDE ACCOUNTING PROFILE

Assistance Listing:
    93.658 - Foster Care Title IV-E

Purpose:
    Profile Washington FY2020-FY2024 USAspending assistance transactions for
    AL 93.658 before making a WCFFBP accounting decision.

Known residual control from ETL-197A:
    Transactions        70
    Awards              23
    Recipients           3
    Net obligation      $762,368,121.74
    COVID                        $0.00
    IIJA                         $0.00
    Extraordinary               $0.00

Primary questions:
    1. Does the certified focal population reproduce ETL-197A?
    2. What federal transfer mechanism and recipients are represented?
    3. What do award descriptions establish about the funded activity?
    4. Are negative adjustments material?
    5. Do focal award identifiers appear under another Assistance Listing?
    6. Is there a plausible overlap pathway with another ACF / Title IV-E
       assistance stream or an existing WCFFBP principal accounting source?
    7. Can AL 93.658 safely receive one program-level accounting disposition?

Important:
    Adjacent child-welfare programs are not automatically duplicates.

    Shared recipient identity is not duplicate-dollar evidence.

    This diagnostic addresses statewide federal-transfer accounting only.
    It does not infer county beneficiary or economic incidence.

No persistent database writes.
No accounting classification.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-197B'
\echo 'FOSTER CARE TITLE IV-E STATEWIDE ACCOUNTING PROFILE'
\echo 'AL 93.658'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197b_foster;

CREATE TEMP TABLE m197b_foster AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.658';


ANALYZE m197b_foster;


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

FROM m197b_foster;


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

    FROM m197b_foster;


    IF v_tx <> 70
       OR v_awards <> 23
       OR v_recip <> 3
       OR ROUND(v_amount, 2) <> 762368121.74
       OR ROUND(v_covid, 2) <> 0.00
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 0.00
    THEN
        RAISE EXCEPTION
            'ETL-197B FOCAL CONTROL FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-197B EXACT FOCAL CONTROL PASS';

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
    ) AS net_obligation

FROM m197b_foster

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

FROM m197b_foster

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

FROM m197b_foster

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

FROM m197b_foster

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
7. RECIPIENT PROFILE

Only three recipients are present, so print all of them.

Recipient identity helps establish transfer semantics but does not establish
county beneficiary incidence.
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

FROM m197b_foster

GROUP BY
    recipient_id,
    recipient_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
8. BUILD AWARD-LEVEL PROFILE
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197b_awards;

CREATE TEMP TABLE m197b_awards AS

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

FROM m197b_foster

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    );


ANALYZE m197b_awards;


/*
====================================================================================================
9. AWARD-LEVEL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. AWARD-LEVEL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS award_count,

    SUM(transaction_count)
        AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation,

    COUNT(*) FILTER
    (
        WHERE negative_transaction_count > 0
    ) AS awards_with_negative_adjustments,

    COUNT(*) FILTER
    (
        WHERE net_obligation < 0
    ) AS negative_net_awards,

    COUNT(*) FILTER
    (
        WHERE net_obligation = 0
    ) AS zero_net_awards

FROM m197b_awards;


/*
====================================================================================================
10. COMPLETE AWARD EVIDENCE

Only 23 awards exist, so print all rather than sample.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. COMPLETE AWARD EVIDENCE'
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

    LEFT(
        COALESCE(
            award_descriptions,
            transaction_descriptions,
            ''
        ),
        2500
    ) AS evidence_excerpt

FROM m197b_awards

ORDER BY ABS(net_obligation) DESC;


/*
====================================================================================================
11. SEMANTIC SCREEN

Discovery only.

The goal is to distinguish ordinary Title IV-E foster-care funding from
anything suggesting a materially different transfer type.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. AWARD SEMANTIC SCREEN'
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

    FROM m197b_awards
)

SELECT
    CASE

        WHEN
               semantic_text LIKE '%foster care%'
            OR semantic_text LIKE '%title iv-e%'
            OR semantic_text LIKE '%title ive%'
            OR semantic_text LIKE '%title iv e%'
        THEN 'EXPLICIT_FOSTER_CARE_OR_TITLE_IV_E'

        WHEN
               semantic_text LIKE '%child welfare%'
            OR semantic_text LIKE '%child placement%'
            OR semantic_text LIKE '%guardianship%'
            OR semantic_text LIKE '%adoption%'
        THEN 'RELATED_CHILD_WELFARE_WORDING'

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
12. SEMANTIC EXCEPTION REVIEW

Print only awards that do not explicitly mention Foster Care or Title IV-E.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. SEMANTIC EXCEPTION REVIEW'
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

    FROM m197b_awards
)

SELECT
    award_identifier,
    recipient_name,
    transaction_count,

    ROUND(
        net_obligation::numeric,
        2
    ) AS net_obligation,

    LEFT(
        COALESCE(
            award_descriptions,
            transaction_descriptions,
            ''
        ),
        2500
    ) AS evidence_excerpt

FROM semantic

WHERE NOT
(
       semantic_text LIKE '%foster care%'
    OR semantic_text LIKE '%title iv-e%'
    OR semantic_text LIKE '%title ive%'
    OR semantic_text LIKE '%title iv e%'
)

ORDER BY ABS(net_obligation) DESC;


/*
====================================================================================================
13. SHARED AWARD IDENTIFIER SCREEN

Strong internal duplicate test:

Do any AL 93.658 award identifiers occur under another Assistance Listing
within the certified Washington FY2020-FY2024 assistance ledger?
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

    FROM m197b_awards

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

        MIN(l.cfda_title)
            AS other_program_title,

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
      AND l.cfda_number <> '93.658'

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
14. SAME RECIPIENT / RELATED HHS-ACF PROGRAM SCREEN

This is deliberately broader than the award-ID screen.

Recipient overlap does NOT establish duplicate dollars.

It tells us which other HHS/ACF assistance programs flow to the same three
recipient identities so that obvious adjacent child-welfare streams are not
mistaken for duplicate Title IV-E Foster Care dollars.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. SAME RECIPIENT / RELATED HHS-ACF PROGRAM SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_recipients AS
(
    SELECT DISTINCT recipient_id
    FROM m197b_foster
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
  AND l.cfda_number <> '93.658'

  AND
  (
         UPPER(COALESCE(l.funding_agency_name, ''))
             LIKE '%HEALTH AND HUMAN SERVICES%'

      OR UPPER(COALESCE(l.awarding_agency_name, ''))
             LIKE '%HEALTH AND HUMAN SERVICES%'

      OR UPPER(COALESCE(l.funding_subagency_name, ''))
             LIKE '%CHILDREN AND FAMILIES%'

      OR UPPER(COALESCE(l.awarding_subagency_name, ''))
             LIKE '%CHILDREN AND FAMILIES%'
  )

GROUP BY l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC

LIMIT 100;


/*
====================================================================================================
15. TITLE IV-E / CHILD-WELFARE PROGRAM NEIGHBORHOOD

Search the complete certified WA assistance universe for program titles
suggesting Title IV-E, foster care, adoption, guardianship, or child welfare.

This is a program-neighborhood inventory, not duplicate-dollar evidence.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. TITLE IV-E / CHILD-WELFARE PROGRAM NEIGHBORHOOD'
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

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM analysis.v_certified_assistance_ledger l

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024

  AND
  (
         UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%FOSTER%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%ADOPTION%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%GUARDIANSHIP%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%CHILD WELFARE%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%TITLE IV-E%'

      OR UPPER(COALESCE(l.cfda_title, ''))
             LIKE '%TITLE IV E%'
  )

GROUP BY l.cfda_number

ORDER BY ABS(SUM(l.federal_action_obligation)) DESC;


/*
====================================================================================================
16. EXISTING AL 93.658 CLASSIFICATION / MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16A. EXISTING AL 93.658 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '93.658'

ORDER BY federal_inflow_program_classification_id;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16B. EXISTING AL 93.658 PROGRAM POLICY MAPPING'
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
  AND source_program_code = '93.658'

ORDER BY federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
17. EXISTING POTENTIALLY RELATED PROGRAM CLASSIFICATIONS

Inspect WCFFBP classifications already assigned to child/family/welfare
programs.

Discovery only.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. RELATED EXISTING PROGRAM CLASSIFICATIONS'
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
       UPPER(COALESCE(source_program_title, '')) LIKE '%FOSTER%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%ADOPTION%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%CHILD WELFARE%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%CHILD CARE%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%CHILDREN%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%CHILD%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%CHILD%'

ORDER BY
    source_system,
    source_program_code,
    federal_inflow_program_classification_id;


/*
====================================================================================================
18. EXISTING POTENTIALLY RELATED SOURCE POLICIES
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. RELATED EXISTING SOURCE POLICIES'
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
       UPPER(COALESCE(inflow_family, '')) LIKE '%CHILD%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%CHILD%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%FOSTER%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%FOSTER%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%WELFARE%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%WELFARE%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
19. FOCAL AWARDS VS OTHER PROGRAM IDENTIFIERS — SUMMARY CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '19. CROSS-LISTING SUMMARY CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT
        award_identifier

    FROM m197b_awards

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
      AND l.cfda_number <> '93.658'
)

SELECT
    COUNT(DISTINCT award_identifier)
        AS focal_awards_cross_listed_elsewhere,

    COUNT(*)
        AS award_program_cross_listings

FROM cross_listed;


/*
====================================================================================================
20. FINAL CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '20. FINAL CLOSURE CONTROL'
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

FROM m197b_foster;


/*
====================================================================================================
21. NO-WRITE CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-197B COMPLETE'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;