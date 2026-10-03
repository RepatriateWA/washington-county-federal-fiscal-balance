/*
===============================================================================
ETL-174B-5I-2 / MIGRATION 177
CMS-SENSITIVE ASSISTANCE ACCOUNTING POLICY
===============================================================================

PURPOSE
-------
Persist the accounting conclusions reached through ETL-174B-5G through 5I.

PROGRAMS
--------
93.777  State Survey and Certification of Health Care Providers and Suppliers
        (Title XVIII) Medicare

        Decision:
            INCLUDE at source-policy level
            INCLUDE_ADDITIVE at award-classification level

        Basis:
            The certified Washington awards finance state survey agencies and
            regulatory/certification activity. The WCFFBP Medicare accounting
            structures profiled in ETL-174B-5I represent beneficiary/payment
            streams (Original Medicare FFS, reconstructed Part C, reconstructed
            Part D), not these state administrative grants.

93.775  State Medicaid Fraud Control Units

93.791  Money Follows the Person Rebalancing Demonstration

93.796  State Survey and Certification of Health Care Providers and Suppliers
        (Title XIX) Medicaid

        Decision for all three:
            REVIEW_REQUIRED at source-policy level
            WITHHOLD_UNRESOLVED at award-classification level

        Basis:
            WCFFBP uses the CMS Medicaid Total Net Expenditures control as the
            authoritative Medicaid accounting path. The current CMS Medicaid
            architecture deliberately does not construct an additive
            service-level decomposition. Existing evidence therefore does not
            establish that these three USAspending programs are either:
                (a) already contained in that control, or
                (b) economically distinct from it.

            They are withheld rather than forced into either INCLUDE or
            EXCLUDE_DUPLICATE.

ACCOUNTING PRINCIPLE
--------------------
No federal expenditure receives an additional plus sign merely because it
appears in a distinct federal reporting system.

Likewise, no federal expenditure is removed merely because its program title
resembles an authoritative control.

Classification requires affirmative evidence.

COVID
-----
This migration does not alter transaction-level COVID flags. COVID remains an
independent analytical dimension in analysis.v_certified_assistance_ledger.

EXPECTED FY2020-FY2024 FOUR-PROGRAM CONTROL
-------------------------------------------
93.775 + 93.777 + 93.791 + 93.796
= $394,380,089.04

READ/WRITE
----------
THIS MIGRATION WRITES REFERENCE POLICY AND AWARD-CLASSIFICATION RECORDS.
It does not alter raw USAspending transactions or CMS source data.
===============================================================================
*/

BEGIN;


/* ============================================================================
   1. PRE-WRITE CONTROL

   Assert the exact certified USAspending universe on which this migration is
   based.
   ========================================================================== */

DO $$
DECLARE
    v_control numeric;
BEGIN
    SELECT
        ROUND(SUM(federal_action_obligation), 2)
    INTO v_control
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number IN (
          '93.775',
          '93.777',
          '93.791',
          '93.796'
      );

    IF v_control IS DISTINCT FROM 394380089.04::numeric THEN
        RAISE EXCEPTION
            'ETL-174B-5I-2 pre-write control failed. Expected 394380089.04; observed %',
            v_control;
    END IF;

    RAISE NOTICE
        'PASS pre-write four-program control: %',
        v_control;
END
$$;


/* ============================================================================
   2. PROGRAM-LEVEL DESCRIPTIVE CLASSIFICATIONS

   These records describe program identity and overlap risk. They do not by
   themselves determine accounting inclusion.
   ========================================================================== */

INSERT INTO reference.federal_inflow_program_classification (
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
)
VALUES

