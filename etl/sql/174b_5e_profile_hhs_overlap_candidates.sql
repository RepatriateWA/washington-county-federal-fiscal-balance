/*
===============================================================================
ETL-174B-5E
HHS RESIDUAL OVERLAP TRIAGE
===============================================================================

PURPOSE
-------
Profile the HHS portion of the post-overlap, post-SSI USAspending assistance
review universe and isolate programs that require substantive Medicare /
Medicaid / CHIP overlap reconciliation.

This stage is READ ONLY.

It does NOT:
  * declare residual HHS programs additive;
  * declare residual HHS programs duplicates;
  * change any source policy;
  * change any award classification;
  * write to the database.

GOVERNING RULE
--------------
No double-counting.

A program is not excluded merely because:
  * it is funded by HHS;
  * its Assistance Listing begins with 93.;
  * it mentions health, Medicare, Medicaid, CHIP, CMS, or ACA.

Likewise, a program is not included merely because it survived the earlier
overlap rules.

COVID / IIJA / extraordinary classifications remain independent funding
characteristics and are preserved throughout this analysis.

EXPECTED POST-SSI CONTROL
-------------------------
Obligations: $107,679,175,964.03

Expected ETL-174B-5D HHS review lane:
Obligations: $21,975,789,147.43

METHODOLOGY
-----------
1. Reconstruct the ETL-174B post-overlap universe.
2. Remove SSI 96.006, now independently included under
   ANALYSIS-174B-5B-SSI-v1.
3. Restrict to residual HHS Assistance Listings (93.*).
4. Apply a conservative analytical triage:
     A. CMS_DIRECT_REVIEW
     B. MEDICAID_RELATED_REVIEW
     C. MEDICARE_RELATED_REVIEW
     D. CHIP_RELATED_REVIEW
     E. HEALTH_PROGRAM_DISTINCT_CANDIDATE
5. Produce exact accounting bridges and program-level evidence.

The triage labels are analytical only. They are NOT ledger dispositions.
===============================================================================
*/

\pset pager off


/* ============================================================================
   SECTION 1
   Reconstruct post-overlap / post-SSI review universe.
   ========================================================================== */

CREATE OR REPLACE TEMP VIEW etl_174b_5e_residual AS
WITH base AS (
    SELECT
        l.*,

        /*
        Award-level exception handling currently applies to 93.767 CHIP.
        */
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
),

post_overlap AS (
    SELECT *
    FROM base
    WHERE
        /*
        OASDI duplicate of authoritative SSA benefit-payment ledger.
        */
        cfda_number NOT IN ('96.001', '96.002', '96.004')

        /*
        CMS-native Medicaid / Medicare controls already represented.
        */
        AND cfda_number NOT IN (
            '93.778',
            '93.770',
            '93.773',
            '93.774'
        )

        /*
        VA GDX authoritative control.
        */
        AND COALESCE(cfda_number, '') NOT LIKE '64.%'

        /*
        CHIP requires award-level treatment.
        Core T21 awards are duplicate; Healthy Kids Together remains.
        */
        AND NOT (
            cfda_number = '93.767'
            AND award_accounting_disposition = 'EXCLUDE_DUPLICATE'
        )
),

post_ssi AS (
    SELECT *
    FROM post_overlap
    WHERE cfda_number <> '96.006'
)

SELECT *
FROM post_ssi;


/* ============================================================================
   SECTION 2
   Fail-closed control.
   ========================================================================== */

SELECT
    'ETL-174B-5E POST-SSI CONTROL' AS section,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS assistance_listing_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
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
FROM etl_174b_5e_residual;


/* ============================================================================
   SECTION 3
   Construct HHS analytical triage.

   IMPORTANT:
   These are REVIEW LANES, not accounting dispositions.

   Priority is intentional:
       direct CMS relationship
       Medicaid relationship
       Medicare relationship
       CHIP relationship
       otherwise distinct-program candidate
   ========================================================================== */

CREATE OR REPLACE TEMP VIEW etl_174b_5e_hhs_triage AS
WITH hhs AS (
    SELECT *
    FROM etl_174b_5e_residual
    WHERE cfda_number LIKE '93.%'
      AND COALESCE(
            award_accounting_disposition,
            ''
          ) <> 'WITHHOLD_UNRESOLVED'
),

