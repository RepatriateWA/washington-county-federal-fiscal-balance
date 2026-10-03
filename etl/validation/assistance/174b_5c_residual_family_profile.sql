/* =====================================================================
   ETL-174B-5C
   WASHINGTON FEDERAL INFLOWS
   POST-OVERLAP RESIDUAL ASSISTANCE FAMILY PROFILE

   READ ONLY -- NO DATABASE WRITES

   Purpose:
     Partition the remaining FY2020-FY2024 USAspending assistance
     review universe into broad analytical families.

   Already removed from the review universe:
     - SSA OASDI: 96.001, 96.002, 96.004
     - SSI:       96.006 (affirmatively INCLUDE)
     - Medicaid:  93.778
     - Medicare:  93.770, 93.773, 93.774
     - VA:        64.*
     - CHIP core state T21 awards classified EXCLUDE_DUPLICATE

   CHIP Healthy Kids Together remains unresolved.

   IMPORTANT:
     Family assignment in this query is DESCRIPTIVE ONLY.
     It does not authorize inclusion in the federal-inflow ledger.

     COVID, IIJA, and extraordinary status remain independent
     characteristics and are not accounting dispositions.

   Expected post-SSI review control:
     $107,679,175,964.03
   ===================================================================== */


\pset pager off


/* =====================================================================
   1. BUILD ANALYTICAL UNIVERSE
   ===================================================================== */

WITH classified AS (

    SELECT
        l.*,

        ac.accounting_disposition AS award_accounting_disposition,

        CASE

            /* ---------------------------------------------------------
               Explicit already-ledgered overlap
               --------------------------------------------------------- */

            WHEN l.cfda_number IN (
                '96.001',
                '96.002',
                '96.004'
            )
                THEN 'EXCLUDE_DUPLICATE'

            WHEN l.cfda_number IN (
                '93.778',
                '93.770',
                '93.773',
                '93.774'
            )
                THEN 'EXCLUDE_DUPLICATE'

            WHEN l.cfda_number LIKE '64.%'
                THEN 'EXCLUDE_DUPLICATE'

            /* ---------------------------------------------------------
               SSI -- resolved additive in ETL-174B-5B / ETL-176
               --------------------------------------------------------- */

            WHEN l.cfda_number = '96.006'
                THEN 'INCLUDE'

            /* ---------------------------------------------------------
               CHIP -- award-level classification controls 93.767
               --------------------------------------------------------- */

            WHEN l.cfda_number = '93.767'
                THEN COALESCE(
                    ac.accounting_disposition,
                    'UNCLASSIFIED_CHIP'
                )

            ELSE 'RESIDUAL_REVIEW'

        END AS accounting_status

    FROM analysis.v_certified_assistance_ledger l

    LEFT JOIN reference.federal_inflow_award_classification ac

      ON ac.source_system = 'USASPENDING_ASSISTANCE'
     AND ac.source_program_code = l.cfda_number
     AND ac.source_award_identifier = l.award_id_fain
     AND ac.methodology_version =
         'ANALYSIS-174B-4D-CHIP-v1'
     AND l.action_date_fiscal_year
         BETWEEN ac.valid_from_fiscal_year
             AND ac.valid_through_fiscal_year

    WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.reference_state_abbreviation = 'WA'
),

review_universe AS (

    SELECT *
    FROM classified

    WHERE accounting_status IN (
        'RESIDUAL_REVIEW',
        'WITHHOLD_UNRESOLVED'
    )
),

