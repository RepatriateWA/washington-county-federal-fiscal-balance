/*
================================================================================
MIGRATION 183
SEED EDUCATION ASSISTANCE ACCOUNTING POLICY
================================================================================

ETL branch
----------
ETL-174B-5X

Methodology version
-------------------
ANALYSIS-174B-5X-v1

Purpose
-------
Persist accounting policy for four high-materiality Washington education
assistance programs after successful completion of:

    ETL-174B-5X
    ETL-174B-5X-1
    ETL-174B-5X-2

Programs
--------
84.425  Education Stabilization Fund
84.063  Federal Pell Grant Program
84.010  Title I Grants to Local Educational Agencies
84.027  Special Education Grants to States

Accounting conclusion
---------------------
All four programs are genuine federal economic inflows to Washington and are
not represented by the authoritative SSA, CMS, VA, or federal-compensation
ledger streams.

Disposition:
    INCLUDE_ADDITIVE

Accounting measure:
    NET_FEDERAL_ACTION_OBLIGATION

Preferred source:
    USASPENDING_ASSISTANCE

Funding agency:
    PROVENANCE ONLY.

Program identity determines the economic assistance function. The complete
Assistance Listing population is included regardless of whether the funding
agency is the Department of Education or Department of the Interior.

COVID / extraordinary funding:
    PROVENANCE ONLY.

COVID status does not change accounting disposition. COVID-tagged additive
education assistance remains INCLUDE_ADDITIVE and is separately identifiable
for ordinary / COVID-inclusive / COVID-excluded reporting.

Certified pre-migration focal controls
--------------------------------------
Transactions       28,900
Programs                 4
Awards                1,316
Recipients              149

Net obligations:
    $9,035,419,332.15

COVID:
    $4,474,035,816.00

IIJA:
    $0.00

Extraordinary:
    $4,474,035,816.00

Program controls:
    84.425  $4,400,028,954.00
    84.063  $1,812,084,197.25
    84.010  $1,472,272,408.06
    84.027  $1,351,033,772.84

Funding-agency provenance:
    Department of Education     $8,953,191,721.52
    Department of the Interior     $82,227,610.63
                                ------------------
    Full population             $9,035,419,332.15

Expected post-migration assistance bridge effect
------------------------------------------------
Prior INCLUDE_ADDITIVE:
    $42,461,687,570.89

Education increment:
     $9,035,419,332.15

Expected INCLUDE_ADDITIVE:
    $51,497,106,903.04

Prior UNCLASSIFIED_REVIEW:
    $70,539,463,376.71

Education decrement:
     $9,035,419,332.15

Expected UNCLASSIFIED_REVIEW:
    $61,504,044,044.56

Migration behavior
------------------
FAIL CLOSED.

The migration:
1. verifies the certified source population;
2. verifies the four programs remain unresolved;
3. refuses to overwrite existing program classifications or mappings;
4. inserts four source policies;
5. inserts four program classifications;
6. inserts four program-policy mappings;
7. reconstructs the effective assistance disposition;
8. verifies exact post-migration controls;
9. commits only if all controls pass.

================================================================================
*/

BEGIN;

\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 183 - EDUCATION ASSISTANCE ACCOUNTING POLICY'
\echo '===================================================================================================='
\echo 'Methodology: ANALYSIS-174B-5X-v1'
\echo ''


-- ================================================================================================
-- 1. MATERIALIZE CERTIFIED WA ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.m183_ledger;

CREATE TEMP TABLE m183_ledger AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year,
    federal_action_obligation,
    cfda_number,
    cfda_title,
    award_id_fain,
    award_id_uri,
    recipient_name,
    funding_agency_name,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;

CREATE INDEX ON m183_ledger (cfda_number);
CREATE INDEX ON m183_ledger (source_award_identifier);
CREATE INDEX ON m183_ledger (action_date_fiscal_year);


-- ================================================================================================
-- 2. CERTIFIED FOUR-PROGRAM SOURCE CONTROL
--
-- IMPORTANT:
-- No funding-agency restriction.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.m183_focal;

CREATE TEMP TABLE m183_focal AS
SELECT *
FROM m183_ledger
WHERE cfda_number IN (
    '84.425',
    '84.063',
    '84.010',
    '84.027'
);


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION FOUR-PROGRAM SOURCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m183_focal;


DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_awards       bigint;
    v_recipients   bigint;
    v_total        numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COUNT(DISTINCT source_award_identifier),
        COUNT(DISTINCT recipient_name),

        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

        COALESCE(
            SUM(
                CASE WHEN is_covid
                     THEN federal_action_obligation ELSE 0 END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE WHEN is_iija
                     THEN federal_action_obligation ELSE 0 END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE WHEN is_extraordinary
                     THEN federal_action_obligation ELSE 0 END
            ),
            0
        )

    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_recipients,
        v_total,
        v_covid,
        v_iija,
        v_extra

    FROM m183_focal;

    IF v_transactions <> 28900
       OR v_programs <> 4
       OR v_awards <> 1316
       OR v_recipients <> 149
       OR ABS(v_total - 9035419332.15::numeric) > 0.01
       OR ABS(v_covid - 4474035816.00::numeric) > 0.01
       OR ABS(v_iija - 0::numeric) > 0.01
       OR ABS(v_extra - 4474035816.00::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'M183 SOURCE CONTROL FAILED: tx=% programs=% awards=% recipients=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_awards,
            v_recipients,
            v_total,
            v_covid,
            v_iija,
            v_extra;
    END IF;

    RAISE NOTICE
        'M183 SOURCE CONTROL PASS: total=% COVID=%',
        v_total,
        v_covid;
END
$$;


-- ================================================================================================
-- 3. INDIVIDUAL PROGRAM CONTROLS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. INDIVIDUAL PROGRAM CONTROLS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount

FROM m183_focal

GROUP BY cfda_number

ORDER BY cfda_number;


DO $$
DECLARE
    v_84010 numeric;
    v_84027 numeric;
    v_84063 numeric;
    v_84425 numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (WHERE cfda_number = '84.010'),
            0
        ),
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (WHERE cfda_number = '84.027'),
            0
        ),
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (WHERE cfda_number = '84.063'),
            0
        ),
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (WHERE cfda_number = '84.425'),
            0
        )

    INTO
        v_84010,
        v_84027,
        v_84063,
        v_84425

    FROM m183_focal;

    IF ABS(v_84010 - 1472272408.06::numeric) > 0.01
       OR ABS(v_84027 - 1351033772.84::numeric) > 0.01
       OR ABS(v_84063 - 1812084197.25::numeric) > 0.01
       OR ABS(v_84425 - 4400028954.00::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'M183 PROGRAM CONTROL FAILED: 84.010=% 84.027=% 84.063=% 84.425=%',
            v_84010,
            v_84027,
            v_84063,
            v_84425;
    END IF;

    RAISE NOTICE
        'M183 INDIVIDUAL PROGRAM CONTROLS PASS';
END
$$;


-- ================================================================================================
-- 4. FUNDING-AGENCY PROVENANCE CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FUNDING-AGENCY PROVENANCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    funding_agency_name,
    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM m183_focal

GROUP BY funding_agency_name

ORDER BY SUM(federal_action_obligation) DESC;


DO $$
DECLARE
    v_education numeric;
    v_interior  numeric;
    v_other     numeric;
    v_total     numeric;
    v_closure   numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name =
                      'Department of Education'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name =
                      'Department of the Interior'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name NOT IN (
                    'Department of Education',
                    'Department of the Interior'
                )
                   OR funding_agency_name IS NULL
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_education,
        v_interior,
        v_other,
        v_total

    FROM m183_focal;

    v_closure :=
        v_total
        - v_education
        - v_interior
        - v_other;

    IF ABS(v_education - 8953191721.52::numeric) > 0.01
       OR ABS(v_interior - 82227610.63::numeric) > 0.01
       OR ABS(v_other) > 0.01
       OR ABS(v_closure) > 0.01
    THEN
        RAISE EXCEPTION
            'M183 FUNDING-AGENCY CONTROL FAILED: Education=% Interior=% other=% total=% closure=%',
            v_education,
            v_interior,
            v_other,
            v_total,
            v_closure;
    END IF;

    RAISE NOTICE
        'M183 FUNDING-AGENCY CONTROL PASS: Education=% Interior=% closure=%',
        v_education,
        v_interior,
        v_closure;
END
$$;


-- ================================================================================================
-- 5. FAIL-CLOSED EXISTING-STATE GUARDS
--
-- Migration 183 is intentionally one-time. It must not silently overwrite,
-- supersede, or duplicate an existing classification or mapping.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. EXISTING-STATE GUARDS'
\echo '----------------------------------------------------------------------------------------------------'


DO $$
DECLARE
    v_program_classifications bigint;
    v_award_classifications   bigint;
    v_program_mappings        bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_program_classifications
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
          '84.425',
          '84.063',
          '84.010',
          '84.027'
      );

    SELECT COUNT(*)
    INTO v_award_classifications
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
          '84.425',
          '84.063',
          '84.010',
          '84.027'
      );

    SELECT COUNT(*)
    INTO v_program_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
          '84.425',
          '84.063',
          '84.010',
          '84.027'
      );

    IF v_program_classifications <> 0
       OR v_award_classifications <> 0
       OR v_program_mappings <> 0
    THEN
        RAISE EXCEPTION
            'M183 EXISTING-STATE GUARD FAILED: program_classifications=% award_classifications=% mappings=%',
            v_program_classifications,
            v_award_classifications,
            v_program_mappings;
    END IF;

    RAISE NOTICE
        'M183 EXISTING-STATE GUARD PASS: no prior focal classifications or mappings';
