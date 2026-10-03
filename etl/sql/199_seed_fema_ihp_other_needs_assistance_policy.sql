/*
====================================================================================================
ETL-199
SEED FEMA IHP OTHER NEEDS ASSISTANCE ACCOUNTING POLICY

Assistance Listing:
    97.050 - Presidential Declared Disaster Assistance to Individuals and
             Households - Other Needs

Accounting decision:
    DISASTER_ASSISTANCE / FEMA_IHP_OTHER_NEEDS_ASSISTANCE

    accounting_measure               NET_FEDERAL_ACTION_OBLIGATION
    preferred_source                 USASPENDING_ASSISTANCE
    allocation_source                UNRESOLVED
    overlapping_sources              {}
    ledger_treatment                 INCLUDE
    overlap_risk                     NONE
    covid_relevance                  TRUE
    extraordinary_relevance          TRUE
    resolved_accounting_disposition  INCLUDE_ADDITIVE
    methodology_version              ANALYSIS-199-v1

Certified FY2020-FY2024 control:
    Transactions                     15
    Awards                            2
    Recipients                        2
    Net obligation        $731,476,459.87
    Positive obligations  $968,744,214.00
    Negative adjustments -$237,267,754.13
    COVID                 $731,476,459.87
    IIJA                             $0.00
    Extraordinary         $731,476,459.87

Award-level evidence:
    4481LOSTWAGESBENEFIT  $730,597,303.13
    4481LOSTWAGESADMIN        $879,156.74

Accounting interpretation:
    AL 97.050 represents a FEMA Individual and Household Program / Other Needs
    Assistance stream. ETL-198A found no focal award identifier cross-listed
    under another Assistance Listing and specifically no award-ID collision
    with AL 97.036 FEMA Public Assistance.

    FEMA agency identity, disaster provenance, or COVID provenance does not
    itself make distinct FEMA Assistance Listings duplicate dollars.

Double-count prohibitions:
    1. AL 97.050 is distinct from AL 97.036 FEMA Public Assistance and is not
       excluded merely because both arise from FEMA/disaster activity.

    2. Downstream state unemployment/lost-wage benefit payments or other
       disbursements financed from these FEMA transfers are uses of this
       federal transfer and MUST NOT be counted as a second federal inflow.

    3. COVID and extraordinary status are provenance/reporting dimensions,
       not additional additive accounting paths.

Fiscal-year rule:
    Transaction action-date fiscal year controls ledger assignment.

    Later deobligations remain in their actual action-date fiscal years and
    are not reassigned to FY2020 merely because the underlying Lost Wages
    awards originated in FY2020.

County incidence:
    UNRESOLVED.

    Administrative recipient geography does not establish beneficiary or
    economic-incidence geography.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-199'
\echo 'SEED FEMA IHP OTHER NEEDS ASSISTANCE ACCOUNTING POLICY'
\echo 'AL 97.050'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD CERTIFIED FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m199_focal;

CREATE TEMP TABLE m199_focal AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '97.050';


ANALYZE m199_focal;


/*
====================================================================================================
2. EXACT PRE-MIGRATION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. EXACT PRE-MIGRATION CONTROL'
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

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

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

FROM m199_focal;


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

    FROM m199_focal;


    IF v_tx <> 15
       OR v_awards <> 2
       OR v_recip <> 2
       OR ROUND(v_amount, 2) <> 731476459.87
       OR ROUND(v_covid, 2) <> 731476459.87
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 731476459.87
    THEN
        RAISE EXCEPTION
            'ETL-199 EXACT PRE-CONTROL FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-199 EXACT PRE-CONTROL PASS';

END
$$;


/*
====================================================================================================
3. TRANSACTION-SIGN CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. TRANSACTION-SIGN CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    CASE
        WHEN federal_action_obligation > 0 THEN 'POSITIVE'
        WHEN federal_action_obligation < 0 THEN 'NEGATIVE'
        ELSE 'ZERO'
    END AS obligation_sign,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m199_focal

GROUP BY 1
ORDER BY 1;


DO $$
DECLARE
    v_positive numeric;
    v_negative numeric;
    v_net      numeric;
BEGIN

    SELECT
        COALESCE(SUM(
            CASE WHEN federal_action_obligation > 0
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN federal_action_obligation < 0
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_positive,
        v_negative,
        v_net

    FROM m199_focal;


    IF ROUND(v_positive, 2) <> 968744214.00
       OR ROUND(v_negative, 2) <> -237267754.13
       OR ROUND(v_net, 2) <> 731476459.87
    THEN
        RAISE EXCEPTION
            'ETL-199 SIGN CONTROL FAILED: positive=% negative=% net=%',
            ROUND(v_positive, 2),
            ROUND(v_negative, 2),
            ROUND(v_net, 2);
    END IF;


    RAISE NOTICE
        'ETL-199 TRANSACTION-SIGN CONTROL PASS';

END
$$;


/*
====================================================================================================
4. FISCAL-YEAR CONTROL

Preserve later deobligations in their action-date fiscal years.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FISCAL-YEAR CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m199_focal

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


DO $$
DECLARE
    v_bad bigint;
BEGIN

    WITH expected
    (
        fiscal_year,
        transaction_count,
        net_obligation
    ) AS
    (
        VALUES
            (2020, 9::bigint,  968744214.00::numeric),
            (2021, 2::bigint, -220000000.00::numeric),
            (2022, 1::bigint,   -5000000.00::numeric),
            (2023, 1::bigint,   -4081996.87::numeric),
            (2024, 2::bigint,   -8185757.26::numeric)
    ),

    actual AS
    (
        SELECT
            action_date_fiscal_year AS fiscal_year,
            COUNT(*) AS transaction_count,
            ROUND(
                SUM(federal_action_obligation)::numeric,
                2
            ) AS net_obligation

        FROM m199_focal

        GROUP BY action_date_fiscal_year
    ),

    differences AS
    (
        SELECT
            COALESCE(e.fiscal_year, a.fiscal_year)
                AS fiscal_year

        FROM expected e

        FULL OUTER JOIN actual a
          ON a.fiscal_year = e.fiscal_year

        WHERE e.fiscal_year IS NULL
           OR a.fiscal_year IS NULL
           OR e.transaction_count <> a.transaction_count
           OR e.net_obligation <> a.net_obligation
    )

    SELECT COUNT(*)
    INTO v_bad
    FROM differences;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 FISCAL-YEAR CONTROL FAILED: mismatched fiscal years=%',
            v_bad;
    END IF;


    RAISE NOTICE
        'ETL-199 FISCAL-YEAR CONTROL PASS';

END
$$;


/*
====================================================================================================
5. AWARD-ID DOUBLE-COUNT GUARD

Re-run the strongest internal collision test inside the write migration.

No focal AL 97.050 award identifier may occur under another Assistance Listing
in the certified WA FY2020-FY2024 assistance universe.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. AWARD-ID DOUBLE-COUNT GUARD'
\echo '----------------------------------------------------------------------------------------------------'

WITH focal_awards AS
(
    SELECT DISTINCT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier

    FROM m199_focal

    WHERE COALESCE(
              NULLIF(award_id_fain, ''),
              NULLIF(award_id_uri, '')
          ) IS NOT NULL
)

SELECT
    f.award_identifier,
    l.cfda_number AS other_assistance_listing,
    MIN(l.cfda_title) AS other_program_title,
    COUNT(*) AS transaction_count,
    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM focal_awards f

JOIN analysis.v_certified_assistance_ledger l
  ON f.award_identifier =
     COALESCE(
         NULLIF(l.award_id_fain, ''),
         NULLIF(l.award_id_uri, '')
     )

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number <> '97.050'

GROUP BY
    f.award_identifier,
    l.cfda_number

ORDER BY
    f.award_identifier,
    l.cfda_number;


DO $$
DECLARE
    v_cross_listed bigint;
    v_public_assistance_collision bigint;
BEGIN

    WITH focal_awards AS
    (
        SELECT DISTINCT
            COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            ) AS award_identifier

        FROM m199_focal

        WHERE COALESCE(
                  NULLIF(award_id_fain, ''),
                  NULLIF(award_id_uri, '')
              ) IS NOT NULL
    )

    SELECT COUNT(*)
    INTO v_cross_listed

    FROM focal_awards f

    JOIN analysis.v_certified_assistance_ledger l
      ON f.award_identifier =
         COALESCE(
             NULLIF(l.award_id_fain, ''),
             NULLIF(l.award_id_uri, '')
         )

    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number <> '97.050';


    WITH focal_awards AS
    (
        SELECT DISTINCT
            COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            ) AS award_identifier

        FROM m199_focal

        WHERE COALESCE(
                  NULLIF(award_id_fain, ''),
                  NULLIF(award_id_uri, '')
              ) IS NOT NULL
    )

    SELECT COUNT(*)
    INTO v_public_assistance_collision

    FROM focal_awards f

    JOIN analysis.v_certified_assistance_ledger l
      ON f.award_identifier =
         COALESCE(
             NULLIF(l.award_id_fain, ''),
             NULLIF(l.award_id_uri, '')
         )

    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number = '97.036';


    IF v_cross_listed <> 0
       OR v_public_assistance_collision <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 AWARD-ID DOUBLE-COUNT GUARD FAILED: cross-listed rows=% 97.036 collisions=%',
            v_cross_listed,
            v_public_assistance_collision;
    END IF;


    RAISE NOTICE
        'ETL-199 AWARD-ID DOUBLE-COUNT GUARD PASS';

END
$$;


/*
====================================================================================================
6. PRE-EXISTING PROGRAM CLASSIFICATION / MAPPING GUARD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. PRE-EXISTING PROGRAM CLASSIFICATION / MAPPING GUARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    inflow_family,
    inflow_subfamily,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '97.050'
  AND valid_from_fiscal_year <= 2024
  AND (
        valid_through_fiscal_year IS NULL
        OR valid_through_fiscal_year >= 2020
      );


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '97.050'
  AND valid_from_fiscal_year <= 2024
  AND (
        valid_through_fiscal_year IS NULL
        OR valid_through_fiscal_year >= 2020
      );


DO $$
DECLARE
    v_classification_count bigint;
    v_mapping_count        bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_classification_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '97.050'
      AND valid_from_fiscal_year <= 2024
      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          );


    SELECT COUNT(*)
    INTO v_mapping_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '97.050'
      AND valid_from_fiscal_year <= 2024
      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          );


    IF v_classification_count <> 0
       OR v_mapping_count <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 PRE-EXISTING PROGRAM GUARD FAILED: classifications=% mappings=%',
            v_classification_count,
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-199 PRE-EXISTING PROGRAM GUARD PASS';

END
$$;


/*
====================================================================================================
7. PRE-EXISTING SOURCE POLICY GUARD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. PRE-EXISTING SOURCE POLICY GUARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    methodology_version

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'DISASTER_ASSISTANCE'
  AND inflow_subfamily = 'FEMA_IHP_OTHER_NEEDS_ASSISTANCE'
  AND valid_from_fiscal_year <= 2024
  AND (
        valid_through_fiscal_year IS NULL
        OR valid_through_fiscal_year >= 2020
      );


DO $$
DECLARE
    v_policy_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'DISASTER_ASSISTANCE'
      AND inflow_subfamily = 'FEMA_IHP_OTHER_NEEDS_ASSISTANCE'
      AND valid_from_fiscal_year <= 2024
      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          );


    IF v_policy_count <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 PRE-EXISTING SOURCE POLICY GUARD FAILED: policies=%',
            v_policy_count;
    END IF;


    RAISE NOTICE
        'ETL-199 PRE-EXISTING SOURCE POLICY GUARD PASS';

END
$$;


/*
====================================================================================================
8. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. INSERT SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_source_policy
(
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
    'DISASTER_ASSISTANCE',
    'FEMA_IHP_OTHER_NEEDS_ASSISTANCE',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'AL 97.050 represents FEMA Presidential Declared Disaster Assistance to '
    || 'Individuals and Households - Other Needs. ETL-198A certified 15 '
    || 'Washington FY2020-FY2024 transactions, 2 awards, 2 recipient records, '
    || 'and $731,476,459.87 net federal action obligation. The focal awards are '
    || '4481LOSTWAGESBENEFIT and 4481LOSTWAGESADMIN. No focal award identifier '
    || 'was cross-listed under another Assistance Listing, including AL 97.036 '
    || 'FEMA Public Assistance. Distinct FEMA programs are not duplicate dollars '
    || 'merely because they share agency, disaster, or COVID provenance. '
    || 'Downstream lost-wage/unemployment-benefit disbursements financed from '
    || 'these transfers are uses of the federal transfer and are not a second '
    || 'federal inflow. COVID and extraordinary flags are provenance dimensions, '
    || 'not separate additive accounting paths. Transaction action-date fiscal '
    || 'year controls ledger assignment, including later deobligations. County '
    || 'beneficiary/economic incidence remains unresolved.',

    'ANALYSIS-199-v1',
    2020,
    2024
);


DROP TABLE IF EXISTS pg_temp.m199_policy;

CREATE TEMP TABLE m199_policy AS

SELECT *
FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'DISASTER_ASSISTANCE'
  AND inflow_subfamily = 'FEMA_IHP_OTHER_NEEDS_ASSISTANCE'
  AND methodology_version = 'ANALYSIS-199-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m199_policy;


    IF v_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-199 SOURCE POLICY INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-199 SOURCE POLICY INSERT PASS';

END
$$;


SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version

FROM m199_policy;


/*
====================================================================================================
9. SOURCE POLICY ATTRIBUTE CERTIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad

    FROM m199_policy

    WHERE inflow_family <> 'DISASTER_ASSISTANCE'
       OR inflow_subfamily <> 'FEMA_IHP_OTHER_NEEDS_ASSISTANCE'
       OR accounting_measure <> 'NET_FEDERAL_ACTION_OBLIGATION'
       OR preferred_source <> 'USASPENDING_ASSISTANCE'
       OR allocation_source <> 'UNRESOLVED'
       OR overlapping_sources <> ARRAY[]::text[]
       OR ledger_treatment <> 'INCLUDE'
       OR methodology_version <> 'ANALYSIS-199-v1'
       OR valid_from_fiscal_year <> 2020
       OR valid_through_fiscal_year <> 2024;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 SOURCE POLICY ATTRIBUTE CERTIFICATION FAILED';
    END IF;


    RAISE NOTICE
        'ETL-199 SOURCE POLICY ATTRIBUTE CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
10. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. INSERT PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_classification
(
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
    '97.050',
    'Presidential Declared Disaster Assistance to Individuals and Households - Other Needs',
    'DISASTER_ASSISTANCE',
    'FEMA_IHP_OTHER_NEEDS_ASSISTANCE',
    'NONE',
    TRUE,
    TRUE,

    'ETL-198A certified AL 97.050 as a distinct FEMA Individual/Household '
    || 'Other Needs assistance stream. Both focal awards are Lost Wages awards. '
    || 'No focal award identifier was observed under another Assistance Listing, '
    || 'including AL 97.036 FEMA Public Assistance. COVID and extraordinary '
    || 'status are retained as provenance dimensions.',

    'ANALYSIS-199-v1',
    2020,
    2024
);


DROP TABLE IF EXISTS pg_temp.m199_classification;

CREATE TEMP TABLE m199_classification AS

SELECT *
FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '97.050'
  AND methodology_version = 'ANALYSIS-199-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m199_classification;


    IF v_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-199 PROGRAM CLASSIFICATION INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-199 PROGRAM CLASSIFICATION INSERT PASS';

END
$$;


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

FROM m199_classification;


/*
====================================================================================================
11. PROGRAM CLASSIFICATION ATTRIBUTE CERTIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad

    FROM m199_classification

    WHERE source_system <> 'USASPENDING_ASSISTANCE'
       OR source_program_code <> '97.050'
       OR inflow_family <> 'DISASTER_ASSISTANCE'
       OR inflow_subfamily <> 'FEMA_IHP_OTHER_NEEDS_ASSISTANCE'
       OR overlap_risk <> 'NONE'
       OR covid_relevance IS DISTINCT FROM TRUE
       OR extraordinary_relevance IS DISTINCT FROM TRUE
       OR methodology_version <> 'ANALYSIS-199-v1'
       OR valid_from_fiscal_year <> 2020
       OR valid_through_fiscal_year <> 2024;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 PROGRAM CLASSIFICATION ATTRIBUTE CERTIFICATION FAILED';
    END IF;


    RAISE NOTICE
        'ETL-199 PROGRAM CLASSIFICATION ATTRIBUTE CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
12. INSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. INSERT PROGRAM -> POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_policy_mapping
(
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
    '97.050',
    federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'AL 97.050 is included once as additive FEMA Individual/Household Other '
    || 'Needs assistance using net federal action obligation. Downstream Lost '
    || 'Wages benefit payments financed by these transfers are not separately '
    || 'additive. COVID and extraordinary classifications remain provenance '
    || 'dimensions only.',

    'ANALYSIS-199-v1',
    2020,
    2024

FROM m199_policy;


DROP TABLE IF EXISTS pg_temp.m199_mapping;

CREATE TEMP TABLE m199_mapping AS

SELECT *
FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '97.050'
  AND methodology_version = 'ANALYSIS-199-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m199_mapping;


    IF v_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-199 PROGRAM MAPPING INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-199 PROGRAM MAPPING INSERT PASS';

END
$$;


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version

FROM m199_mapping;


/*
====================================================================================================
13. PROGRAM MAPPING ATTRIBUTE CERTIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad

    FROM m199_mapping m

    CROSS JOIN m199_policy p

    WHERE m.source_system <> 'USASPENDING_ASSISTANCE'
       OR m.source_program_code <> '97.050'
       OR m.federal_inflow_source_policy_id <>
          p.federal_inflow_source_policy_id
       OR m.resolved_accounting_disposition <> 'INCLUDE_ADDITIVE'
       OR m.methodology_version <> 'ANALYSIS-199-v1'
       OR m.valid_from_fiscal_year <> 2020
       OR m.valid_through_fiscal_year <> 2024;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 PROGRAM MAPPING ATTRIBUTE CERTIFICATION FAILED';
    END IF;


    RAISE NOTICE
        'ETL-199 PROGRAM MAPPING ATTRIBUTE CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
14. RECONSTRUCT EFFECTIVE ACCOUNTING DISPOSITION

Reconstruct from the persisted policy chain rather than trusting the INSERT.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m199_effective;

CREATE TEMP TABLE m199_effective AS

SELECT
    f.*,

    m.federal_inflow_program_policy_mapping_id,
    m.resolved_accounting_disposition,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.methodology_version AS policy_methodology_version

FROM m199_focal f

LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = f.cfda_number
 AND m.valid_from_fiscal_year <= f.action_date_fiscal_year
 AND (
        m.valid_through_fiscal_year IS NULL
        OR m.valid_through_fiscal_year >= f.action_date_fiscal_year
     )

LEFT JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id;


ANALYZE m199_effective;


/*
====================================================================================================
15. EFFECTIVE DISPOSITION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. EFFECTIVE DISPOSITION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        resolved_accounting_disposition,
        'UNRESOLVED'
    ) AS resolved_accounting_disposition,

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

FROM m199_effective

GROUP BY
    COALESCE(
        resolved_accounting_disposition,
        'UNRESOLVED'
    )

ORDER BY 1;


DO $$
DECLARE
    v_tx       bigint;
    v_awards   bigint;
    v_amount   numeric;
    v_covid    numeric;
    v_iija     numeric;
    v_extra    numeric;
    v_bad      bigint;
BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            )
        ),

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
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m199_effective

    WHERE resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';


    SELECT COUNT(*)
    INTO v_bad

    FROM m199_effective

    WHERE resolved_accounting_disposition IS DISTINCT FROM
          'INCLUDE_ADDITIVE'

       OR inflow_family IS DISTINCT FROM
          'DISASTER_ASSISTANCE'

       OR inflow_subfamily IS DISTINCT FROM
          'FEMA_IHP_OTHER_NEEDS_ASSISTANCE'

       OR accounting_measure IS DISTINCT FROM
          'NET_FEDERAL_ACTION_OBLIGATION'

       OR preferred_source IS DISTINCT FROM
          'USASPENDING_ASSISTANCE'

       OR allocation_source IS DISTINCT FROM
          'UNRESOLVED'

       OR overlapping_sources IS DISTINCT FROM
          ARRAY[]::text[]

       OR ledger_treatment IS DISTINCT FROM
          'INCLUDE'

       OR policy_methodology_version IS DISTINCT FROM
          'ANALYSIS-199-v1';


    IF v_tx <> 15
       OR v_awards <> 2
       OR ROUND(v_amount, 2) <> 731476459.87
       OR ROUND(v_covid, 2) <> 731476459.87
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 731476459.87
       OR v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 EFFECTIVE DISPOSITION FAILED: tx=% awards=% amount=% COVID=% IIJA=% extraordinary=% bad_rows=%',
            v_tx,
            v_awards,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2),
            v_bad;
    END IF;


    RAISE NOTICE
        'ETL-199 EFFECTIVE DISPOSITION PASS: all 15 transactions / $731,476,459.87 INCLUDE_ADDITIVE';

END
$$;


/*
====================================================================================================
16. PROVENANCE PRESERVATION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. PROVENANCE PRESERVATION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    is_covid,
    is_iija,
    is_extraordinary,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m199_effective

GROUP BY
    is_covid,
    is_iija,
    is_extraordinary

ORDER BY
    is_covid,
    is_iija,
    is_extraordinary;


DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad

    FROM m199_effective

    WHERE is_covid IS DISTINCT FROM TRUE
       OR is_iija IS DISTINCT FROM FALSE
       OR is_extraordinary IS DISTINCT FROM TRUE;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-199 PROVENANCE PRESERVATION FAILED: unexpected provenance rows=%',
            v_bad;
    END IF;


    RAISE NOTICE
        'ETL-199 PROVENANCE PRESERVATION PASS';

END
$$;


/*
====================================================================================================
17. PERSISTED OBJECT CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. PERSISTED OBJECT CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.methodology_version,

    c.federal_inflow_program_classification_id,
    c.source_program_code,
    c.source_program_title,
    c.overlap_risk,
    c.covid_relevance,
    c.extraordinary_relevance,

    m.federal_inflow_program_policy_mapping_id,
    m.resolved_accounting_disposition

FROM m199_policy p

CROSS JOIN m199_classification c

CROSS JOIN m199_mapping m;


DO $$
DECLARE
    v_policy          bigint;
    v_classification  bigint;
    v_mapping         bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'DISASTER_ASSISTANCE'
      AND inflow_subfamily = 'FEMA_IHP_OTHER_NEEDS_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-199-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    SELECT COUNT(*)
    INTO v_classification

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '97.050'
      AND methodology_version = 'ANALYSIS-199-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    SELECT COUNT(*)
    INTO v_mapping

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '97.050'
      AND methodology_version = 'ANALYSIS-199-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    IF v_policy <> 1
       OR v_classification <> 1
       OR v_mapping <> 1
    THEN
        RAISE EXCEPTION
            'ETL-199 PERSISTED OBJECT CERTIFICATION FAILED: policy=% classification=% mapping=%',
            v_policy,
            v_classification,
            v_mapping;
    END IF;


    RAISE NOTICE
        'ETL-199 PERSISTED OBJECT CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
18. FINAL EXACT ACCOUNTING CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. FINAL EXACT ACCOUNTING CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,

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

FROM m199_effective

GROUP BY resolved_accounting_disposition;


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

    FROM m199_effective

    WHERE resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';


    IF v_tx <> 15
       OR v_awards <> 2
       OR v_recip <> 2
       OR ROUND(v_amount, 2) <> 731476459.87
       OR ROUND(v_covid, 2) <> 731476459.87
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 731476459.87
    THEN
        RAISE EXCEPTION
            'ETL-199 FINAL CERTIFICATION FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-199 FINAL CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
19. CERTIFICATION SUMMARY
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-199 CERTIFICATION COMPLETE'
\echo ''
\echo 'Accounting treatment:'
\echo '  DISASTER_ASSISTANCE / FEMA_IHP_OTHER_NEEDS_ASSISTANCE'
\echo '  USASPENDING_ASSISTANCE'
\echo '  NET_FEDERAL_ACTION_OBLIGATION'
\echo '  INCLUDE_ADDITIVE'
\echo '  allocation_source = UNRESOLVED'
\echo ''
\echo 'Certified FY2020-FY2024 population:'
\echo '  15 transactions'
\echo '  2 awards'
\echo '  2 recipient records'
\echo '  $731,476,459.87 net federal action obligation'
\echo '  $731,476,459.87 COVID'
\echo '  $0 IIJA'
\echo '  $731,476,459.87 extraordinary'
\echo ''
\echo 'Award-level identity:'
\echo '  4481LOSTWAGESBENEFIT'
\echo '  4481LOSTWAGESADMIN'
\echo ''
\echo 'Double-count prohibitions:'
\echo '  AL 97.050 is distinct from AL 97.036 FEMA Public Assistance.'
\echo '  Downstream Lost Wages benefit payments financed by these transfers'
\echo '  are uses of the federal transfer and are NOT a second federal inflow.'
\echo '  COVID/extraordinary are provenance dimensions, not additive paths.'
\echo ''
\echo 'Transaction action-date fiscal year controls ledger assignment.'
\echo 'Later deobligations remain in their actual transaction fiscal years.'
\echo 'County beneficiary/economic incidence remains unresolved.'
\echo '===================================================================================================='
\echo ''


COMMIT;

\echo ''
\echo 'ETL-199 COMMIT COMPLETE'
\echo ''