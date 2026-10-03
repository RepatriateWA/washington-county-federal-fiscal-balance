/*
===============================================================================
ETL-174B-5N-4
VA FINAL-REVIEW PROGRAM ADJUDICATION PROFILE
===============================================================================

PURPOSE
-------
Produce the final read-only evidence package for the 18 positive-dollar
CFDA 64.* programs left unresolved by ETL-174B-5N-3.

ETL-174B-5N-3 established:

    Class A direct GDX overlap     $22,798,869,788.97
    Class B final review              $908,773,543.31
    Class C zero-dollar                         $0.00
    Total VA assistance            $23,707,643,332.28

Class B COVID dollars:
                                      $293,054,380.66

READ ONLY.
NO DATABASE WRITES.
NO ACCOUNTING DISPOSITIONS ARE PERSISTED HERE.

METHOD
------
For each remaining program:

1. reproduce its certified dollar control;
2. profile annual obligations and COVID funding;
3. inspect recipient and award-description semantics;
4. expose the relevant GDX component categories and definitions;
5. compare annual program obligations with plausible GDX component amounts;
6. assign an EVIDENCE STATUS only:
      DIRECT_COMPONENT_EVIDENCE
      STRONG_SCOPE_EVIDENCE
      AMBIGUOUS_SCOPE
      NO_DIRECT_GDX_EVIDENCE

Evidence status is NOT an accounting disposition.
===============================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N-4 - VA FINAL-REVIEW PROGRAM ADJUDICATION PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''


/* ============================================================================
   SECTION 1
   FIXED 18-PROGRAM REVIEW UNIVERSE
   ========================================================================== */

DROP TABLE IF EXISTS va_5n4_review_programs;

CREATE TEMP TABLE va_5n4_review_programs (
    cfda_number text PRIMARY KEY,
    review_family text NOT NULL
);

INSERT INTO va_5n4_review_programs
    (cfda_number, review_family)
VALUES
    ('64.015', 'MEDICAL_CARE'),
    ('64.029', 'MEDICAL_CARE'),
    ('64.014', 'MEDICAL_CARE'),
    ('64.035', 'MEDICAL_CARE_RELATED'),
    ('64.055', 'MEDICAL_CARE_RELATED'),

    ('64.116', 'EDUCATION_VRE'),
    ('64.130', 'EDUCATION_VRE'),

    ('64.031', 'INSURANCE_SPECIAL_BENEFITS'),
    ('64.030', 'INSURANCE_SPECIAL_BENEFITS'),
    ('64.100', 'INSURANCE_SPECIAL_BENEFITS'),
    ('64.106', 'INSURANCE_SPECIAL_BENEFITS'),
    ('64.127', 'INSURANCE_SPECIAL_BENEFITS'),

    ('64.033', 'OTHER_VETERAN_SERVICES'),
    ('64.024', 'OTHER_VETERAN_SERVICES'),
    ('64.053', 'OTHER_VETERAN_SERVICES'),
    ('64.056', 'OTHER_VETERAN_SERVICES'),
    ('64.037', 'OTHER_VETERAN_SERVICES'),
    ('64.034', 'OTHER_VETERAN_SERVICES');

\echo ''
\echo 'SECTION 1 - FIXED 18-PROGRAM REVIEW UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM va_5n4_review_programs
ORDER BY review_family, cfda_number;


/* ============================================================================
   SECTION 2
   HARD CONTROL REPRODUCTION
   ========================================================================== */

\echo ''
\echo 'SECTION 2 - CLASS B CONTROL REPRODUCTION'
\echo '----------------------------------------------------------------------------------------------------'