END
$$;


-- ================================================================================================
-- 6. INSERT SOURCE POLICIES
--
-- One source-policy row per economic subfamily. Program-policy mapping then
-- connects each Assistance Listing to its policy.
--
-- IMPORTANT:
-- federal_inflow_source_policy has no composite unique constraint.
-- Do NOT use composite ON CONFLICT here.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. INSERT SOURCE POLICIES'
\echo '----------------------------------------------------------------------------------------------------'


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
    'EDUCATION_ASSISTANCE',
    'EDUCATION_STABILIZATION',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'Education Stabilization Fund (84.425) is represented by the complete Washington USAspending Assistance Listing population. ETL-174B-5X-2 found no overlap with authoritative SSA, CMS, VA, or federal-compensation ledger streams. Funding agency is provenance only. COVID and extraordinary classifications are separate provenance dimensions and do not alter additive accounting disposition.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
),
(
    'EDUCATION_ASSISTANCE',
    'STUDENT_FINANCIAL_AID',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'Federal Pell Grant Program (84.063) is represented by Washington USAspending net federal action obligations. ETL-174B-5X-2 supports treatment as additive federal student financial assistance not represented in authoritative SSA, CMS, VA, or federal-compensation ledger streams.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
),
(
    'EDUCATION_ASSISTANCE',
    'TITLE_I',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'Title I Grants to Local Educational Agencies (84.010) use the complete Washington Assistance Listing population. ETL-174B-5X-1 established that Department of the Interior-administered tribal education awards remain part of the Title I economic program population; funding agency is retained as provenance rather than used as an accounting restriction.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
),
(
    'EDUCATION_ASSISTANCE',
    'SPECIAL_EDUCATION',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE',
    ARRAY[]::text[],
    'INCLUDE',
    'Special Education Grants to States (84.027) use the complete Washington Assistance Listing population. ETL-174B-5X-1 established that Department of the Interior-administered tribal education awards remain part of the special-education economic program population; funding agency is retained as provenance rather than used as an accounting restriction.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
);


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-174B-5X-v1'
      AND inflow_family = 'EDUCATION_ASSISTANCE'
      AND inflow_subfamily IN (
          'EDUCATION_STABILIZATION',
          'STUDENT_FINANCIAL_AID',
          'TITLE_I',
          'SPECIAL_EDUCATION'
      );

    IF v_count <> 4 THEN
        RAISE EXCEPTION
            'M183 SOURCE POLICY INSERT FAILED: expected 4 rows, found %',
            v_count;
    END IF;

    RAISE NOTICE
        'M183 SOURCE POLICY INSERT PASS: 4 policies';
END
$$;

