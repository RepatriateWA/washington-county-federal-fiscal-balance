/*
===============================================================================
ETL-174B-5H
MEDICAID CONTROL-COMPOSITION RECONCILIATION
===============================================================================

PURPOSE
-------
Determine whether selected CMS-adjacent USAspending assistance programs are
already represented in the authoritative Washington Medicaid expenditure
control.

Programs under primary review:

    93.791  Money Follows the Person Rebalancing Demonstration
    93.796  State Survey Certification - Title XIX Medicaid
    93.775  State Medicaid Fraud Control Units

Comparison program:

    93.777  State Survey and Certification - Title XVIII Medicare

5G established that:

1. Washington Medicaid's accounting control comes from
   cms.medicaid_state_control_total.

2. The control is "Total Net Expenditures", uses FEDERAL_FISCAL_YEAR,
   and reports the federal share.

3. cms.medicaid_service_expenditures contains the service-category detail
   underlying the Medicaid control and includes
   is_additive_to_control_total.

4. USAspending descriptions alone are insufficient to establish whether
   these programs are economically distinct from the MBES control.

GOVERNING QUESTION
------------------
Does the MBES Medicaid control already contain the same economic expenditure
represented by each USAspending program?

IMPORTANT
---------
Read only.

No accounting disposition is persisted by this script.

No program is INCLUDE or EXCLUDE merely because its title or description
contains "Medicaid", "Medicare", "administration", "demonstration", or similar
language.

COVID remains an independent funding characteristic.

===============================================================================
*/

\pset pager off


/* ============================================================================
   1. AUTHORITATIVE MEDICAID CONTROL
   ========================================================================== */

SELECT
    'MEDICAID STATE CONTROL' AS section,

    fiscal_year,

    ROUND(total_computable, 2)
        AS total_computable_dollars,

    ROUND(federal_share, 2)
        AS federal_share_dollars,

    ROUND(federal_share_medicaid, 2)
        AS federal_share_medicaid_dollars,

    ROUND(federal_share_arra, 2)
        AS federal_share_arra_dollars,

    ROUND(federal_share_covid, 2)
        AS federal_share_covid_dollars,

    ROUND(state_share, 2)
        AS state_share_dollars,

    control_total_label,
    expenditure_time_basis,
    source_file,
    source_worksheet,
    source_row_number

FROM cms.medicaid_state_control_total AS m

JOIN reference.state_registry AS s
  ON s.state_id = m.state_id

WHERE s.state_abbreviation = 'WA'
  AND m.fiscal_year BETWEEN 2015 AND 2024

ORDER BY m.fiscal_year;


/* ============================================================================
   2. MEDICAID SERVICE-CATEGORY DICTIONARY

   Establish the live category vocabulary before trying to identify overlap.
   ========================================================================== */

SELECT
    medicaid_service_category_id,
    service_category_name,
    normalized_service_category_name,
    is_adjustment,
    default_row_type,
    description

FROM reference.medicaid_service_category

ORDER BY
    normalized_service_category_name,
    service_category_name;


/* ============================================================================
   3. WASHINGTON MEDICAID SERVICE-CATEGORY DETAIL, 2020-2024

   This is the accounting composition we need to compare with USAspending.
   ========================================================================== */

SELECT
    mse.fiscal_year,

    msc.medicaid_service_category_id,
    msc.service_category_name,
    msc.normalized_service_category_name,

    mse.row_type,

    mse.is_additive_to_control_total,

    ROUND(
        SUM(mse.total_computable),
        2
    ) AS total_computable_dollars,

    ROUND(
        SUM(mse.federal_share),
        2
    ) AS federal_share_dollars,

    ROUND(
        SUM(mse.federal_share_medicaid),
        2
    ) AS federal_share_medicaid_dollars,

    ROUND(
        SUM(mse.federal_share_arra),
        2
    ) AS federal_share_arra_dollars,

    ROUND(
        SUM(mse.federal_share_covid),
        2
    ) AS federal_share_covid_dollars,

    ROUND(
        SUM(mse.state_share),
        2
    ) AS state_share_dollars,

    COUNT(*) AS source_row_count

FROM cms.medicaid_service_expenditures AS mse

JOIN reference.state_registry AS s
  ON s.state_id = mse.state_id

JOIN reference.medicaid_service_category AS msc
  ON msc.medicaid_service_category_id =
     mse.medicaid_service_category_id

WHERE s.state_abbreviation = 'WA'
  AND mse.fiscal_year BETWEEN 2020 AND 2024