family_profile AS (

    SELECT
        r.*,

        CASE

            /* =========================================================
               SOCIAL BENEFITS / INCOME SUPPORT
               ========================================================= */

            WHEN r.cfda_number LIKE '10.%'
                THEN 'AGRICULTURE_AND_NUTRITION'

            WHEN r.cfda_number LIKE '57.%'
                THEN 'RAILROAD_SOCIAL_INSURANCE'

            /* =========================================================
               TRANSPORTATION
               ========================================================= */

            WHEN r.cfda_number LIKE '20.%'
                THEN 'TRANSPORTATION'

            /* =========================================================
               TREASURY / STATE-LOCAL FISCAL AID
               ========================================================= */

            WHEN r.cfda_number LIKE '21.%'
                THEN 'TREASURY_AND_STATE_LOCAL_FISCAL_AID'

            /* =========================================================
               HOUSING / COMMUNITY DEVELOPMENT
               ========================================================= */

            WHEN r.cfda_number LIKE '14.%'
                THEN 'HOUSING_AND_COMMUNITY_DEVELOPMENT'

            /* =========================================================
               LABOR / EMPLOYMENT
               ========================================================= */

            WHEN r.cfda_number LIKE '17.%'
                THEN 'LABOR_AND_EMPLOYMENT'

            /* =========================================================
               EDUCATION
               ========================================================= */

            WHEN r.cfda_number LIKE '84.%'
                THEN 'EDUCATION'

            /* =========================================================
               HEALTH AND HUMAN SERVICES

               IMPORTANT:
               This is intentionally broad. HHS residual programs need
               additional overlap review before inclusion.
               ========================================================= */

            WHEN r.cfda_number LIKE '93.%'
                THEN 'HEALTH_AND_HUMAN_SERVICES'

            /* =========================================================
               HOMELAND SECURITY / FEMA
               ========================================================= */

            WHEN r.cfda_number LIKE '97.%'
                THEN 'DISASTER_AND_HOMELAND_SECURITY'

            /* =========================================================
               SMALL BUSINESS ADMINISTRATION
               ========================================================= */

            WHEN r.cfda_number LIKE '59.%'
                THEN 'SMALL_BUSINESS'

            /* =========================================================
               COMMERCE
               ========================================================= */

            WHEN r.cfda_number LIKE '11.%'
                THEN 'COMMERCE'

            /* =========================================================
               INTERIOR
               ========================================================= */

            WHEN r.cfda_number LIKE '15.%'
                THEN 'INTERIOR_AND_NATURAL_RESOURCES'

            /* =========================================================
               JUSTICE
               ========================================================= */

            WHEN r.cfda_number LIKE '16.%'
                THEN 'JUSTICE'

            /* =========================================================
               EPA
               ========================================================= */

            WHEN r.cfda_number LIKE '66.%'
                THEN 'ENVIRONMENTAL_PROTECTION'

            /* =========================================================
               ENERGY
               ========================================================= */

            WHEN r.cfda_number LIKE '81.%'
                THEN 'ENERGY'

            /* =========================================================
               NSF
               ========================================================= */

            WHEN r.cfda_number LIKE '47.%'
                THEN 'SCIENCE_AND_RESEARCH'

            /* =========================================================
               NASA
               ========================================================= */

            WHEN r.cfda_number LIKE '43.%'
                THEN 'SCIENCE_AND_RESEARCH'

            /* =========================================================
               OTHER / NOT YET GROUPED
               ========================================================= */

            ELSE 'OTHER_UNCLASSIFIED'

        END AS analytical_family

    FROM review_universe r
),