(
    'USASPENDING_ASSISTANCE',
    '93.777',
    'STATE SURVEY AND CERTIFICATION OF HEALTH CARE PROVIDERS AND SUPPLIERS (TITLE XVIII) MEDICARE',
    'MEDICARE',
    'STATE_SURVEY_CERTIFICATION',
    'LOW',
    TRUE,
    TRUE,
    $basis$
ETL-174B-5I reconciled Washington USAspending Assistance Listing 93.777
against the live WCFFBP Medicare accounting architecture. The Medicare
reporting path is based on CMS geographic Medicare payments, while the broader
Medicare core contains Original Medicare FFS, reconstructed Part C, and
reconstructed Part D. The observed 93.777 awards instead finance Washington
state survey agencies performing provider survey, certification, and
quality-standard verification activities. The program is therefore
economically distinct from the Medicare beneficiary/payment streams currently
represented by the WCFFBP Medicare accounting structures. COVID relevance is
preserved independently from accounting disposition.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
),

(
    'USASPENDING_ASSISTANCE',
    '93.775',
    'STATE MEDICAID FRAUD CONTROL UNITS',
    'MEDICAID',
    'MEDICAID_ADMIN_REVIEW',
    'HIGH',
    TRUE,
    TRUE,
    $basis$
ETL-174B-5H confirmed that WCFFBP uses the CMS Medicaid Total Net Expenditures
control as its authoritative Medicaid accounting path and deliberately does
not treat raw CMS service-level rows as an additive decomposition of that
control. Current evidence does not establish whether USAspending Assistance
Listing 93.775 is contained within or economically distinct from that
authoritative control. The program therefore remains unresolved rather than
being forced into either additive or duplicate treatment.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
),

(
    'USASPENDING_ASSISTANCE',
    '93.791',
    'MONEY FOLLOWS THE PERSON REBALANCING DEMONSTRATION',
    'MEDICAID',
    'MEDICAID_DEMONSTRATION_REVIEW',
    'HIGH',
    TRUE,
    TRUE,
    $basis$
ETL-174B-5H confirmed that WCFFBP uses the CMS Medicaid Total Net Expenditures
control as its authoritative Medicaid accounting path and deliberately does
not treat raw CMS service-level rows as an additive decomposition of that
control. Current evidence does not establish whether USAspending Assistance
Listing 93.791 is contained within or economically distinct from that
authoritative control. The program therefore remains unresolved rather than
being forced into either additive or duplicate treatment.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
),

(
    'USASPENDING_ASSISTANCE',
    '93.796',
    'STATE SURVEY AND CERTIFICATION OF HEALTH CARE PROVIDERS AND SUPPLIERS (TITLE XIX) MEDICAID',
    'MEDICAID',
    'STATE_SURVEY_CERTIFICATION_REVIEW',
    'HIGH',
    TRUE,
    TRUE,
    $basis$
ETL-174B-5H confirmed that WCFFBP uses the CMS Medicaid Total Net Expenditures
control as its authoritative Medicaid accounting path and deliberately does
not treat raw CMS service-level rows as an additive decomposition of that
control. Current evidence does not establish whether USAspending Assistance
Listing 93.796 is contained within or economically distinct from that
authoritative control. The program therefore remains unresolved rather than
being forced into either additive or duplicate treatment.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
)

ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)
DO UPDATE SET
    source_program_title = EXCLUDED.source_program_title,
    inflow_family = EXCLUDED.inflow_family,
    inflow_subfamily = EXCLUDED.inflow_subfamily,
    overlap_risk = EXCLUDED.overlap_risk,
    covid_relevance = EXCLUDED.covid_relevance,
    extraordinary_relevance = EXCLUDED.extraordinary_relevance,
    classification_basis = EXCLUDED.classification_basis,
    valid_from_fiscal_year = EXCLUDED.valid_from_fiscal_year,
    valid_through_fiscal_year = EXCLUDED.valid_through_fiscal_year,
    updated_at = CURRENT_TIMESTAMP;


/* ============================================================================
   3. SOURCE POLICY — 93.777

   Program-level accounting authorization.

   reference.federal_inflow_source_policy uses INCLUDE, not
   INCLUDE_ADDITIVE.
   ========================================================================== */