WITH x AS (
    SELECT
        COUNT(DISTINCT l.cfda_number) AS program_count,
        COUNT(*) AS transaction_count,
        SUM(l.federal_action_obligation) AS obligation_dollars,
        SUM(
            CASE
                WHEN l.is_covid
                    THEN l.federal_action_obligation
                ELSE 0
            END
        ) AS covid_dollars
    FROM analysis.v_certified_assistance_ledger AS l
    JOIN va_5n4_review_programs AS r
      ON r.cfda_number = l.cfda_number
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
)
SELECT
    program_count,
    transaction_count,
    ROUND(obligation_dollars, 2) AS obligation_dollars,
    ROUND(covid_dollars, 2) AS covid_dollars,
    ROUND(
        obligation_dollars - 908773543.31::numeric,
        2
    ) AS obligation_difference_from_5n3,
    ROUND(
        covid_dollars - 293054380.66::numeric,
        2
    ) AS covid_difference_from_5n3
FROM x;


/* ============================================================================
   SECTION 3
   PROGRAM x YEAR
   ========================================================================== */

\echo ''
\echo 'SECTION 3 - FINAL-REVIEW PROGRAM x FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    r.review_family,
    l.cfda_number,
    MAX(l.cfda_title) AS cfda_title,
    l.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(SUM(l.federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN l.is_covid
                    THEN l.federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars
FROM analysis.v_certified_assistance_ledger AS l
JOIN va_5n4_review_programs AS r
  ON r.cfda_number = l.cfda_number
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
GROUP BY
    r.review_family,
    l.cfda_number,
    l.action_date_fiscal_year
ORDER BY
    r.review_family,
    l.cfda_number,
    l.action_date_fiscal_year;


/* ============================================================================
   SECTION 4
   PROGRAM SUMMARY
   ========================================================================== */

\echo ''
\echo 'SECTION 4 - FINAL-REVIEW PROGRAM SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    r.review_family,
    l.cfda_number,
    MAX(l.cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT NULLIF(l.award_id_fain, ''))
        AS distinct_nonblank_fains,
    ROUND(SUM(l.federal_action_obligation), 2)
        AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN l.is_covid
                    THEN l.federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    COUNT(*) FILTER (WHERE l.is_covid)
        AS covid_transaction_count
FROM analysis.v_certified_assistance_ledger AS l
JOIN va_5n4_review_programs AS r
  ON r.cfda_number = l.cfda_number
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
GROUP BY
    r.review_family,
    l.cfda_number
ORDER BY
    obligation_dollars DESC;


/* ============================================================================
   SECTION 5
   TOP RECIPIENTS

   Recipient structure can distinguish:
   - direct individual benefit representations,
   - state institutional reimbursement,
   - grants to service organizations,
   - aggregate program accounting records.
   ========================================================================== */

\echo ''
\echo 'SECTION 5 - TOP RECIPIENTS BY PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH x AS (
    SELECT
        r.review_family,
        l.cfda_number,
        MAX(l.cfda_title) AS cfda_title,
        COALESCE(NULLIF(l.recipient_name, ''), '[BLANK]')
            AS recipient_name,
        COUNT(*) AS transaction_count,
        SUM(l.federal_action_obligation) AS obligation_dollars,
        ROW_NUMBER() OVER (
            PARTITION BY l.cfda_number
            ORDER BY
                SUM(l.federal_action_obligation) DESC,
                COALESCE(NULLIF(l.recipient_name, ''), '[BLANK]')
        ) AS recipient_rank
    FROM analysis.v_certified_assistance_ledger AS l
    JOIN va_5n4_review_programs AS r
      ON r.cfda_number = l.cfda_number
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
    GROUP BY
        r.review_family,
        l.cfda_number,
        COALESCE(NULLIF(l.recipient_name, ''), '[BLANK]')
)
SELECT
    review_family,
    cfda_number,
    cfda_title,
    recipient_rank,
    recipient_name,
    transaction_count,
    ROUND(obligation_dollars, 2) AS obligation_dollars
FROM x
WHERE recipient_rank <= 5
ORDER BY cfda_number, recipient_rank;


/* ============================================================================
   SECTION 6
   AWARD / DESCRIPTION PROFILE

   Show the largest records for human semantic review.
   Descriptions are evidence only.
   ========================================================================== */

\echo ''
\echo 'SECTION 6 - TOP AWARD/DESCRIPTION RECORDS'
\echo '----------------------------------------------------------------------------------------------------'

WITH x AS (
    SELECT
        r.review_family,
        l.cfda_number,
        l.cfda_title,
        l.action_date_fiscal_year AS fiscal_year,
        NULLIF(l.award_id_fain, '') AS award_id_fain,
        l.recipient_name,
        l.transaction_description,
        l.is_covid,
        l.defc_codes,
        l.federal_action_obligation,

        ROW_NUMBER() OVER (
            PARTITION BY l.cfda_number
            ORDER BY
                ABS(l.federal_action_obligation) DESC,
                l.action_date_fiscal_year,
                l.assistance_transaction_id
        ) AS amount_rank

    FROM analysis.v_certified_assistance_ledger AS l

    JOIN va_5n4_review_programs AS r
      ON r.cfda_number = l.cfda_number

    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
)

SELECT
    review_family,
    cfda_number,
    cfda_title,
    fiscal_year,
    amount_rank,
    award_id_fain,
    recipient_name,
    is_covid,
    defc_codes,
    ROUND(federal_action_obligation, 2) AS obligation_dollars,
    transaction_description

FROM x

WHERE amount_rank <= 5

ORDER BY cfda_number, amount_rank;


/* ============================================================================
   SECTION 7
   COVID / DEFC PROFILE
   ========================================================================== */

\echo ''
\echo 'SECTION 7 - COVID / DEFC PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    r.review_family,
    l.cfda_number,
    MAX(l.cfda_title) AS cfda_title,
    l.is_covid,
    l.defc_codes,
    COUNT(*) AS transaction_count,
    ROUND(SUM(l.federal_action_obligation), 2)
        AS obligation_dollars
FROM analysis.v_certified_assistance_ledger AS l
JOIN va_5n4_review_programs AS r
  ON r.cfda_number = l.cfda_number
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
GROUP BY
    r.review_family,
    l.cfda_number,
    l.is_covid,
    l.defc_codes
ORDER BY
    l.cfda_number,
    l.is_covid DESC,
    obligation_dollars DESC;


/* ============================================================================
   SECTION 8
   RELEVANT GDX CATEGORY DICTIONARY

   No fuzzy program classification is made here.
   We expose the categories relevant to the four review families.
   ========================================================================== */

\echo ''
\echo 'SECTION 8 - RELEVANT GDX CATEGORY DICTIONARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    gdx_category_id,
    category_code,
    category_name,
    aggregation_role,
    first_fiscal_year,
    last_fiscal_year,
    description
FROM va.gdx_expenditure_category
WHERE
       UPPER(category_name) LIKE '%MEDICAL%'
    OR UPPER(category_name) LIKE '%HEALTH%'
    OR UPPER(category_name) LIKE '%EDUCATION%'
    OR UPPER(category_name) LIKE '%VRE%'
    OR UPPER(category_name) LIKE '%INSURANCE%'
    OR UPPER(category_name) LIKE '%HOUSING%'
    OR UPPER(category_name) LIKE '%AUTOMOBILE%'
    OR UPPER(category_name) LIKE '%ADAPT%'
    OR UPPER(category_name) LIKE '%HOME%'
    OR UPPER(category_name) LIKE '%LOAN%'
    OR UPPER(category_name) LIKE '%OPERATING%'
    OR UPPER(category_name) LIKE '%MEMORIAL%'
ORDER BY
    first_fiscal_year,
    category_code;


/* ============================================================================
   SECTION 9
   RELEVANT GDX STATEWIDE COMPONENT AMOUNTS
   ========================================================================== */

\echo ''
\echo 'SECTION 9 - RELEVANT GDX COMPONENT AMOUNTS BY YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    ROUND(SUM(e.expenditure_amount), 2)
        AS washington_amount
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2024
  AND (
         UPPER(c.category_name) LIKE '%MEDICAL%'
      OR UPPER(c.category_name) LIKE '%HEALTH%'
      OR UPPER(c.category_name) LIKE '%EDUCATION%'
      OR UPPER(c.category_name) LIKE '%VRE%'
      OR UPPER(c.category_name) LIKE '%INSURANCE%'
      OR UPPER(c.category_name) LIKE '%HOUSING%'
      OR UPPER(c.category_name) LIKE '%AUTOMOBILE%'
      OR UPPER(c.category_name) LIKE '%ADAPT%'
      OR UPPER(c.category_name) LIKE '%HOME%'
      OR UPPER(c.category_name) LIKE '%LOAN%'
      OR UPPER(c.category_name) LIKE '%OPERATING%'
      OR UPPER(c.category_name) LIKE '%MEMORIAL%'
  )
GROUP BY
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY
    e.fiscal_year,
    washington_amount DESC;


/* ============================================================================
   SECTION 10
   PROGRAM-TO-CANDIDATE-GDX EVIDENCE MATRIX

   IMPORTANT:
   These are explicit research hypotheses, not accounting dispositions.

   The purpose is to test whether the remaining program concepts have an
   explicit GDX accounting home.
   ========================================================================== */

DROP TABLE IF EXISTS va_5n4_hypothesis;

CREATE TEMP TABLE va_5n4_hypothesis (
    cfda_number text PRIMARY KEY,
    candidate_gdx_concept text,
    evidence_question text
);

INSERT INTO va_5n4_hypothesis VALUES

('64.015', 'MEDICAL_CARE',
 'Is Veterans State Nursing Home Care contained in the GDX Medical Care component?'),

('64.029', 'MEDICAL_CARE',
 'Is Purchase Care contained in the GDX Medical Care component?'),

('64.014', 'MEDICAL_CARE',
 'Is Veterans State Domiciliary Care contained in the GDX Medical Care component?'),

('64.035', 'MEDICAL_CARE',
 'Is Veterans Transportation Program expenditure part of GDX Medical Care?'),

('64.055', 'MEDICAL_CARE',
 'Is suicide-prevention grant spending contained in GDX Medical Care or another GDX component?'),

('64.116', 'EDUCATION_VRE',
 'Does Veteran Readiness and Employment correspond to the explicit GDX Education/VRE component?'),

('64.130', 'EDUCATION_VRE',
 'Does Veteran Rapid Retraining Assistance correspond to the GDX Education/VRE component?'),

('64.031', 'INSURANCE',
 'Do direct veterans life-insurance payments correspond to the explicit GDX Insurance component?'),

('64.030', 'INSURANCE',
 'Does this life-insurance measure represent expenditures contained in GDX Insurance, or a non-expenditure face-value measure?'),

('64.100', 'SPECIALLY_ADAPTED_AUTOMOBILES',
 'Does this program correspond to the explicit GDX specially adapted automobiles component?'),

('64.106', 'SPECIALLY_ADAPTED_HOUSING',
 'Does this program correspond to the explicit GDX specially adapted housing component?'),

('64.127', 'COMPENSATION_SPECIAL_BENEFIT',
 'Are spina-bifida monthly allowances included within GDX compensation/pension or another direct-benefit component?'),

('64.033', 'OTHER_VETERAN_SERVICES',
 'Is SSVF expenditure represented within a GDX operating/medical/direct-expenditure component?'),

('64.024', 'OTHER_VETERAN_SERVICES',
 'Is Homeless Providers Grant and Per Diem represented within GDX Medical Care or operating expenditures?'),

('64.053', 'OTHER_VETERAN_SERVICES',
 'Are state-veterans-home nurse hiring payments contained in GDX Medical Care or another component?'),

('64.056', 'OTHER_VETERAN_SERVICES',
 'Are Legal Services for Veterans grants represented within an existing GDX component?'),

('64.037', 'OTHER_VETERAN_SERVICES',
 'Is the Paralympics monthly assistance allowance represented within a GDX benefit component?'),

('64.034', 'OTHER_VETERAN_SERVICES',
 'Are Adaptive Sports grants represented within a GDX component?');

\echo ''
\echo 'SECTION 10 - PROGRAM-TO-GDX RESEARCH HYPOTHESES'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    h.cfda_number,
    MAX(l.cfda_title) AS cfda_title,
    h.candidate_gdx_concept,
    h.evidence_question,
    ROUND(SUM(l.federal_action_obligation), 2)
        AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN l.is_covid
                    THEN l.federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars
FROM va_5n4_hypothesis AS h
JOIN analysis.v_certified_assistance_ledger AS l
  ON l.cfda_number = h.cfda_number
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
GROUP BY
    h.cfda_number,
    h.candidate_gdx_concept,
    h.evidence_question
ORDER BY
    obligation_dollars DESC;


/* ============================================================================
   SECTION 11
   PROGRAM TITLE / GDX SOURCE-CATEGORY TERM HITS

   Discovery evidence only.

   Unlike 5N-2, this also searches source_category_name because a useful
   historical label may not survive as the normalized category_name.
   ========================================================================== */

\echo ''
\echo 'SECTION 11 - PROGRAM / GDX SOURCE-CATEGORY SEMANTIC TERM HITS'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_terms AS (
    SELECT *
    FROM (
        VALUES
            ('64.015', 'NURSING'),
            ('64.015', 'HOME'),
            ('64.029', 'PURCHASE'),
            ('64.029', 'MEDICAL'),
            ('64.014', 'DOMICILIARY'),
            ('64.014', 'HOME'),
            ('64.035', 'TRANSPORT'),
            ('64.055', 'SUICIDE'),
            ('64.055', 'MENTAL'),
            ('64.116', 'VRE'),
            ('64.116', 'VOCATIONAL'),
            ('64.116', 'EDUCATION'),
            ('64.130', 'RETRAIN'),
            ('64.130', 'EDUCATION'),
            ('64.031', 'INSURANCE'),
            ('64.030', 'INSURANCE'),
            ('64.100', 'AUTOMOBILE'),
            ('64.100', 'ADAPT'),
            ('64.106', 'HOUSING'),
            ('64.106', 'ADAPT'),
            ('64.127', 'SPINA'),
            ('64.127', 'ALLOWANCE'),
            ('64.033', 'HOMELESS'),
            ('64.033', 'SUPPORT'),
            ('64.024', 'HOMELESS'),
            ('64.024', 'GRANT'),
            ('64.053', 'NURS'),
            ('64.053', 'HOME'),
            ('64.056', 'LEGAL'),
            ('64.037', 'PARALYMP'),
            ('64.037', 'ALLOWANCE'),
            ('64.034', 'SPORT'),
            ('64.034', 'ADAPT')
    ) AS t(cfda_number, search_term)
),

hits AS (
    SELECT DISTINCT
        t.cfda_number,
        t.search_term,
        e.fiscal_year,
        e.source_category_name,
        c.category_code,
        c.category_name,
        c.aggregation_role
    FROM program_terms AS t
    CROSS JOIN va.gdx_county_expenditure AS e
    JOIN va.gdx_expenditure_category AS c
      ON c.gdx_category_id = e.gdx_category_id
    WHERE e.fiscal_year BETWEEN 2020 AND 2024
      AND (
             UPPER(COALESCE(e.source_category_name, ''))
                 LIKE '%' || t.search_term || '%'
          OR UPPER(COALESCE(c.category_name, ''))
                 LIKE '%' || t.search_term || '%'
      )
)

SELECT *
FROM hits
ORDER BY
    cfda_number,
    search_term,
    fiscal_year,
    category_code;


/* ============================================================================
   SECTION 12
   REVIEW-FAMILY MATERIALITY
   ========================================================================== */

\echo ''
\echo 'SECTION 12 - REVIEW-FAMILY MATERIALITY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    r.review_family,
    COUNT(DISTINCT r.cfda_number) AS program_count,
    COUNT(*) AS transaction_count,
    ROUND(SUM(l.federal_action_obligation), 2)
        AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN l.is_covid
                    THEN l.federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        100.0 * SUM(l.federal_action_obligation)
        / 908773543.31::numeric,
        2
    ) AS percent_of_class_b