classified AS (
    SELECT
        h.*,

        CASE

            /*
            ---------------------------------------------------------------
            Direct CMS / CMS-administered review candidates.

            This is deliberately conservative. We use agency/subagency and
            textual evidence to identify programs needing a closer look,
            rather than assuming every HHS program overlaps CMS controls.
            ---------------------------------------------------------------
            */
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


            /*
            ---------------------------------------------------------------
            Medicaid-related residual programs.
            ---------------------------------------------------------------
            */
            WHEN
                UPPER(COALESCE(cfda_title, '')) LIKE '%MEDICAID%'
                OR
                UPPER(COALESCE(canonical_award_description, ''))
                    LIKE '%MEDICAID%'
                OR
                UPPER(COALESCE(transaction_description, ''))
                    LIKE '%MEDICAID%'
            THEN 'MEDICAID_RELATED_REVIEW'


            /*
            ---------------------------------------------------------------
            Medicare-related residual programs.
            ---------------------------------------------------------------
            */
            WHEN
                UPPER(COALESCE(cfda_title, '')) LIKE '%MEDICARE%'
                OR
                UPPER(COALESCE(canonical_award_description, ''))
                    LIKE '%MEDICARE%'
                OR
                UPPER(COALESCE(transaction_description, ''))
                    LIKE '%MEDICARE%'
            THEN 'MEDICARE_RELATED_REVIEW'


            /*
            ---------------------------------------------------------------
            CHIP-related residual programs.
            ---------------------------------------------------------------
            */
            WHEN
                UPPER(COALESCE(cfda_title, ''))
                    LIKE '%CHILDREN''S HEALTH INSURANCE%'
                OR
                UPPER(COALESCE(cfda_title, ''))
                    LIKE '%CHILD HEALTH INSURANCE%'
                OR
                UPPER(COALESCE(canonical_award_description, ''))
                    LIKE '%CHILDREN''S HEALTH INSURANCE%'
                OR
                UPPER(COALESCE(transaction_description, ''))
                    LIKE '%CHILDREN''S HEALTH INSURANCE%'
                OR
                UPPER(COALESCE(canonical_award_description, ''))
                    LIKE '%HEALTHY KIDS%'
                OR
                UPPER(COALESCE(transaction_description, ''))
                    LIKE '%HEALTHY KIDS%'
            THEN 'CHIP_RELATED_REVIEW'


            ELSE 'HEALTH_PROGRAM_DISTINCT_CANDIDATE'

        END AS hhs_review_lane

    FROM hhs AS h
)

SELECT *
FROM classified;


/* ============================================================================
   SECTION 4
   HHS control.
   ========================================================================== */

SELECT
    'ETL-174B-5E HHS CONTROL' AS section,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS assistance_listing_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_obligation_dollars,
    ROUND(
        SUM(federal_action_obligation)
        - 21975789147.43,
        2
    ) AS expected_5d_hhs_difference
FROM etl_174b_5e_hhs_triage;


/* ============================================================================
   SECTION 5
   Triage-lane totals.
   ========================================================================== */

SELECT
    hhs_review_lane,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS assistance_listing_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_obligation_dollars,

    ROUND(
        100.0 * SUM(federal_action_obligation)
        / NULLIF(
            SUM(SUM(federal_action_obligation)) OVER (),
            0
        ),
        4
    ) AS percent_of_hhs_review

FROM etl_174b_5e_hhs_triage
GROUP BY hhs_review_lane
ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 6
   Annual triage bridge.
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,
    hhs_review_lane,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS assistance_listing_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_obligation_dollars

FROM etl_174b_5e_hhs_triage
GROUP BY
    action_date_fiscal_year,
    hhs_review_lane
ORDER BY
    action_date_fiscal_year,
    obligation_dollars DESC;


/* ============================================================================
   SECTION 7
   COMPLETE program inventory for all non-distinct lanes.

   This should be small enough to inspect program by program.
   ========================================================================== */

SELECT
    hhs_review_lane,
    cfda_number,
    cfda_title,
    funding_agency_name,
    funding_subagency_name,
    awarding_subagency_name,

    COUNT(*) AS transaction_count,
    COUNT(DISTINCT award_id_fain) AS distinct_fain_count,
    COUNT(DISTINCT award_id_uri) AS distinct_uri_count,

    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_obligation_dollars,

    MIN(action_date_fiscal_year) AS first_fiscal_year,
    MAX(action_date_fiscal_year) AS last_fiscal_year,

    MIN(canonical_award_description)
        AS sample_award_description,

    MIN(transaction_description)
        AS sample_transaction_description

FROM etl_174b_5e_hhs_triage

WHERE hhs_review_lane <> 'HEALTH_PROGRAM_DISTINCT_CANDIDATE'

GROUP BY
    hhs_review_lane,
    cfda_number,
    cfda_title,
    funding_agency_name,
    funding_subagency_name,
    awarding_subagency_name

ORDER BY
    hhs_review_lane,
    obligation_dollars DESC,
    cfda_number;


/* ============================================================================
   SECTION 8
   Largest programs currently classified as distinct-program candidates.

   This is a reasonableness screen. It does NOT certify inclusion.
   ========================================================================== */

