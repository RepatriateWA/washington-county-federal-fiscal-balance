/*
===============================================================================
ETL-174B-5F
HHS SENSITIVE OVERLAP ADJUDICATION PROFILE
===============================================================================

PURPOSE
-------
Perform a read-only evidentiary examination of the sensitive HHS subset
identified by ETL-174B-5E.

ETL-174B-5E established:

    HHS review universe                  $21,975,789,147.43
    Distinct-program candidate          $21,470,385,036.66

    Sensitive review lanes:
      CMS_DIRECT_REVIEW                    $400,231,129.31
      MEDICAID_RELATED_REVIEW               $69,918,674.09
      MEDICARE_RELATED_REVIEW               $35,254,307.37
                                         -----------------
      Sensitive HHS total                  $505,404,110.77

This stage is READ ONLY.

NO accounting disposition is persisted here.

GOVERNING PRINCIPLE
-------------------
No double-counting.

However:

    "related to Medicare/Medicaid"
        is NOT equivalent to
    "already contained in Medicare/Medicaid benefit expenditures."

The purpose of this stage is therefore to distinguish:

    BENEFIT_PAYMENT_COLLISION_RISK
        Plausible direct collision with an authoritative CMS benefit /
        medical expenditure stream.

    DISTINCT_GRANT_OR_ADMIN_CANDIDATE
        Separate grant, demonstration, administration, research,
        enforcement, outreach, infrastructure, or program-development
        expenditure that appears economically distinct from benefit payments.

    MANUAL_REVIEW
        Evidence is insufficient for either conclusion.

These are analytical review classes, NOT final ledger dispositions.

COVID / IIJA / extraordinary status remains independent.
===============================================================================
*/

\pset pager off


/* ============================================================================
   1. RECONSTRUCT THE ETL-174B-5E HHS UNIVERSE
   ========================================================================== */

CREATE OR REPLACE TEMP VIEW etl_174b_5f_hhs AS

WITH base AS (

    SELECT
        l.*,
        ac.accounting_disposition AS award_accounting_disposition

    FROM analysis.v_certified_assistance_ledger AS l

    LEFT JOIN reference.federal_inflow_award_classification AS ac
      ON ac.source_system = 'USASPENDING_ASSISTANCE'
     AND ac.source_program_code = l.cfda_number
     AND ac.source_award_identifier = l.award_id_fain
     AND l.action_date_fiscal_year
            BETWEEN ac.valid_from_fiscal_year
                AND ac.valid_through_fiscal_year

    WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.reference_state_abbreviation = 'WA'
),

post_overlap AS (

    SELECT *
    FROM base

    WHERE cfda_number NOT IN (
        '96.001',
        '96.002',
        '96.004',
        '93.778',
        '93.770',
        '93.773',
        '93.774'
    )

      AND COALESCE(cfda_number, '') NOT LIKE '64.%'

      AND NOT (
          cfda_number = '93.767'
          AND award_accounting_disposition = 'EXCLUDE_DUPLICATE'
      )
),

post_ssi AS (

    SELECT *
    FROM post_overlap
    WHERE cfda_number <> '96.006'
),

hhs AS (

    SELECT *
    FROM post_ssi

    WHERE cfda_number LIKE '93.%'

      AND COALESCE(
            award_accounting_disposition,
            ''
          ) <> 'WITHHOLD_UNRESOLVED'
)

SELECT *
FROM hhs;


/* ============================================================================
   2. FAIL-CLOSED HHS CONTROL

   Must reproduce ETL-174B-5E exactly.
   ========================================================================== */

SELECT
    'ETL-174B-5F HHS CONTROL' AS section,

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
        SUM(federal_action_obligation)
        - 21975789147.43,
        2
    ) AS expected_hhs_difference

FROM etl_174b_5f_hhs;


/* ============================================================================
   3. RECONSTRUCT 5E REVIEW LANES
   ========================================================================== */

CREATE OR REPLACE TEMP VIEW etl_174b_5f_triage AS