GROUP BY
    mse.fiscal_year,
    msc.medicaid_service_category_id,
    msc.service_category_name,
    msc.normalized_service_category_name,
    mse.row_type,
    mse.is_additive_to_control_total

ORDER BY
    mse.fiscal_year,
    ABS(SUM(mse.federal_share)) DESC,
    msc.normalized_service_category_name;


/* ============================================================================
   4. SERVICE-CATEGORY CONTRIBUTION CONTROL

   Compare the detail explicitly marked additive to the state control.

   This tells us whether the service detail is intended to reproduce the
   authoritative control, rather than assuming it does.
   ========================================================================== */

WITH detail AS (

    SELECT
        mse.fiscal_year,

        SUM(
            CASE
                WHEN mse.is_additive_to_control_total
                THEN mse.federal_share
                ELSE 0
            END
        ) AS additive_detail_federal_share,

        SUM(
            CASE
                WHEN NOT COALESCE(
                    mse.is_additive_to_control_total,
                    false
                )
                THEN mse.federal_share
                ELSE 0
            END
        ) AS nonadditive_detail_federal_share

    FROM cms.medicaid_service_expenditures AS mse

    JOIN reference.state_registry AS s
      ON s.state_id = mse.state_id

    WHERE s.state_abbreviation = 'WA'
      AND mse.fiscal_year BETWEEN 2020 AND 2024

    GROUP BY mse.fiscal_year
),

control AS (

    SELECT
        m.fiscal_year,
        m.federal_share AS control_federal_share

    FROM cms.medicaid_state_control_total AS m

    JOIN reference.state_registry AS s
      ON s.state_id = m.state_id

    WHERE s.state_abbreviation = 'WA'
      AND m.fiscal_year BETWEEN 2020 AND 2024
)

SELECT
    c.fiscal_year,

    ROUND(
        c.control_federal_share,
        2
    ) AS control_federal_share,

    ROUND(
        d.additive_detail_federal_share,
        2
    ) AS additive_detail_federal_share,

    ROUND(
        d.nonadditive_detail_federal_share,
        2
    ) AS nonadditive_detail_federal_share,

    ROUND(
        d.additive_detail_federal_share
        - c.control_federal_share,
        2
    ) AS additive_detail_minus_control

FROM control AS c

LEFT JOIN detail AS d
  ON d.fiscal_year = c.fiscal_year

ORDER BY c.fiscal_year;


/* ============================================================================
   5. KEYWORD SCREEN OF MEDICAID SERVICE CATEGORIES

   Screening only.

   Search specifically for terminology potentially related to the three
   USAspending programs under review.
   ========================================================================== */

SELECT
    mse.fiscal_year,

    msc.service_category_name,
    msc.normalized_service_category_name,
    msc.description,

    mse.row_type,
    mse.is_additive_to_control_total,

    ROUND(
        SUM(mse.federal_share),
        2
    ) AS federal_share_dollars,

    ROUND(
        SUM(mse.federal_share_covid),
        2
    ) AS federal_share_covid_dollars,

    COUNT(*) AS source_row_count

FROM cms.medicaid_service_expenditures AS mse

JOIN reference.state_registry AS s
  ON s.state_id = mse.state_id

JOIN reference.medicaid_service_category AS msc
  ON msc.medicaid_service_category_id =
     mse.medicaid_service_category_id

WHERE s.state_abbreviation = 'WA'
  AND mse.fiscal_year BETWEEN 2020 AND 2024

  AND (
       UPPER(COALESCE(msc.service_category_name, ''))
           LIKE '%MONEY FOLLOWS%'

    OR UPPER(COALESCE(msc.normalized_service_category_name, ''))
           LIKE '%MONEY FOLLOWS%'

    OR UPPER(COALESCE(msc.description, ''))
           LIKE '%MONEY FOLLOWS%'

    OR UPPER(COALESCE(msc.service_category_name, ''))
           LIKE '%SURVEY%'

    OR UPPER(COALESCE(msc.normalized_service_category_name, ''))
           LIKE '%SURVEY%'

    OR UPPER(COALESCE(msc.description, ''))
           LIKE '%SURVEY%'

    OR UPPER(COALESCE(msc.service_category_name, ''))
           LIKE '%CERTIFICATION%'

    OR UPPER(COALESCE(msc.normalized_service_category_name, ''))
           LIKE '%CERTIFICATION%'

    OR UPPER(COALESCE(msc.description, ''))
           LIKE '%CERTIFICATION%'

    OR UPPER(COALESCE(msc.service_category_name, ''))
           LIKE '%FRAUD%'

    OR UPPER(COALESCE(msc.normalized_service_category_name, ''))
           LIKE '%FRAUD%'

    OR UPPER(COALESCE(msc.description, ''))
           LIKE '%FRAUD%'

    OR UPPER(COALESCE(msc.service_category_name, ''))
           LIKE '%ADMIN%'

    OR UPPER(COALESCE(msc.normalized_service_category_name, ''))
           LIKE '%ADMIN%'

    OR UPPER(COALESCE(msc.description, ''))
           LIKE '%ADMIN%'

    OR UPPER(COALESCE(msc.service_category_name, ''))
           LIKE '%DEMONSTRATION%'

    OR UPPER(COALESCE(msc.normalized_service_category_name, ''))
           LIKE '%DEMONSTRATION%'

    OR UPPER(COALESCE(msc.description, ''))
           LIKE '%DEMONSTRATION%'
  )