control AS (

    SELECT
        COUNT(*) AS transaction_count,
        COALESCE(SUM(federal_action_obligation), 0)
            AS obligation_dollars,

        COALESCE(
            SUM(
                CASE
                    WHEN is_covid
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ) AS covid_obligation_dollars,

        COALESCE(
            SUM(
                CASE
                    WHEN is_iija
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ) AS iija_obligation_dollars,

        COALESCE(
            SUM(
                CASE
                    WHEN is_extraordinary
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ) AS extraordinary_obligation_dollars

    FROM family_profile
)


/* =====================================================================
   2. CONTROL
   ===================================================================== */

SELECT
    'POST_SSI_REVIEW_CONTROL' AS section,
    transaction_count,
    ROUND(obligation_dollars, 2)
        AS obligation_dollars,
    ROUND(covid_obligation_dollars, 2)
        AS covid_obligation_dollars,
    ROUND(iija_obligation_dollars, 2)
        AS iija_obligation_dollars,
    ROUND(extraordinary_obligation_dollars, 2)
        AS extraordinary_obligation_dollars,
    ROUND(
        obligation_dollars - 107679175964.03,
        2
    ) AS expected_control_difference

FROM control;


/* =====================================================================
   3. FAMILY SUMMARY
   ===================================================================== */

WITH classified AS (

    SELECT
        l.*,
        ac.accounting_disposition AS award_accounting_disposition,

        CASE
            WHEN l.cfda_number IN (
                '96.001','96.002','96.004',
                '93.778','93.770','93.773','93.774'
            )
                THEN 'EXCLUDE_DUPLICATE'

            WHEN l.cfda_number LIKE '64.%'
                THEN 'EXCLUDE_DUPLICATE'

            WHEN l.cfda_number = '96.006'
                THEN 'INCLUDE'

            WHEN l.cfda_number = '93.767'
                THEN COALESCE(
                    ac.accounting_disposition,
                    'UNCLASSIFIED_CHIP'
                )

            ELSE 'RESIDUAL_REVIEW'
        END AS accounting_status

    FROM analysis.v_certified_assistance_ledger l

    LEFT JOIN reference.federal_inflow_award_classification ac
      ON ac.source_system = 'USASPENDING_ASSISTANCE'
     AND ac.source_program_code = l.cfda_number
     AND ac.source_award_identifier = l.award_id_fain
     AND ac.methodology_version =
         'ANALYSIS-174B-4D-CHIP-v1'
     AND l.action_date_fiscal_year
         BETWEEN ac.valid_from_fiscal_year
             AND ac.valid_through_fiscal_year

    WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.reference_state_abbreviation = 'WA'
),

family_profile AS (

    SELECT
        r.*,

        CASE
            WHEN r.cfda_number LIKE '10.%'
                THEN 'AGRICULTURE_AND_NUTRITION'
            WHEN r.cfda_number LIKE '57.%'
                THEN 'RAILROAD_SOCIAL_INSURANCE'
            WHEN r.cfda_number LIKE '20.%'
                THEN 'TRANSPORTATION'
            WHEN r.cfda_number LIKE '21.%'
                THEN 'TREASURY_AND_STATE_LOCAL_FISCAL_AID'
            WHEN r.cfda_number LIKE '14.%'
                THEN 'HOUSING_AND_COMMUNITY_DEVELOPMENT'
            WHEN r.cfda_number LIKE '17.%'
                THEN 'LABOR_AND_EMPLOYMENT'
            WHEN r.cfda_number LIKE '84.%'
                THEN 'EDUCATION'
            WHEN r.cfda_number LIKE '93.%'
                THEN 'HEALTH_AND_HUMAN_SERVICES'
            WHEN r.cfda_number LIKE '97.%'
                THEN 'DISASTER_AND_HOMELAND_SECURITY'
            WHEN r.cfda_number LIKE '59.%'
                THEN 'SMALL_BUSINESS'
            WHEN r.cfda_number LIKE '11.%'
                THEN 'COMMERCE'
            WHEN r.cfda_number LIKE '15.%'
                THEN 'INTERIOR_AND_NATURAL_RESOURCES'
            WHEN r.cfda_number LIKE '16.%'
                THEN 'JUSTICE'
            WHEN r.cfda_number LIKE '66.%'
                THEN 'ENVIRONMENTAL_PROTECTION'
            WHEN r.cfda_number LIKE '81.%'
                THEN 'ENERGY'
            WHEN r.cfda_number LIKE '47.%'
                THEN 'SCIENCE_AND_RESEARCH'
            WHEN r.cfda_number LIKE '43.%'
                THEN 'SCIENCE_AND_RESEARCH'
            ELSE 'OTHER_UNCLASSIFIED'
        END AS analytical_family

    FROM classified r

    WHERE accounting_status IN (
        'RESIDUAL_REVIEW',
        'WITHHOLD_UNRESOLVED'
    )
)

SELECT
    analytical_family,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number)
        AS assistance_listing_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_obligation_dollars,

    ROUND(
        100.0 *
        SUM(federal_action_obligation)
        /
        SUM(SUM(federal_action_obligation)) OVER (),
        4
    ) AS percent_of_review_universe

FROM family_profile

GROUP BY analytical_family

ORDER BY obligation_dollars DESC;


/* =====================================================================
   4. FAMILY x FISCAL YEAR
   ===================================================================== */

WITH classified AS (

    SELECT
        l.*,
        ac.accounting_disposition,

        CASE
            WHEN l.cfda_number IN (
                '96.001','96.002','96.004',
                '93.778','93.770','93.773','93.774'
            )
                THEN 'EXCLUDE_DUPLICATE'
            WHEN l.cfda_number LIKE '64.%'
                THEN 'EXCLUDE_DUPLICATE'
            WHEN l.cfda_number = '96.006'
                THEN 'INCLUDE'
            WHEN l.cfda_number = '93.767'
                THEN COALESCE(
                    ac.accounting_disposition,
                    'UNCLASSIFIED_CHIP'
                )
            ELSE 'RESIDUAL_REVIEW'
        END AS accounting_status

    FROM analysis.v_certified_assistance_ledger l

    LEFT JOIN reference.federal_inflow_award_classification ac
      ON ac.source_system = 'USASPENDING_ASSISTANCE'
     AND ac.source_program_code = l.cfda_number
     AND ac.source_award_identifier = l.award_id_fain
     AND ac.methodology_version =
         'ANALYSIS-174B-4D-CHIP-v1'
     AND l.action_date_fiscal_year
         BETWEEN ac.valid_from_fiscal_year
             AND ac.valid_through_fiscal_year

    WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.reference_state_abbreviation = 'WA'
),

family_profile AS (

    SELECT
        r.*,

        CASE
            WHEN r.cfda_number LIKE '10.%'
                THEN 'AGRICULTURE_AND_NUTRITION'
            WHEN r.cfda_number LIKE '57.%'
                THEN 'RAILROAD_SOCIAL_INSURANCE'
            WHEN r.cfda_number LIKE '20.%'
                THEN 'TRANSPORTATION'
            WHEN r.cfda_number LIKE '21.%'
                THEN 'TREASURY_AND_STATE_LOCAL_FISCAL_AID'
            WHEN r.cfda_number LIKE '14.%'
                THEN 'HOUSING_AND_COMMUNITY_DEVELOPMENT'
            WHEN r.cfda_number LIKE '17.%'
                THEN 'LABOR_AND_EMPLOYMENT'
            WHEN r.cfda_number LIKE '84.%'
                THEN 'EDUCATION'
            WHEN r.cfda_number LIKE '93.%'
                THEN 'HEALTH_AND_HUMAN_SERVICES'
            WHEN r.cfda_number LIKE '97.%'
                THEN 'DISASTER_AND_HOMELAND_SECURITY'
            WHEN r.cfda_number LIKE '59.%'
                THEN 'SMALL_BUSINESS'
            WHEN r.cfda_number LIKE '11.%'
                THEN 'COMMERCE'
            WHEN r.cfda_number LIKE '15.%'
                THEN 'INTERIOR_AND_NATURAL_RESOURCES'
            WHEN r.cfda_number LIKE '16.%'
                THEN 'JUSTICE'
            WHEN r.cfda_number LIKE '66.%'
                THEN 'ENVIRONMENTAL_PROTECTION'
            WHEN r.cfda_number LIKE '81.%'
                THEN 'ENERGY'
            WHEN r.cfda_number LIKE '47.%'
                THEN 'SCIENCE_AND_RESEARCH'
            WHEN r.cfda_number LIKE '43.%'
                THEN 'SCIENCE_AND_RESEARCH'
            ELSE 'OTHER_UNCLASSIFIED'
        END AS analytical_family

    FROM classified r

    WHERE accounting_status IN (
        'RESIDUAL_REVIEW',
        'WITHHOLD_UNRESOLVED'
    )
)

SELECT
    action_date_fiscal_year AS fiscal_year,
    analytical_family,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_obligation_dollars

FROM family_profile

GROUP BY
    action_date_fiscal_year,
    analytical_family

ORDER BY
    action_date_fiscal_year,
    obligation_dollars DESC;


/* =====================================================================
   5. PROGRAM DETAIL -- COMPLETE REVIEW UNIVERSE
   ===================================================================== */

WITH classified AS (

    SELECT
        l.*,
        ac.accounting_disposition,

        CASE
            WHEN l.cfda_number IN (
                '96.001','96.002','96.004',
                '93.778','93.770','93.773','93.774'
            )
                THEN 'EXCLUDE_DUPLICATE'
            WHEN l.cfda_number LIKE '64.%'
                THEN 'EXCLUDE_DUPLICATE'
            WHEN l.cfda_number = '96.006'
                THEN 'INCLUDE'
            WHEN l.cfda_number = '93.767'
                THEN COALESCE(
                    ac.accounting_disposition,
                    'UNCLASSIFIED_CHIP'
                )
            ELSE 'RESIDUAL_REVIEW'
        END AS accounting_status

    FROM analysis.v_certified_assistance_ledger l

    LEFT JOIN reference.federal_inflow_award_classification ac
      ON ac.source_system = 'USASPENDING_ASSISTANCE'
     AND ac.source_program_code = l.cfda_number
     AND ac.source_award_identifier = l.award_id_fain
     AND ac.methodology_version =
         'ANALYSIS-174B-4D-CHIP-v1'
     AND l.action_date_fiscal_year
         BETWEEN ac.valid_from_fiscal_year
             AND ac.valid_through_fiscal_year

    WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.reference_state_abbreviation = 'WA'
),

family_profile AS (

    SELECT
        r.*,

        CASE
            WHEN r.cfda_number LIKE '10.%'
                THEN 'AGRICULTURE_AND_NUTRITION'
            WHEN r.cfda_number LIKE '57.%'
                THEN 'RAILROAD_SOCIAL_INSURANCE'
            WHEN r.cfda_number LIKE '20.%'
                THEN 'TRANSPORTATION'
            WHEN r.cfda_number LIKE '21.%'
                THEN 'TREASURY_AND_STATE_LOCAL_FISCAL_AID'
            WHEN r.cfda_number LIKE '14.%'
                THEN 'HOUSING_AND_COMMUNITY_DEVELOPMENT'
            WHEN r.cfda_number LIKE '17.%'
                THEN 'LABOR_AND_EMPLOYMENT'
            WHEN r.cfda_number LIKE '84.%'
                THEN 'EDUCATION'
            WHEN r.cfda_number LIKE '93.%'
                THEN 'HEALTH_AND_HUMAN_SERVICES'
            WHEN r.cfda_number LIKE '97.%'
                THEN 'DISASTER_AND_HOMELAND_SECURITY'
            WHEN r.cfda_number LIKE '59.%'
                THEN 'SMALL_BUSINESS'
            WHEN r.cfda_number LIKE '11.%'
                THEN 'COMMERCE'
            WHEN r.cfda_number LIKE '15.%'
                THEN 'INTERIOR_AND_NATURAL_RESOURCES'
            WHEN r.cfda_number LIKE '16.%'
                THEN 'JUSTICE'
            WHEN r.cfda_number LIKE '66.%'
                THEN 'ENVIRONMENTAL_PROTECTION'
            WHEN r.cfda_number LIKE '81.%'
                THEN 'ENERGY'
            WHEN r.cfda_number LIKE '47.%'
                THEN 'SCIENCE_AND_RESEARCH'
            WHEN r.cfda_number LIKE '43.%'
                THEN 'SCIENCE_AND_RESEARCH'
            ELSE 'OTHER_UNCLASSIFIED'
        END AS analytical_family

    FROM classified r

    WHERE accounting_status IN (
        'RESIDUAL_REVIEW',
        'WITHHOLD_UNRESOLVED'
    )
)

SELECT
    analytical_family,
    cfda_number,
    MIN(cfda_title) AS cfda_title,
    MIN(funding_agency_name) AS funding_agency_name,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_obligation_dollars,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year

FROM family_profile

GROUP BY
    analytical_family,
    cfda_number

ORDER BY
    obligation_dollars DESC;


/* =====================================================================
   6. BRIDGE CERTIFICATION
   ===================================================================== */

WITH classified AS (

    SELECT
        l.*,
        ac.accounting_disposition,

        CASE
            WHEN l.cfda_number IN (
                '96.001','96.002','96.004',
                '93.778','93.770','93.773','93.774'
            )
                THEN 'EXCLUDE_DUPLICATE'
            WHEN l.cfda_number LIKE '64.%'
                THEN 'EXCLUDE_DUPLICATE'
            WHEN l.cfda_number = '96.006'
                THEN 'INCLUDE'
            WHEN l.cfda_number = '93.767'
                THEN COALESCE(
                    ac.accounting_disposition,
                    'UNCLASSIFIED_CHIP'
                )
            ELSE 'RESIDUAL_REVIEW'
        END AS accounting_status

    FROM analysis.v_certified_assistance_ledger l

    LEFT JOIN reference.federal_inflow_award_classification ac
      ON ac.source_system = 'USASPENDING_ASSISTANCE'
     AND ac.source_program_code = l.cfda_number
     AND ac.source_award_identifier = l.award_id_fain
     AND ac.methodology_version =
         'ANALYSIS-174B-4D-CHIP-v1'
     AND l.action_date_fiscal_year
         BETWEEN ac.valid_from_fiscal_year
             AND ac.valid_through_fiscal_year

    WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.reference_state_abbreviation = 'WA'
)

SELECT
    accounting_status,
    COUNT(*) AS transaction_count,
    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars

FROM classified

GROUP BY accounting_status

ORDER BY accounting_status;