INSERT INTO reference.federal_inflow_source_policy (
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
VALUES (
    'MEDICARE',
    'STATE_SURVEY_CERTIFICATION',
    'FEDERAL_ASSISTANCE_OBLIGATIONS',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    $basis$
ETL-174B-5I established that Assistance Listing 93.777 finances Washington
state survey and certification activity and is economically distinct from the
CMS Medicare beneficiary/payment streams represented by the WCFFBP Medicare
accounting structures. USAspending federal_action_obligation is therefore the
preferred accounting measure for this distinct federal assistance stream.

This policy does not authorize the broader CMS Medicare core for the principal
FFY ledger. Medicare-core timing and coverage authorization remains a separate
accounting decision.

COVID tagging remains an independent analytical dimension and does not alter
the additive accounting treatment.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
);


/* ============================================================================
   4. SOURCE POLICIES — MEDICAID-ADJACENT UNRESOLVED PROGRAMS

   Source-policy contract uses REVIEW_REQUIRED.
   ========================================================================== */

INSERT INTO reference.federal_inflow_source_policy (
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
VALUES

(
    'MEDICAID',
    'MEDICAID_FRAUD_CONTROL_REVIEW',
    'FEDERAL_ASSISTANCE_OBLIGATIONS',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY['CMS_MEDICAID_TOTAL_NET_EXPENDITURES']::text[],
    'REVIEW_REQUIRED',
    $basis$
Assistance Listing 93.775 remains unresolved against the authoritative CMS
Medicaid Total Net Expenditures control. Existing evidence does not prove
either duplication or economic distinctness. No additional ledger plus sign
is authorized pending affirmative reconciliation.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
),

(
    'MEDICAID',
    'MONEY_FOLLOWS_PERSON_REVIEW',
    'FEDERAL_ASSISTANCE_OBLIGATIONS',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY['CMS_MEDICAID_TOTAL_NET_EXPENDITURES']::text[],
    'REVIEW_REQUIRED',
    $basis$
Assistance Listing 93.791 remains unresolved against the authoritative CMS
Medicaid Total Net Expenditures control. Existing evidence does not prove
either duplication or economic distinctness. No additional ledger plus sign
is authorized pending affirmative reconciliation.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
),

(
    'MEDICAID',
    'STATE_SURVEY_CERTIFICATION_REVIEW',
    'FEDERAL_ASSISTANCE_OBLIGATIONS',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY['CMS_MEDICAID_TOTAL_NET_EXPENDITURES']::text[],
    'REVIEW_REQUIRED',
    $basis$
Assistance Listing 93.796 remains unresolved against the authoritative CMS
Medicaid Total Net Expenditures control. Existing evidence does not prove
either duplication or economic distinctness. No additional ledger plus sign
is authorized pending affirmative reconciliation.
$basis$,
    'ANALYSIS-174B-5I-v1',
    2020,
    2024
);


/* ============================================================================
   5. AWARD-LEVEL CLASSIFICATIONS

   Use the certified ledger to discover every observed award identifier for the
   four programs. This avoids hard-coding a partial FAIN list.

   93.777 -> INCLUDE_ADDITIVE
   others -> WITHHOLD_UNRESOLVED
   ========================================================================== */

INSERT INTO reference.federal_inflow_award_classification (
    source_system,
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)

SELECT DISTINCT
    'USASPENDING_ASSISTANCE' AS source_system,

    ledger.cfda_number AS source_program_code,

    ledger.award_id_fain AS source_award_identifier,

    CASE
        WHEN ledger.cfda_number = '93.777'
            THEN 'MEDICARE'
        ELSE 'MEDICAID'
    END AS inflow_family,

    CASE ledger.cfda_number
        WHEN '93.775'
            THEN 'MEDICAID_FRAUD_CONTROL_REVIEW'
        WHEN '93.777'
            THEN 'STATE_SURVEY_CERTIFICATION'
        WHEN '93.791'
            THEN 'MONEY_FOLLOWS_PERSON_REVIEW'
        WHEN '93.796'
            THEN 'STATE_SURVEY_CERTIFICATION_REVIEW'
    END AS inflow_subfamily,

    CASE
        WHEN ledger.cfda_number = '93.777'
            THEN 'INCLUDE_ADDITIVE'
        ELSE 'WITHHOLD_UNRESOLVED'
    END AS accounting_disposition,

    CASE
        WHEN ledger.cfda_number = '93.777'
        THEN
            'ETL-174B-5I: award belongs to Medicare state survey and certification assistance, a state administrative/regulatory grant stream distinct from the WCFFBP Medicare beneficiary/payment accounting structures.'
        ELSE
            'ETL-174B-5H/5I: Medicaid-adjacent award remains unresolved against the authoritative CMS Medicaid Total Net Expenditures control; neither duplication nor economic distinctness has been affirmatively established.'
    END AS classification_basis,

    'ANALYSIS-174B-5I-v1'
        AS methodology_version,

    2020 AS valid_from_fiscal_year,
    2024 AS valid_through_fiscal_year

FROM analysis.v_certified_assistance_ledger AS ledger

WHERE ledger.reference_state_abbreviation = 'WA'
  AND ledger.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND ledger.cfda_number IN (
      '93.775',
      '93.777',
      '93.791',
      '93.796'
  )
  AND NULLIF(TRIM(ledger.award_id_fain), '') IS NOT NULL

ON CONFLICT (
    source_system,
    source_program_code,
    source_award_identifier,
    methodology_version
)
DO UPDATE SET
    inflow_family = EXCLUDED.inflow_family,
    inflow_subfamily = EXCLUDED.inflow_subfamily,
    accounting_disposition = EXCLUDED.accounting_disposition,
    classification_basis = EXCLUDED.classification_basis,
    valid_from_fiscal_year = EXCLUDED.valid_from_fiscal_year,
    valid_through_fiscal_year = EXCLUDED.valid_through_fiscal_year,
    updated_at = CURRENT_TIMESTAMP;


/* ============================================================================
   6. ASSERT ALL OBSERVED AWARDS RECEIVED A CLASSIFICATION
   ========================================================================== */

DO $$
DECLARE
    v_missing bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_missing
    FROM (
        SELECT DISTINCT
            ledger.cfda_number,
            ledger.award_id_fain
        FROM analysis.v_certified_assistance_ledger AS ledger
        WHERE ledger.reference_state_abbreviation = 'WA'
          AND ledger.action_date_fiscal_year BETWEEN 2020 AND 2024
          AND ledger.cfda_number IN (
              '93.775',
              '93.777',
              '93.791',
              '93.796'
          )
          AND NULLIF(TRIM(ledger.award_id_fain), '') IS NOT NULL
    ) AS observed

    LEFT JOIN reference.federal_inflow_award_classification AS classification
      ON classification.source_system = 'USASPENDING_ASSISTANCE'
     AND classification.source_program_code = observed.cfda_number
     AND classification.source_award_identifier = observed.award_id_fain
     AND classification.methodology_version = 'ANALYSIS-174B-5I-v1'

    WHERE classification.federal_inflow_award_classification_id IS NULL;

    IF v_missing <> 0 THEN
        RAISE EXCEPTION
            'ETL-174B-5I-2 award-classification coverage failed. Missing awards: %',
            v_missing;
    END IF;

    RAISE NOTICE
        'PASS award-classification coverage: no observed awards missing';
END
$$;


/* ============================================================================
   7. POST-WRITE ACCOUNTING BRIDGE

   Reconstruct amounts from the certified transaction ledger joined to the
   persisted award classification.
   ========================================================================== */

WITH classified AS (

    SELECT
        ledger.action_date_fiscal_year AS fiscal_year,
        ledger.cfda_number,
        classification.accounting_disposition,
        ledger.federal_action_obligation,
        ledger.is_covid

    FROM analysis.v_certified_assistance_ledger AS ledger

    JOIN reference.federal_inflow_award_classification AS classification
      ON classification.source_system = 'USASPENDING_ASSISTANCE'
     AND classification.source_program_code = ledger.cfda_number
     AND classification.source_award_identifier = ledger.award_id_fain
     AND classification.methodology_version = 'ANALYSIS-174B-5I-v1'

    WHERE ledger.reference_state_abbreviation = 'WA'
      AND ledger.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND ledger.cfda_number IN (
          '93.775',
          '93.777',
          '93.791',
          '93.796'
      )
)

SELECT
    cfda_number,
    accounting_disposition,
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

GROUP BY
    cfda_number,
    accounting_disposition

ORDER BY cfda_number;


/* ============================================================================
   8. FINAL FOUR-PROGRAM RECONCILIATION ASSERTION
   ========================================================================== */

DO $$
DECLARE
    v_total numeric;
    v_include numeric;
    v_withhold numeric;
BEGIN

    WITH classified AS (

        SELECT
            classification.accounting_disposition,
            ledger.federal_action_obligation

        FROM analysis.v_certified_assistance_ledger AS ledger

        JOIN reference.federal_inflow_award_classification AS classification
          ON classification.source_system = 'USASPENDING_ASSISTANCE'
         AND classification.source_program_code = ledger.cfda_number
         AND classification.source_award_identifier = ledger.award_id_fain
         AND classification.methodology_version = 'ANALYSIS-174B-5I-v1'

        WHERE ledger.reference_state_abbreviation = 'WA'
          AND ledger.action_date_fiscal_year BETWEEN 2020 AND 2024
          AND ledger.cfda_number IN (
              '93.775',
              '93.777',
              '93.791',
              '93.796'
          )
    )

    SELECT
        ROUND(SUM(federal_action_obligation), 2),

        ROUND(
            SUM(
                CASE
                    WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            2
        ),

        ROUND(
            SUM(
                CASE
                    WHEN accounting_disposition = 'WITHHOLD_UNRESOLVED'
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            2
        )

    INTO
        v_total,
        v_include,
        v_withhold

    FROM classified;


    IF v_total IS DISTINCT FROM 394380089.04::numeric THEN
        RAISE EXCEPTION
            'Final four-program control failed. Expected 394380089.04; observed %',
            v_total;
    END IF;


    IF v_include IS DISTINCT FROM 40775969.39::numeric THEN
        RAISE EXCEPTION
            '93.777 additive control failed. Expected 40775969.39; observed %',
            v_include;
    END IF;


    IF v_withhold IS DISTINCT FROM 353604119.65::numeric THEN
        RAISE EXCEPTION
            'Medicaid-adjacent withheld control failed. Expected 353604119.65; observed %',
            v_withhold;
    END IF;


    IF ROUND(v_include + v_withhold, 2)
       IS DISTINCT FROM v_total THEN

        RAISE EXCEPTION
            'Accounting bridge failed: include % + withhold % <> total %',
            v_include,
            v_withhold,
            v_total;
    END IF;


    RAISE NOTICE
        'PASS final bridge: total %, include %, withhold %',
        v_total,
        v_include,
        v_withhold;

END
$$;


/* ============================================================================
   9. FINAL POLICY ASSERTIONS
   ========================================================================== */

DO $$
DECLARE
    v_93777_policy bigint;
    v_review_policies bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_93777_policy
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'MEDICARE'
      AND inflow_subfamily = 'STATE_SURVEY_CERTIFICATION'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-174B-5I-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    SELECT COUNT(*)
    INTO v_review_policies
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'MEDICAID'
      AND inflow_subfamily IN (
          'MEDICAID_FRAUD_CONTROL_REVIEW',
          'MONEY_FOLLOWS_PERSON_REVIEW',
          'STATE_SURVEY_CERTIFICATION_REVIEW'
      )
      AND ledger_treatment = 'REVIEW_REQUIRED'
      AND methodology_version = 'ANALYSIS-174B-5I-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    IF v_93777_policy <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one 93.777 INCLUDE source policy; observed %',
            v_93777_policy;
    END IF;


    IF v_review_policies <> 3 THEN
        RAISE EXCEPTION
            'Expected exactly three Medicaid REVIEW_REQUIRED source policies; observed %',
            v_review_policies;
    END IF;


    RAISE NOTICE
        'PASS source-policy assertions: 1 INCLUDE + 3 REVIEW_REQUIRED';

END
$$;


/* ============================================================================
   10. COMPLETION MARKER
   ========================================================================== */

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5I-2 PASS - CMS-sensitive assistance accounting policy persisted';
END
$$;


COMMIT;