WITH program_totals AS (
    SELECT
        cfda_number,
        cfda_title,
        funding_agency_name,

        COUNT(*) AS transaction_count,

        ROUND(
            SUM(federal_action_obligation),
            2
        ) AS obligation_dollars,

        ROUND(
            SUM(
                CASE WHEN is_covid
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            2
        ) AS covid_obligation_dollars,

        ROUND(
            SUM(
                CASE WHEN is_iija
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            2
        ) AS iija_obligation_dollars,

        MIN(action_date_fiscal_year) AS first_fiscal_year,
        MAX(action_date_fiscal_year) AS last_fiscal_year,

        MIN(canonical_award_description)
            AS sample_award_description

    FROM etl_174b_5e_hhs_triage

    WHERE hhs_review_lane =
          'HEALTH_PROGRAM_DISTINCT_CANDIDATE'

    GROUP BY
        cfda_number,
        cfda_title,
        funding_agency_name
)

SELECT *
FROM program_totals
ORDER BY obligation_dollars DESC
LIMIT 100;


/* ============================================================================
   SECTION 9
   Explicit known-sensitive Assistance Listings.

   These were identified during ETL-174B-5D as deserving particular scrutiny.
   Their presence here is diagnostic only.
   ========================================================================== */

SELECT
    cfda_number,
    cfda_title,
    hhs_review_lane,

    COUNT(*) AS transaction_count,
    COUNT(DISTINCT award_id_fain) AS distinct_fain_count,
    COUNT(DISTINCT award_id_uri) AS distinct_uri_count,

    ROUND(SUM(federal_action_obligation), 2)
        AS obligation_dollars,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars,

    MIN(canonical_award_description)
        AS sample_award_description,

    MIN(transaction_description)
        AS sample_transaction_description

FROM etl_174b_5e_hhs_triage

WHERE cfda_number IN (
    '93.791',    -- Money Follows the Person
    '93.796',    -- Medicaid survey/certification
    '93.777',    -- Medicare survey/certification
    '93.775',    -- Medicaid Fraud Control Units
    '93.767'     -- remaining CHIP exception
)

GROUP BY
    cfda_number,
    cfda_title,
    hhs_review_lane

ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 10
   Existing durable policy / classification evidence touching residual HHS.

   This prevents us from overlooking policy decisions already stored in the DB.
   ========================================================================== */

SELECT
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.source_selection_basis

FROM reference.federal_inflow_source_policy AS p

WHERE
    p.inflow_family IN (
        'MEDICARE',
        'MEDICAID',
        'CHIP',
        'HEALTH'
    )
    OR EXISTS (
        SELECT 1
        FROM unnest(COALESCE(p.overlapping_sources, ARRAY[]::text[]))
             AS s(source_name)
        WHERE source_name ILIKE '%93.%'
           OR source_name ILIKE '%MEDICARE%'
           OR source_name ILIKE '%MEDICAID%'
           OR source_name ILIKE '%CHIP%'
    )

ORDER BY
    p.inflow_family,
    p.inflow_subfamily,
    p.methodology_version;


/* ============================================================================
   SECTION 11
   Final arithmetic bridge.
   ========================================================================== */

WITH totals AS (
    SELECT
        hhs_review_lane,
        SUM(federal_action_obligation) AS amount
    FROM etl_174b_5e_hhs_triage
    GROUP BY hhs_review_lane
),

pivot AS (
    SELECT
        COALESCE(
            SUM(amount)
            FILTER (
                WHERE hhs_review_lane =
                      'CMS_DIRECT_REVIEW'
            ),
            0
        ) AS cms_direct,

        COALESCE(
            SUM(amount)
            FILTER (
                WHERE hhs_review_lane =
                      'MEDICAID_RELATED_REVIEW'
            ),
            0
        ) AS medicaid_related,

        COALESCE(
            SUM(amount)
            FILTER (
                WHERE hhs_review_lane =
                      'MEDICARE_RELATED_REVIEW'
            ),
            0
        ) AS medicare_related,

        COALESCE(
            SUM(amount)
            FILTER (
                WHERE hhs_review_lane =
                      'CHIP_RELATED_REVIEW'
            ),
            0
        ) AS chip_related,

        COALESCE(
            SUM(amount)
            FILTER (
                WHERE hhs_review_lane =
                      'HEALTH_PROGRAM_DISTINCT_CANDIDATE'
            ),
            0
        ) AS distinct_candidate

    FROM totals
)

SELECT
    ROUND(cms_direct, 2)
        AS cms_direct_review_dollars,

    ROUND(medicaid_related, 2)
        AS medicaid_related_review_dollars,

    ROUND(medicare_related, 2)
        AS medicare_related_review_dollars,

    ROUND(chip_related, 2)
        AS chip_related_review_dollars,

    ROUND(distinct_candidate, 2)
        AS health_program_distinct_candidate_dollars,

    ROUND(
        cms_direct
        + medicaid_related
        + medicare_related
        + chip_related
        + distinct_candidate,
        2
    ) AS reconstructed_hhs_dollars,

    ROUND(
        (
            cms_direct
            + medicaid_related
            + medicare_related
            + chip_related
            + distinct_candidate
        )
        - 21975789147.43,
        2
    ) AS bridge_difference

FROM pivot;


/* ============================================================================
   CLEANUP
   ========================================================================== */

DROP VIEW etl_174b_5e_hhs_triage;
DROP VIEW etl_174b_5e_residual;