GROUP BY
    mse.fiscal_year,
    msc.service_category_name,
    msc.normalized_service_category_name,
    msc.description,
    mse.row_type,
    mse.is_additive_to_control_total

ORDER BY
    mse.fiscal_year,
    ABS(SUM(mse.federal_share)) DESC,
    msc.normalized_service_category_name;


/* ============================================================================
   6. RAW MBES KEYWORD SCREEN

   Search the source rows themselves.

   This avoids relying solely on our normalized service-category dictionary.
   ========================================================================== */

SELECT
    fiscal_year,
    section_code,
    row_type,
    service_category,

    ROUND(
        SUM(total_computable),
        2
    ) AS total_computable_dollars,

    ROUND(
        SUM(federal_share),
        2
    ) AS federal_share_dollars,

    ROUND(
        SUM(federal_share_covid),
        2
    ) AS federal_share_covid_dollars,

    COUNT(*) AS raw_row_count

FROM cms_raw.medicaid_mbes

WHERE state_name = 'Washington'
  AND fiscal_year BETWEEN 2020 AND 2024

  AND (
       UPPER(COALESCE(service_category, ''))
           LIKE '%MONEY FOLLOWS%'

    OR UPPER(COALESCE(service_category, ''))
           LIKE '%SURVEY%'

    OR UPPER(COALESCE(service_category, ''))
           LIKE '%CERTIFICATION%'

    OR UPPER(COALESCE(service_category, ''))
           LIKE '%FRAUD%'

    OR UPPER(COALESCE(service_category, ''))
           LIKE '%ADMIN%'

    OR UPPER(COALESCE(service_category, ''))
           LIKE '%DEMONSTRATION%'
  )

GROUP BY
    fiscal_year,
    section_code,
    row_type,
    service_category

ORDER BY
    fiscal_year,
    ABS(SUM(federal_share)) DESC,
    service_category;


/* ============================================================================
   7. COMPLETE MBES CATEGORY PROFILE FOR POSSIBLE ADMINISTRATIVE ROWS

   Broader than Section 5, but still limited to rows whose accounting structure
   suggests something other than ordinary medical-service benefit spending.
   ========================================================================== */

SELECT
    mse.fiscal_year,

    msc.service_category_name,
    msc.normalized_service_category_name,
    msc.description,

    mse.row_type,
    mse.is_additive_to_control_total,

    ROUND(
        SUM(mse.federal_share),
        2
    ) AS federal_share_dollars,

    COUNT(*) AS source_row_count

FROM cms.medicaid_service_expenditures AS mse

JOIN reference.state_registry AS s
  ON s.state_id = mse.state_id

JOIN reference.medicaid_service_category AS msc
  ON msc.medicaid_service_category_id =
     mse.medicaid_service_category_id

WHERE s.state_abbreviation = 'WA'
  AND mse.fiscal_year BETWEEN 2020 AND 2024

  AND (
       UPPER(COALESCE(mse.row_type, ''))
           NOT IN (
               'SERVICE',
               'EXPENDITURE',
               'MEDICAL_ASSISTANCE'
           )

       OR COALESCE(msc.is_adjustment, false)

       OR NOT COALESCE(
           mse.is_additive_to_control_total,
           false
       )
  )

GROUP BY
    mse.fiscal_year,
    msc.service_category_name,
    msc.normalized_service_category_name,
    msc.description,
    mse.row_type,
    mse.is_additive_to_control_total

ORDER BY
    mse.fiscal_year,
    ABS(SUM(mse.federal_share)) DESC,
    msc.normalized_service_category_name;