-- ================================================================================================
-- 7. INSERT PROGRAM CLASSIFICATIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. INSERT PROGRAM CLASSIFICATIONS'
\echo '----------------------------------------------------------------------------------------------------'


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
    '84.425',
    'Education Stabilization Fund',
    'EDUCATION_ASSISTANCE',
    'EDUCATION_STABILIZATION',
    'NONE',
    TRUE,
    TRUE,
    'ETL-174B-5X-2 certified the full Assistance Listing population. Emergency education stabilization assistance is additive to authoritative SSA, CMS, VA, and federal-compensation streams. COVID and extraordinary status remain separate provenance dimensions.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '84.063',
    'Federal Pell Grant Program',
    'EDUCATION_ASSISTANCE',
    'STUDENT_FINANCIAL_AID',
    'NONE',
    FALSE,
    FALSE,
    'ETL-174B-5X-2 certified the full Assistance Listing population. Pell grants represent additive student financial assistance and are not represented in authoritative SSA, CMS, VA, or federal-compensation streams.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '84.010',
    'Title I Grants to Local Educational Agencies',
    'EDUCATION_ASSISTANCE',
    'TITLE_I',
    'NONE',
    TRUE,
    TRUE,
    'ETL-174B-5X-1 and ETL-174B-5X-2 certified the full Assistance Listing population. Funding agency is provenance; Department of the Interior-administered tribal education awards remain within the Title I economic program population.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
),
(
    'USASPENDING_ASSISTANCE',
    '84.027',
    'Special Education Grants to States',
    'EDUCATION_ASSISTANCE',
    'SPECIAL_EDUCATION',
    'NONE',
    TRUE,
    TRUE,
    'ETL-174B-5X-1 and ETL-174B-5X-2 certified the full Assistance Listing population. Funding agency is provenance; Department of the Interior-administered tribal education awards remain within the special-education economic program population.',
    'ANALYSIS-174B-5X-v1',
    2020,
    2024
);


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-174B-5X-v1'
      AND source_program_code IN (
          '84.425',
          '84.063',
          '84.010',
          '84.027'
      );

    IF v_count <> 4 THEN
        RAISE EXCEPTION
            'M183 PROGRAM CLASSIFICATION INSERT FAILED: expected 4 rows, found %',
            v_count;
    END IF;

    RAISE NOTICE
        'M183 PROGRAM CLASSIFICATION INSERT PASS: 4 classifications';
END
$$;


-- ================================================================================================
-- 8. INSERT PROGRAM-POLICY MAPPINGS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. INSERT PROGRAM-POLICY MAPPINGS'
\echo '----------------------------------------------------------------------------------------------------'


