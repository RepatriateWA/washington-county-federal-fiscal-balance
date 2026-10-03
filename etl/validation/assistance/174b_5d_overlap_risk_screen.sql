/* =====================================================================
   ETL-174B-5D
   WASHINGTON FEDERAL INFLOWS
   RESIDUAL ASSISTANCE OVERLAP-RISK SCREEN

   READ ONLY -- NO DATABASE WRITES

   Purpose:
     Partition the post-overlap, post-SSI USAspending assistance
     universe into accounting-review lanes.

   This stage DOES NOT authorize ledger inclusion.

   Review lanes:

     KNOWN_SPECIAL_REVIEW
       Program has a specifically identified potential relationship
       with another WCFFBP accounting stream.

     HEALTH_OVERLAP_REVIEW
       Residual HHS program requires examination against CMS-native
       Medicare / Medicaid / CHIP accounting.

     ADDITIVE_CANDIDATE
       No currently identified authoritative WCFFBP duplicate in the
       present accounting architecture. This is NOT equivalent to
       INCLUDE.

     WITHHOLD_UNRESOLVED
       Existing explicit unresolved award-level exception.

   Governing rule:
     No double-counting. Appearance in a different federal dataset
     does not by itself make a dollar additive.

   Expected review control:
     $107,679,175,964.03
   ===================================================================== */

\pset pager off


/* =====================================================================
   COMMON ACCOUNTING CLASSIFICATION
   ===================================================================== */

CREATE TEMP VIEW etl174b5d_universe AS

WITH base AS (

    SELECT
        l.*,
        ac.accounting_disposition
            AS award_accounting_disposition

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

accounted AS (

    SELECT
        b.*,

        CASE

            WHEN b.cfda_number IN (
                '96.001',
                '96.002',
                '96.004'
            )
                THEN 'EXCLUDE_DUPLICATE'

            WHEN b.cfda_number IN (
                '93.778',
                '93.770',
                '93.773',
                '93.774'
            )
                THEN 'EXCLUDE_DUPLICATE'

            WHEN b.cfda_number LIKE '64.%'
                THEN 'EXCLUDE_DUPLICATE'

            WHEN b.cfda_number = '96.006'
                THEN 'INCLUDE'

            WHEN b.cfda_number = '93.767'
                THEN COALESCE(
                    b.award_accounting_disposition,
                    'UNCLASSIFIED_CHIP'
                )

            ELSE 'RESIDUAL_REVIEW'

        END AS existing_accounting_status

    FROM base b
),

review AS (

    SELECT *
    FROM accounted

    WHERE existing_accounting_status IN (
        'RESIDUAL_REVIEW',
        'WITHHOLD_UNRESOLVED'
    )
)

SELECT
    r.*,

    CASE

        /* -------------------------------------------------------------
           Explicit unresolved CHIP award
           ------------------------------------------------------------- */

        WHEN r.existing_accounting_status =
             'WITHHOLD_UNRESOLVED'
            THEN 'WITHHOLD_UNRESOLVED'


        /* -------------------------------------------------------------
           Railroad Retirement

           Assistance Listing 57.001 is a direct social-insurance
           benefit stream. It requires affirmative review against
           WCFFBP's other federal benefit accounting before inclusion.
           ------------------------------------------------------------- */

        WHEN r.cfda_number = '57.001'
            THEN 'KNOWN_SPECIAL_REVIEW'


        /* -------------------------------------------------------------
           Unemployment Insurance

           17.225 is an expenditure/inflow program, distinct in concept
           from the tax-side UI receipts allocator, but it should be
           affirmatively checked for any separate WCFFBP expenditure
           control before inclusion.
           ------------------------------------------------------------- */

        WHEN r.cfda_number = '17.225'
            THEN 'KNOWN_SPECIAL_REVIEW'


        /* -------------------------------------------------------------
           HHS residual

           Do not assume all 93.* programs overlap CMS.

           Most plainly do not. NIH research, TANF, Head Start, child
           care, etc. are economically distinct programs.

           But because CMS-native Medicare/Medicaid/CHIP controls are
           already authoritative ledger streams, residual 93.* receives
           a dedicated screen before release.
           ------------------------------------------------------------- */

        WHEN r.cfda_number LIKE '93.%'
            THEN 'HEALTH_OVERLAP_REVIEW'


        /* -------------------------------------------------------------
           Everything else

           No currently identified collision with an authoritative
           WCFFBP inflow stream.

           IMPORTANT:
           ADDITIVE_CANDIDATE is a review status, NOT a ledger treatment.
           ------------------------------------------------------------- */

        ELSE 'ADDITIVE_CANDIDATE'

    END AS review_lane,

    CASE

        WHEN r.existing_accounting_status =
             'WITHHOLD_UNRESOLVED'
            THEN
            'Existing award-level unresolved accounting exception'

        WHEN r.cfda_number = '57.001'
            THEN
            'Railroad social-insurance benefit stream requires source-overlap review'

        WHEN r.cfda_number = '17.225'
            THEN
            'Unemployment Insurance benefit/administrative stream requires expenditure-source review'

        WHEN r.cfda_number LIKE '93.%'
            THEN
            'Residual HHS program requires CMS Medicare/Medicaid/CHIP overlap screen'

        ELSE
            'No currently identified authoritative WCFFBP duplicate; candidate for subsequent additive certification'

    END AS review_basis

FROM review r;


/* =====================================================================
   1. EXACT CONTROL
   ===================================================================== */

SELECT
    'ETL-174B-5D CONTROL' AS section,

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

    ROUND(
        SUM(federal_action_obligation)
        - 107679175964.03,
        2
    ) AS expected_control_difference

FROM etl174b5d_universe;


/* =====================================================================
   2. REVIEW-LANE SUMMARY
   ===================================================================== */

SELECT
    review_lane,

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
        100.0
        * SUM(federal_action_obligation)
        / SUM(SUM(federal_action_obligation)) OVER (),
        4
    ) AS percent_of_review_universe