/* ============================================================================
   8. USAspending CONTROL - THREE MEDICAID-ADJACENT PROGRAMS

   Preserve the exact USAspending amounts being tested.
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

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
    ) AS covid_obligation_dollars

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number IN (
      '93.791',
      '93.796',
      '93.775'
  )

GROUP BY
    action_date_fiscal_year,
    cfda_number

ORDER BY
    fiscal_year,
    cfda_number;


/* ============================================================================
   9. USAspending CONTROL - MEDICARE COMPARISON PROGRAM 93.777
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

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
    ) AS covid_obligation_dollars

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.777'

GROUP BY
    action_date_fiscal_year,
    cfda_number

ORDER BY fiscal_year;


/* ============================================================================
   10. DIRECT AMOUNT-MATCH SCREEN

   This is NOT evidence of overlap by itself.

   It asks whether any MBES service-category federal-share amount happens to
   equal a USAspending program amount in the same fiscal year.

   Exact or near matches would justify closer source-row inspection.
   Absence of a match does not prove distinctness.
   ========================================================================== */

WITH usaspending AS (

    SELECT
        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        SUM(federal_action_obligation)
            AS usaspending_obligation

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number IN (
          '93.791',
          '93.796',
          '93.775'
      )

    GROUP BY
        action_date_fiscal_year,
        cfda_number
),

mbes AS (

    SELECT
        mse.fiscal_year,
        msc.service_category_name,
        msc.normalized_service_category_name,
        mse.is_additive_to_control_total,

        SUM(mse.federal_share)
            AS mbes_federal_share

    FROM cms.medicaid_service_expenditures AS mse

    JOIN reference.state_registry AS s
      ON s.state_id = mse.state_id

    JOIN reference.medicaid_service_category AS msc
      ON msc.medicaid_service_category_id =
         mse.medicaid_service_category_id

    WHERE s.state_abbreviation = 'WA'
      AND mse.fiscal_year BETWEEN 2020 AND 2024

    GROUP BY
        mse.fiscal_year,
        msc.service_category_name,
        msc.normalized_service_category_name,
        mse.is_additive_to_control_total
)

SELECT
    u.fiscal_year,
    u.cfda_number,

    ROUND(
        u.usaspending_obligation,
        2
    ) AS usaspending_obligation,

    m.service_category_name,
    m.normalized_service_category_name,
    m.is_additive_to_control_total,

    ROUND(
        m.mbes_federal_share,
        2
    ) AS mbes_federal_share,

    ROUND(
        m.mbes_federal_share
        - u.usaspending_obligation,
        2
    ) AS mbes_minus_usaspending,

    ROUND(
        ABS(
            m.mbes_federal_share
            - u.usaspending_obligation
        ),
        2
    ) AS absolute_difference

FROM usaspending AS u

JOIN mbes AS m
  ON m.fiscal_year = u.fiscal_year

WHERE ABS(
          m.mbes_federal_share
          - u.usaspending_obligation
      ) <= 1000000

ORDER BY
    u.fiscal_year,
    u.cfda_number,
    absolute_difference;


/* ============================================================================
   11. CONTROL CLOSURE SUMMARY

   Compact end-state diagnostic.
   ========================================================================== */

WITH detail AS (

    SELECT
        mse.fiscal_year,

        SUM(
            CASE
                WHEN mse.is_additive_to_control_total
                THEN mse.federal_share
                ELSE 0
            END
        ) AS additive_detail

    FROM cms.medicaid_service_expenditures AS mse

    JOIN reference.state_registry AS s
      ON s.state_id = mse.state_id

    WHERE s.state_abbreviation = 'WA'
      AND mse.fiscal_year BETWEEN 2020 AND 2024

    GROUP BY mse.fiscal_year
),

control AS (

    SELECT
        m.fiscal_year,
        m.federal_share AS control_amount

    FROM cms.medicaid_state_control_total AS m

    JOIN reference.state_registry AS s
      ON s.state_id = m.state_id

    WHERE s.state_abbreviation = 'WA'
      AND m.fiscal_year BETWEEN 2020 AND 2024
)

SELECT
    c.fiscal_year,

    ROUND(
        c.control_amount,
        2
    ) AS control_amount,

    ROUND(
        d.additive_detail,
        2
    ) AS additive_detail,

    ROUND(
        d.additive_detail - c.control_amount,
        2
    ) AS closure_difference,

    CASE
        WHEN ABS(
            d.additive_detail - c.control_amount
        ) < 0.01
        THEN 'PASS'
        ELSE 'REVIEW'
    END AS closure_status

FROM control AS c

LEFT JOIN detail AS d
  ON d.fiscal_year = c.fiscal_year

ORDER BY c.fiscal_year;


/* ============================================================================
   12. END MARKER
   ========================================================================== */

SELECT
    'ETL-174B-5H PROFILE COMPLETE - NO DB WRITES'
        AS final_status;