FROM va_5n4_review_programs AS r
JOIN analysis.v_certified_assistance_ledger AS l
  ON l.cfda_number = r.cfda_number
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
GROUP BY r.review_family
ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 13
   MATERIALITY CONCENTRATION
   ========================================================================== */

\echo ''
\echo 'SECTION 13 - CLASS B MATERIALITY CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH p AS (
    SELECT
        l.cfda_number,
        MAX(l.cfda_title) AS cfda_title,
        SUM(l.federal_action_obligation) AS obligation_dollars
    FROM analysis.v_certified_assistance_ledger AS l
    JOIN va_5n4_review_programs AS r
      ON r.cfda_number = l.cfda_number
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
    GROUP BY l.cfda_number
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            ORDER BY obligation_dollars DESC
        ) AS materiality_rank
    FROM p
)

SELECT
    COUNT(*) AS program_count,
    ROUND(SUM(obligation_dollars), 2)
        AS class_b_total,

    ROUND(
        SUM(obligation_dollars)
            FILTER (WHERE materiality_rank <= 3),
        2
    ) AS top_3_dollars,

    ROUND(
        100.0
        * SUM(obligation_dollars)
            FILTER (WHERE materiality_rank <= 3)
        / SUM(obligation_dollars),
        2
    ) AS top_3_percent,

    ROUND(
        SUM(obligation_dollars)
            FILTER (WHERE materiality_rank <= 5),
        2
    ) AS top_5_dollars,

    ROUND(
        100.0
        * SUM(obligation_dollars)
            FILTER (WHERE materiality_rank <= 5)
        / SUM(obligation_dollars),
        2
    ) AS top_5_percent