FROM etl174b5d_universe

GROUP BY review_lane

ORDER BY obligation_dollars DESC;


/* =====================================================================
   3. REVIEW LANES BY FISCAL YEAR
   ===================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,
    review_lane,

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

FROM etl174b5d_universe

GROUP BY
    action_date_fiscal_year,
    review_lane

ORDER BY
    action_date_fiscal_year,
    obligation_dollars DESC;


/* =====================================================================
   4. COMPLETE NON-CANDIDATE REVIEW QUEUE

   This is the principal output for our next decision.
   ===================================================================== */

SELECT
    review_lane,
    cfda_number,
    MIN(cfda_title) AS cfda_title,
    MIN(funding_agency_name)
        AS funding_agency_name,

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
        AS last_fiscal_year,

    MIN(review_basis)
        AS review_basis

FROM etl174b5d_universe

WHERE review_lane <> 'ADDITIVE_CANDIDATE'

GROUP BY
    review_lane,
    cfda_number

ORDER BY
    obligation_dollars DESC;


/* =====================================================================
   5. TOP ADDITIVE CANDIDATES

   Descriptive only. No inclusion decision is made here.
   ===================================================================== */

SELECT
    cfda_number,
    MIN(cfda_title) AS cfda_title,
    MIN(funding_agency_name)
        AS funding_agency_name,

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

FROM etl174b5d_universe

WHERE review_lane = 'ADDITIVE_CANDIDATE'

GROUP BY cfda_number

ORDER BY obligation_dollars DESC

LIMIT 150;


/* =====================================================================
   6. HHS REVIEW QUEUE -- COMPLETE
   ===================================================================== */

SELECT
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

    COUNT(DISTINCT award_id_uri)
        AS distinct_uri_count,

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

    MIN(canonical_award_description)
        AS sample_award_description

FROM etl174b5d_universe

WHERE review_lane = 'HEALTH_OVERLAP_REVIEW'

GROUP BY cfda_number

ORDER BY obligation_dollars DESC;


/* =====================================================================
   7. FINAL BRIDGE
   ===================================================================== */

SELECT
    review_lane,

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

FROM etl174b5d_universe

GROUP BY review_lane

UNION ALL

SELECT
    'TOTAL',

    COUNT(*),

    ROUND(
        SUM(federal_action_obligation),
        2
    ),

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    )

FROM etl174b5d_universe

ORDER BY review_lane;


/* =====================================================================
   8. CLEANUP
   ===================================================================== */

DROP VIEW etl174b5d_universe;