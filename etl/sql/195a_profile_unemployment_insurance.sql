/*
====================================================================================================
ETL-195A
UNEMPLOYMENT INSURANCE STATEWIDE ACCOUNTING PROFILE

Assistance Listing:
    17.225 - Unemployment Insurance

Purpose:
    Profile Washington FY2020-FY2024 USAspending assistance transactions for
    AL 17.225 before making any WCFFBP accounting decision.

Primary questions:
    1. What does the approximately $938M population represent?
    2. Does AL 17.225 contain multiple economically distinct funding streams?
    3. Which observations represent:
           - ordinary unemployment-insurance administration,
           - unemployment-benefit funding,
           - pandemic unemployment programs,
           - trust-fund activity,
           - grants or administrative modernization,
           - other identifiable components?
    4. Is there a plausible duplicate-accounting pathway through another
       WCFFBP principal source?
    5. Is program-level treatment defensible, or will award-level /
       transaction-level classification be required?

Important:
    Recipient geography is not treated as county economic incidence.

    COVID and extraordinary provenance are preserved independently from
    accounting classification.

    This diagnostic does not assume that all AL 17.225 dollars represent
    unemployment benefits paid to Washington residents.

No persistent database writes.
No accounting classification.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-195A'
\echo 'UNEMPLOYMENT INSURANCE STATEWIDE ACCOUNTING PROFILE'
\echo 'AL 17.225'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m195a_ui;

CREATE TEMP TABLE m195a_ui AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '17.225';


CREATE INDEX m195a_ui_award_idx
    ON m195a_ui (
        award_id_fain
    );

CREATE INDEX m195a_ui_fy_idx
    ON m195a_ui (
        action_date_fiscal_year
    );

ANALYZE m195a_ui;


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

FROM m195a_ui;


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

FROM m195a_ui

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

FROM m195a_ui

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

FROM m195a_ui

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
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS covid_amount

FROM m195a_ui

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

FROM m195a_ui

GROUP BY recipient_name

ORDER BY ABS(SUM(federal_action_obligation)) DESC
LIMIT 50;


/*
====================================================================================================
8. AWARD-LEVEL PROFILE

This is especially important for AL 17.225 because award identity may expose
distinct UI funding components that should not share one accounting treatment.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. AWARD-LEVEL PROFILE'
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
    )::numeric, 2) AS extraordinary_amount,

    MIN(canonical_award_description)
        AS award_description

FROM m195a_ui

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    )

ORDER BY ABS(SUM(federal_action_obligation)) DESC
LIMIT 200;


/*
====================================================================================================
9. PROVENANCE PARTITION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. COVID / IIJA / EXTRAORDINARY PARTITION'
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

FROM m195a_ui

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
10. COVID VS NON-COVID BY FISCAL YEAR
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. COVID VS NON-COVID BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    CASE
        WHEN is_covid
            THEN 'COVID'
        ELSE 'NON_COVID'
    END AS provenance_class,

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

FROM m195a_ui

GROUP BY
    action_date_fiscal_year,
    CASE
        WHEN is_covid
            THEN 'COVID'
        ELSE 'NON_COVID'
    END

ORDER BY
    action_date_fiscal_year,
    provenance_class;


/*
====================================================================================================
11. DESCRIPTION SAMPLE - LARGEST TRANSACTIONS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. LARGEST TRANSACTION DESCRIPTION SAMPLE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    action_date,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier,

    recipient_name,
    assistance_type_code,
    federal_action_obligation,
    is_covid,
    is_extraordinary,
    transaction_description,
    canonical_award_description

FROM m195a_ui

WHERE federal_action_obligation <> 0

ORDER BY
    ABS(federal_action_obligation) DESC,
    action_date,
    assistance_transaction_id

LIMIT 150;


/*
====================================================================================================
12. SEMANTIC COMPONENT SCREEN

The ordering intentionally gives specific pandemic programs priority over
generic UI terminology.

This is discovery logic only. It is NOT an accounting classification.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. SEMANTIC COMPONENT SCREEN'
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

    FROM m195a_ui
),

classified AS
(
    SELECT
        semantic.*,

        CASE

            WHEN semantic_text ~
                'federal pandemic unemployment compensation|\mfpu[c]?\M'
                THEN 'FPUC'

            WHEN semantic_text ~
                'pandemic unemployment assistance|\mpua\M'
                THEN 'PUA'

            WHEN semantic_text ~
                'pandemic emergency unemployment compensation|\mpeuc\M'
                THEN 'PEUC'

            WHEN semantic_text ~
                'mixed earners unemployment compensation|\mmeuc\M'
                THEN 'MEUC'

            WHEN semantic_text ~
                'lost wages assistance|\mlwa\M'
                THEN 'LOST_WAGES_ASSISTANCE'

            WHEN semantic_text ~
                'emergency unemployment relief|governmental entities|nonprofit'
                THEN 'EMERGENCY_UI_RELIEF'

            WHEN semantic_text ~
                'short.time compensation|short time compensation|\mstc\M'
                THEN 'SHORT_TIME_COMPENSATION'

            WHEN semantic_text ~
                'reemployment services|eligibility assessment|\mresea\M'
                THEN 'RESEA'

            WHEN semantic_text ~
                'identity verification|identity fraud|fraud prevention|fraud'
                THEN 'FRAUD_IDENTITY'

            WHEN semantic_text ~
                'modernization|information technology|\mit\M|technology'
                THEN 'UI_MODERNIZATION_IT'

            WHEN semantic_text ~
                'administration|administrative|admin'
                THEN 'UI_ADMINISTRATION'

            WHEN semantic_text ~
                'benefit payment|benefits|claimant|claimants'
                THEN 'UI_BENEFIT_RELATED'

            WHEN semantic_text ~
                'trust fund|unemployment trust'
                THEN 'UI_TRUST_FUND'

            WHEN semantic_text ~
                'unemployment insurance'
                THEN 'GENERAL_UI'

            ELSE 'OTHER_OR_UNSPECIFIED'

        END AS semantic_component

    FROM semantic
)

SELECT
    semantic_component,

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

FROM classified

GROUP BY semantic_component

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
13. SEMANTIC COMPONENT BY FISCAL YEAR
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. SEMANTIC COMPONENT BY FISCAL YEAR'
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

    FROM m195a_ui
),

classified AS
(
    SELECT
        semantic.*,

        CASE

            WHEN semantic_text ~
                'federal pandemic unemployment compensation|\mfpu[c]?\M'
                THEN 'FPUC'

            WHEN semantic_text ~
                'pandemic unemployment assistance|\mpua\M'
                THEN 'PUA'

            WHEN semantic_text ~
                'pandemic emergency unemployment compensation|\mpeuc\M'
                THEN 'PEUC'

            WHEN semantic_text ~
                'mixed earners unemployment compensation|\mmeuc\M'
                THEN 'MEUC'

            WHEN semantic_text ~
                'lost wages assistance|\mlwa\M'
                THEN 'LOST_WAGES_ASSISTANCE'

            WHEN semantic_text ~
                'emergency unemployment relief|governmental entities|nonprofit'
                THEN 'EMERGENCY_UI_RELIEF'

            WHEN semantic_text ~
                'short.time compensation|short time compensation|\mstc\M'
                THEN 'SHORT_TIME_COMPENSATION'

            WHEN semantic_text ~
                'reemployment services|eligibility assessment|\mresea\M'
                THEN 'RESEA'

            WHEN semantic_text ~
                'identity verification|identity fraud|fraud prevention|fraud'
                THEN 'FRAUD_IDENTITY'

            WHEN semantic_text ~
                'modernization|information technology|\mit\M|technology'
                THEN 'UI_MODERNIZATION_IT'

            WHEN semantic_text ~
                'administration|administrative|admin'
                THEN 'UI_ADMINISTRATION'

            WHEN semantic_text ~
                'benefit payment|benefits|claimant|claimants'
                THEN 'UI_BENEFIT_RELATED'

            WHEN semantic_text ~
                'trust fund|unemployment trust'
                THEN 'UI_TRUST_FUND'

            WHEN semantic_text ~
                'unemployment insurance'
                THEN 'GENERAL_UI'

            ELSE 'OTHER_OR_UNSPECIFIED'

        END AS semantic_component

    FROM semantic
)

SELECT
    action_date_fiscal_year AS fiscal_year,
    semantic_component,

    COUNT(*) AS transaction_count,

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

FROM classified

GROUP BY
    action_date_fiscal_year,
    semantic_component

ORDER BY
    action_date_fiscal_year,
    ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
14. DISTINCT DESCRIPTION INVENTORY

This often exposes funding components that keyword classification misses.
Grouped output prevents hundreds of duplicate description rows.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. DISTINCT DESCRIPTION INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    transaction_description,
    canonical_award_description,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    MIN(action_date)
        AS first_action_date,

    MAX(action_date)
        AS last_action_date,

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

FROM m195a_ui

GROUP BY
    transaction_description,
    canonical_award_description

ORDER BY
    ABS(SUM(federal_action_obligation)) DESC

LIMIT 200;


/*
====================================================================================================
15. EXISTING AL 17.225 CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. EXISTING AL 17.225 PROGRAM CLASSIFICATION'
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
  AND source_program_code = '17.225'

ORDER BY federal_inflow_program_classification_id;


/*
====================================================================================================
16. EXISTING AL 17.225 POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. EXISTING AL 17.225 PROGRAM POLICY MAPPING'
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
  AND source_program_code = '17.225'

ORDER BY federal_inflow_program_policy_mapping_id;


/*
====================================================================================================
17. EXISTING UI / LABOR / SOCIAL-INSURANCE SOURCE POLICIES

Discovery only. Presence here does not establish overlap.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. EXISTING POTENTIALLY RELATED SOURCE POLICIES'
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
       UPPER(COALESCE(inflow_family, '')) LIKE '%UNEMPLOY%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%UNEMPLOY%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%LABOR%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%LABOR%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%INCOME%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%INCOME%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
18. RELATED PROGRAM CLASSIFICATIONS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. RELATED PROGRAM CLASSIFICATIONS'
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
       UPPER(COALESCE(source_program_title, '')) LIKE '%UNEMPLOY%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%EMPLOYMENT%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%WORKFORCE%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%UNEMPLOY%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%UNEMPLOY%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%LABOR%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%LABOR%'

ORDER BY
    source_system,
    source_program_code,
    federal_inflow_program_classification_id;


/*
====================================================================================================
19. SHARED AWARD IDENTIFIER SCREEN

Shared award IDs do not prove duplication. This only identifies whether
AL 17.225 award identifiers also appear under other Assistance Listings.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '19. SHARED AWARD IDENTIFIER SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM m195a_ui

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
      AND l.cfda_number <> '17.225'

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
20. AWARD x FISCAL YEAR x PROVENANCE

Useful if one award contains ordinary and COVID-era funding.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '20. AWARD x FISCAL YEAR x PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier,

    action_date_fiscal_year AS fiscal_year,

    is_covid,
    is_extraordinary,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m195a_ui

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ),
    action_date_fiscal_year,
    is_covid,
    is_extraordinary

ORDER BY
    award_identifier,
    fiscal_year,
    is_covid DESC,
    is_extraordinary DESC;


/*
====================================================================================================
21. CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '21. CLOSURE CONTROL'
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
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS closure_covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS closure_iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS closure_extraordinary_amount

FROM m195a_ui;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-195A COMPLETE'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;