INSERT INTO reference.federal_inflow_program_policy_mapping (
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    'USASPENDING_ASSISTANCE',
    x.source_program_code,
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    x.mapping_basis,
    'ANALYSIS-174B-5X-v1',
    2020,
    2024

FROM (
    VALUES
        (
            '84.425',
            'ETL-174B-5X-2 certified Education Stabilization Fund as additive education assistance. Full Assistance Listing population included; COVID retained as provenance.'
        ),
        (
            '84.063',
            'ETL-174B-5X-2 certified Federal Pell Grant Program as additive student financial assistance.'
        ),
        (
            '84.010',
            'ETL-174B-5X-1/5X-2 certified full Title I Assistance Listing population as additive, including Interior-administered tribal education awards.'
        ),
        (
            '84.027',
            'ETL-174B-5X-1/5X-2 certified full IDEA/special-education Assistance Listing population as additive, including Interior-administered tribal education awards.'
        )
) AS x (
    source_program_code,
    mapping_basis
)

JOIN reference.federal_inflow_source_policy p
  ON p.methodology_version = 'ANALYSIS-174B-5X-v1'
 AND p.inflow_family = 'EDUCATION_ASSISTANCE'
 AND p.inflow_subfamily =
     CASE x.source_program_code
         WHEN '84.425' THEN 'EDUCATION_STABILIZATION'
         WHEN '84.063' THEN 'STUDENT_FINANCIAL_AID'
         WHEN '84.010' THEN 'TITLE_I'
         WHEN '84.027' THEN 'SPECIAL_EDUCATION'
     END;


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-174B-5X-v1'
      AND source_program_code IN (
          '84.425',
          '84.063',
          '84.010',
          '84.027'
      )
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';

    IF v_count <> 4 THEN
        RAISE EXCEPTION
            'M183 PROGRAM MAPPING INSERT FAILED: expected 4 INCLUDE_ADDITIVE rows, found %',
            v_count;
    END IF;

    RAISE NOTICE
        'M183 PROGRAM MAPPING INSERT PASS: 4 mappings';
END
$$;


-- ================================================================================================
-- 9. RECONSTRUCT POST-MIGRATION EFFECTIVE DISPOSITION
--
-- Award classification has precedence over program mapping.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.m183_award_matches;

CREATE TEMP TABLE m183_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM m183_ledger l

JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = l.cfda_number
 AND a.source_award_identifier = l.source_award_identifier
 AND (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= a.valid_from_fiscal_year
     )
 AND (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= a.valid_through_fiscal_year
     );


DROP TABLE IF EXISTS pg_temp.m183_program_matches;

CREATE TEMP TABLE m183_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM m183_ledger l

JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = l.cfda_number
 AND (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= m.valid_from_fiscal_year
     )
 AND (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= m.valid_through_fiscal_year
     );


DO $$
DECLARE
    v_award_duplicates   bigint;
    v_program_duplicates bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_award_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM m183_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    SELECT COUNT(*)
    INTO v_program_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM m183_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    IF v_award_duplicates <> 0
       OR v_program_duplicates <> 0
    THEN
        RAISE EXCEPTION
            'M183 POST-MIGRATION RESOLUTION UNIQUENESS FAILED: award_duplicates=% program_duplicates=%',
            v_award_duplicates,
            v_program_duplicates;
    END IF;

    RAISE NOTICE
        'M183 POST-MIGRATION RESOLUTION UNIQUENESS PASS';
END
$$;


DROP TABLE IF EXISTS pg_temp.m183_resolved;

CREATE TEMP TABLE m183_resolved AS
SELECT
    l.*,

    CASE
        WHEN a.assistance_transaction_id IS NOT NULL
            THEN 'AWARD'
        WHEN p.assistance_transaction_id IS NOT NULL
            THEN 'PROGRAM'
        ELSE 'UNCLASSIFIED'
    END AS resolution_level,

    COALESCE(
        a.accounting_disposition,
        p.resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_accounting_disposition

FROM m183_ledger l

LEFT JOIN m183_award_matches a
  ON a.assistance_transaction_id =
     l.assistance_transaction_id

LEFT JOIN m183_program_matches p
  ON p.assistance_transaction_id =
     l.assistance_transaction_id;


-- ================================================================================================
-- 10. POST-MIGRATION FOCAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. POST-MIGRATION FOCAL DISPOSITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount

FROM m183_resolved

WHERE cfda_number IN (
    '84.425',
    '84.063',
    '84.010',
    '84.027'
)

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


DO $$
DECLARE
    v_include       numeric;
    v_unclassified numeric;
    v_other         numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'UNCLASSIFIED_REVIEW'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition NOT IN (
                    'INCLUDE_ADDITIVE',
                    'UNCLASSIFIED_REVIEW'
                )
            ),
            0
        )

    INTO
        v_include,
        v_unclassified,
        v_other

    FROM m183_resolved

    WHERE cfda_number IN (
        '84.425',
        '84.063',
        '84.010',
        '84.027'
    );

    IF ABS(v_include - 9035419332.15::numeric) > 0.01
       OR ABS(v_unclassified) > 0.01
       OR ABS(v_other) > 0.01
    THEN
        RAISE EXCEPTION
            'M183 FOCAL POST-MIGRATION CONTROL FAILED: include=% unclassified=% other=%',
            v_include,
            v_unclassified,
            v_other;
    END IF;

    RAISE NOTICE
        'M183 FOCAL POST-MIGRATION CONTROL PASS: INCLUDE_ADDITIVE=%',
        v_include;
END
$$;


-- ================================================================================================
-- 11. FULL POST-MIGRATION ASSISTANCE BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. FULL POST-MIGRATION ASSISTANCE BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m183_resolved

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