FROM ranked;


/* ============================================================================
   SECTION 14
   HARD ASSERTIONS
   ========================================================================== */

\echo ''
\echo 'SECTION 14 - HARD ASSERTIONS'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_program_count bigint;
    v_amount numeric;
    v_covid numeric;
BEGIN

    SELECT
        COUNT(DISTINCT l.cfda_number),
        ROUND(SUM(l.federal_action_obligation), 2),
        ROUND(
            SUM(
                CASE
                    WHEN l.is_covid
                        THEN l.federal_action_obligation
                    ELSE 0
                END
            ),
            2
        )
    INTO
        v_program_count,
        v_amount,
        v_covid
    FROM analysis.v_certified_assistance_ledger AS l
    JOIN va_5n4_review_programs AS r
      ON r.cfda_number = l.cfda_number
    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;

    IF v_program_count <> 18 THEN
        RAISE EXCEPTION
            'Expected 18 final-review programs; found %',
            v_program_count;
    END IF;

    IF v_amount <> 908773543.31::numeric THEN
        RAISE EXCEPTION
            'Expected Class B control 908773543.31; found %',
            v_amount;
    END IF;

    IF v_covid <> 293054380.66::numeric THEN
        RAISE EXCEPTION
            'Expected Class B COVID control 293054380.66; found %',
            v_covid;
    END IF;

    IF (
        SELECT COUNT(*)
        FROM va_5n4_hypothesis
    ) <> 18 THEN
        RAISE EXCEPTION
            'Expected 18 explicit review hypotheses';
    END IF;

    RAISE NOTICE
        'PASS: 18-program Class B universe reproduced - $908,773,543.31 total; $293,054,380.66 COVID';

END
$$;


/* ============================================================================
   SECTION 15
   COMPLETION MARKER
   ========================================================================== */

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N-4 PROFILE COMPLETE - FINAL VA REVIEW EVIDENCE - NO DB WRITES'
\echo '===================================================================================================='