SELECT
    h.*,

    CASE

        WHEN
            UPPER(COALESCE(awarding_subagency_name, ''))
                LIKE '%CENTERS FOR MEDICARE%'
            OR
            UPPER(COALESCE(funding_subagency_name, ''))
                LIKE '%CENTERS FOR MEDICARE%'
            OR
            UPPER(COALESCE(awarding_subagency_name, ''))
                LIKE '%CENTER FOR MEDICARE%'
            OR
            UPPER(COALESCE(funding_subagency_name, ''))
                LIKE '%CENTER FOR MEDICARE%'
        THEN 'CMS_DIRECT_REVIEW'

        WHEN
            UPPER(COALESCE(cfda_title, ''))
                LIKE '%MEDICAID%'
            OR
            UPPER(COALESCE(canonical_award_description, ''))
                LIKE '%MEDICAID%'
            OR
            UPPER(COALESCE(transaction_description, ''))
                LIKE '%MEDICAID%'
        THEN 'MEDICAID_RELATED_REVIEW'

        WHEN
            UPPER(COALESCE(cfda_title, ''))
                LIKE '%MEDICARE%'
            OR
            UPPER(COALESCE(canonical_award_description, ''))
                LIKE '%MEDICARE%'
            OR
            UPPER(COALESCE(transaction_description, ''))
                LIKE '%MEDICARE%'
        THEN 'MEDICARE_RELATED_REVIEW'

        ELSE 'HEALTH_PROGRAM_DISTINCT_CANDIDATE'

    END AS hhs_review_lane

FROM etl_174b_5f_hhs AS h;


/* ============================================================================
   4. SENSITIVE SUBSET
   ========================================================================== */

CREATE OR REPLACE TEMP VIEW etl_174b_5f_sensitive AS

SELECT *
FROM etl_174b_5f_triage

WHERE hhs_review_lane IN (
    'CMS_DIRECT_REVIEW',
    'MEDICAID_RELATED_REVIEW',
    'MEDICARE_RELATED_REVIEW'
);


/* ============================================================================
   5. FAIL-CLOSED SENSITIVE CONTROL

   Expected:
       $505,404,110.77
   ========================================================================== */

SELECT
    'ETL-174B-5F SENSITIVE CONTROL' AS section,

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
        SUM(federal_action_obligation)
        - 505404110.77,
        2
    ) AS expected_sensitive_difference

FROM etl_174b_5f_sensitive;


/* ============================================================================
   6. PROGRAM-LEVEL SENSITIVE INVENTORY

   Complete, not top-N.
   ========================================================================== */

SELECT
    hhs_review_lane,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    MIN(funding_agency_name)
        AS funding_agency_name,

    MIN(funding_subagency_name)
        AS funding_subagency_name,

    MIN(awarding_subagency_name)
        AS awarding_subagency_name,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

    COUNT(DISTINCT award_id_uri)
        AS distinct_uri_count,

    COUNT(DISTINCT recipient_name)
        AS distinct_recipient_count,

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

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year,

    MIN(canonical_award_description)
        AS sample_award_description,

    MIN(transaction_description)
        AS sample_transaction_description

FROM etl_174b_5f_sensitive

GROUP BY
    hhs_review_lane,
    cfda_number

ORDER BY
    obligation_dollars DESC;


/* ============================================================================
   7. ASSISTANCE-TYPE PROFILE

   Direct benefit payments should look structurally different from many
   project grants / cooperative agreements / administrative awards.
   ========================================================================== */

SELECT
    hhs_review_lane,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    assistance_type_code,
    assistance_type_description,

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

FROM etl_174b_5f_sensitive

GROUP BY
    hhs_review_lane,
    cfda_number,
    assistance_type_code,
    assistance_type_description

ORDER BY
    cfda_number,
    obligation_dollars DESC;


/* ============================================================================
   8. RECIPIENT PROFILE

   Benefit-payment streams often have materially different recipient
   structures from grants to states, universities, nonprofits, etc.
   ========================================================================== */

SELECT
    hhs_review_lane,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    recipient_name,
    recipient_type_code,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year

FROM etl_174b_5f_sensitive

GROUP BY
    hhs_review_lane,
    cfda_number,
    recipient_name,
    recipient_type_code

ORDER BY
    cfda_number,
    obligation_dollars DESC;