DO $$
DECLARE
    v_gross         numeric;
    v_exclude       numeric;
    v_include       numeric;
    v_reference     numeric;
    v_withhold      numeric;
    v_unclassified numeric;
    v_closure       numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'EXCLUDE_DUPLICATE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'REFERENCE_ONLY'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'WITHHOLD_UNRESOLVED'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'UNCLASSIFIED_REVIEW'
            ),
            0
        )

    INTO
        v_gross,
        v_exclude,
        v_include,
        v_reference,
        v_withhold,
        v_unclassified

    FROM m183_resolved;

    v_closure :=
        v_gross
        - v_exclude
        - v_include
        - v_reference
        - v_withhold
        - v_unclassified;

    IF ABS(v_gross - 348524407674.34::numeric) > 0.01
       OR ABS(v_exclude - 234974673851.81::numeric) > 0.01
       OR ABS(v_include - 51497106903.04::numeric) > 0.01
       OR ABS(v_reference - 7799088.00::numeric) > 0.01
       OR ABS(v_withhold - 540783786.93::numeric) > 0.01
       OR ABS(v_unclassified - 61504044044.56::numeric) > 0.01
       OR ABS(v_closure) > 0.01
    THEN
        RAISE EXCEPTION
            'M183 FULL BRIDGE CONTROL FAILED: gross=% exclude=% include=% reference=% withhold=% unclassified=% closure=%',
            v_gross,
            v_exclude,
            v_include,
            v_reference,
            v_withhold,
            v_unclassified,
            v_closure;
    END IF;

    RAISE NOTICE
        'M183 FULL BRIDGE CONTROL PASS: gross=% include=% unclassified=% closure=%',
        v_gross,
        v_include,
        v_unclassified,
        v_closure;
END
$$;


-- ================================================================================================
-- 12. POST-MIGRATION ANNUAL EDUCATION CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. EDUCATION ADDITIVE AMOUNT BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS additive_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m183_resolved

WHERE cfda_number IN (
    '84.425',
    '84.063',
    '84.010',
    '84.027'
)
  AND effective_accounting_disposition =
      'INCLUDE_ADDITIVE'

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 13. FINAL PERSISTED-STATE CERTIFICATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. FINAL PERSISTED-STATE CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'


DO $$
DECLARE
    v_policies        bigint;
    v_classifications bigint;
    v_mappings        bigint;
    v_include         numeric;
    v_unclassified    numeric;
BEGIN
    SELECT COUNT(*)
    INTO v_policies
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version =
          'ANALYSIS-174B-5X-v1'
      AND inflow_family =
          'EDUCATION_ASSISTANCE';

    SELECT COUNT(*)
    INTO v_classifications
    FROM reference.federal_inflow_program_classification
    WHERE source_system =
          'USASPENDING_ASSISTANCE'
      AND methodology_version =
          'ANALYSIS-174B-5X-v1'
      AND source_program_code IN (
          '84.425',
          '84.063',
          '84.010',
          '84.027'
      );

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system =
          'USASPENDING_ASSISTANCE'
      AND methodology_version =
          'ANALYSIS-174B-5X-v1'
      AND source_program_code IN (
          '84.425',
          '84.063',
          '84.010',
          '84.027'
      )
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';

    SELECT
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'UNCLASSIFIED_REVIEW'
            ),
            0
        )

    INTO
        v_include,
        v_unclassified

    FROM m183_resolved;

    IF v_policies <> 4
       OR v_classifications <> 4
       OR v_mappings <> 4
       OR ABS(v_include - 51497106903.04::numeric) > 0.01
       OR ABS(v_unclassified - 61504044044.56::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'M183 FINAL CERTIFICATION FAILED: policies=% classifications=% mappings=% include=% unclassified=%',
            v_policies,
            v_classifications,
            v_mappings,
            v_include,
            v_unclassified;
    END IF;

    RAISE NOTICE
        'M183 FINAL CERTIFICATION PASS: policies=4 classifications=4 mappings=4 INCLUDE_ADDITIVE=% UNCLASSIFIED_REVIEW=%',
        v_include,
        v_unclassified;
END
$$;


COMMIT;


\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 183 COMPLETE'
\echo '===================================================================================================='
\echo 'ANALYSIS-174B-5X-v1'
\echo 'EDUCATION ASSISTANCE POLICY COMMITTED'