/* ============================================================================
   9. TEXTUAL PAYMENT-COLLISION SCREEN

   This is intentionally conservative.

   A textual hit does NOT establish duplicate accounting.
   It merely identifies records deserving closer inspection.
   ========================================================================== */

SELECT
    hhs_review_lane,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN
                    UPPER(
                        COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%BENEFIT PAYMENT%'

                 OR UPPER(
                        COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%MEDICAL ASSISTANCE PAYMENT%'

                 OR UPPER(
                        COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%CLAIM PAYMENT%'

                 OR UPPER(
                        COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%ENTITLEMENT%'
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS payment_collision_text_dollars

FROM etl_174b_5f_sensitive

GROUP BY
    hhs_review_lane,
    cfda_number

ORDER BY
    payment_collision_text_dollars DESC,
    obligation_dollars DESC;


/* ============================================================================
   10. DISTINCT-GRANT / ADMINISTRATIVE EVIDENCE SCREEN

   Again, this is evidentiary rather than dispositive.
   ========================================================================== */

SELECT
    hhs_review_lane,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN
                    UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%GRANT%'

                 OR UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%DEMONSTRATION%'

                 OR UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%RESEARCH%'

                 OR UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%SURVEY%'

                 OR UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%CERTIFICATION%'

                 OR UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%FRAUD CONTROL%'

                 OR UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%OUTREACH%'

                 OR UPPER(
                        COALESCE(cfda_title, '')
                        || ' '
                        || COALESCE(canonical_award_description, '')
                        || ' '
                        || COALESCE(transaction_description, '')
                    ) LIKE '%IMPLEMENTATION%'

                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS distinct_program_text_dollars

FROM etl_174b_5f_sensitive

GROUP BY
    hhs_review_lane,
    cfda_number

ORDER BY
    distinct_program_text_dollars DESC,
    obligation_dollars DESC;


/* ============================================================================
   11. PROGRAM / FISCAL-YEAR PROFILE
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,
    hhs_review_lane,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

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

FROM etl_174b_5f_sensitive

GROUP BY
    action_date_fiscal_year,
    hhs_review_lane,
    cfda_number

ORDER BY
    fiscal_year,
    obligation_dollars DESC;


/* ============================================================================
   12. EXISTING SOURCE-POLICY EVIDENCE

   We explicitly inspect durable policy before making any new decision.
   ========================================================================== */

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    source_selection_basis

FROM reference.federal_inflow_source_policy

WHERE inflow_family IN (
    'MEDICARE',
    'MEDICAID',
    'CHIP',
    'HEALTH'
)

ORDER BY
    inflow_family,
    inflow_subfamily,
    methodology_version;


/* ============================================================================
   13. EXISTING PROGRAM-CLASSIFICATION EVIDENCE

   Only programs actually present in the sensitive universe.
   ========================================================================== */

SELECT
    pc.source_system,
    pc.source_program_code,
    pc.source_program_title,
    pc.inflow_family,
    pc.inflow_subfamily,
    pc.overlap_risk,
    pc.covid_relevance,
    pc.extraordinary_relevance,
    pc.classification_basis,
    pc.methodology_version,
    pc.valid_from_fiscal_year,
    pc.valid_through_fiscal_year

FROM reference.federal_inflow_program_classification AS pc

WHERE pc.source_system = 'USASPENDING_ASSISTANCE'

  AND pc.source_program_code IN (
      SELECT DISTINCT cfda_number
      FROM etl_174b_5f_sensitive
  )

ORDER BY
    pc.source_program_code,
    pc.methodology_version;


/* ============================================================================
   14. FINAL CONTROL BRIDGE
   ========================================================================== */

SELECT
    hhs_review_lane,

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
    ) AS covid_obligation_dollars

FROM etl_174b_5f_sensitive

GROUP BY hhs_review_lane

UNION ALL

SELECT
    'TOTAL',

    COUNT(*),

    COUNT(DISTINCT cfda_number),

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

FROM etl_174b_5f_sensitive

ORDER BY hhs_review_lane;


/* ============================================================================
   CLEANUP
   ========================================================================== */

DROP VIEW etl_174b_5f_sensitive;
DROP VIEW etl_174b_5f_triage;
DROP VIEW etl_174b_5f_hhs;