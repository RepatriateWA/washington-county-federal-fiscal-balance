/*
====================================================================================================
ETL-198
SEED FOSTER CARE TITLE IV-E ACCOUNTING POLICY

Assistance Listing:
    93.658 - Foster Care Title IV-E

Accounting decision:
    CHILD_WELFARE_ASSISTANCE / FOSTER_CARE_TITLE_IV_E

    accounting_measure               NET_FEDERAL_ACTION_OBLIGATION
    preferred_source                 USASPENDING_ASSISTANCE
    allocation_source                UNRESOLVED
    overlapping_sources              {}
    ledger_treatment                 INCLUDE
    overlap_risk                     NONE
    covid_relevance                  FALSE
    extraordinary_relevance          FALSE
    resolved_accounting_disposition  INCLUDE_ADDITIVE
    methodology_version              ANALYSIS-198-v1

Certified FY2020-FY2024 control:
    Transactions                     70
    Awards                           23
    Recipients                        3
    Net obligation        $762,368,121.74
    Positive obligations  $808,042,559.74
    Negative adjustments  -$45,674,438.00
    COVID                             $0.00
    IIJA                              $0.00
    Extraordinary                     $0.00

Accounting interpretation:
    AL 93.658 represents federal HHS / Administration for Children and
    Families assistance for Foster Care Title IV-E.

    No focal AL 93.658 award identifier was observed under another Assistance
    Listing in the certified Washington FY2020-FY2024 assistance population.

    Related child-welfare programs are not duplicates merely because they
    share administering recipients.

Double-count prohibition:
    Downstream state, tribal, provider, foster-family, beneficiary, or other
    expenditures financed from these Title IV-E transfers are uses of the
    federal transfer and MUST NOT be counted as a second federal inflow.

Fiscal-year rule:
    WCFFBP uses transaction action-date fiscal year for the accounting ledger.
    Descriptive fiscal-year labels embedded in award identifiers or award
    descriptions do not override transaction fiscal-year assignment.

County incidence:
    UNRESOLVED.

    Administrative recipient geography must not be interpreted as beneficiary
    or economic-incidence geography.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-198'
\echo 'SEED FOSTER CARE TITLE IV-E ACCOUNTING POLICY'
\echo 'AL 93.658'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD CERTIFIED FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m198_foster;

CREATE TEMP TABLE m198_foster AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.658';


ANALYZE m198_foster;


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

FROM m198_foster;


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
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_extraordinary
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

    FROM m198_foster;


    IF v_tx <> 70
       OR v_awards <> 23
       OR v_recip <> 3
       OR ROUND(v_amount, 2) <> 762368121.74
       OR ROUND(v_covid, 2) <> 0.00
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 0.00
    THEN
        RAISE EXCEPTION
            'ETL-198 EXACT PRE-CONTROL FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-198 EXACT PRE-CONTROL PASS';

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

FROM m198_foster

GROUP BY 1
ORDER BY 1;


DO $$
DECLARE
    v_positive numeric;
    v_negative numeric;
    v_zero     numeric;
    v_net      numeric;
BEGIN

    SELECT
        COALESCE(SUM(
            CASE
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN federal_action_obligation = 0
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_positive,
        v_negative,
        v_zero,
        v_net

    FROM m198_foster;


    IF ROUND(v_positive, 2) <> 808042559.74
       OR ROUND(v_negative, 2) <> -45674438.00
       OR ROUND(v_zero, 2) <> 0.00
       OR ROUND(v_net, 2) <> 762368121.74
    THEN
        RAISE EXCEPTION
            'ETL-198 TRANSACTION-SIGN CONTROL FAILED: positive=% negative=% zero=% net=%',
            ROUND(v_positive, 2),
            ROUND(v_negative, 2),
            ROUND(v_zero, 2),
            ROUND(v_net, 2);
    END IF;


    RAISE NOTICE
        'ETL-198 TRANSACTION-SIGN CONTROL PASS';

END
$$;


/*
====================================================================================================
4. PRE-EXISTING PROGRAM CLASSIFICATION / MAPPING GUARD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PRE-EXISTING PROGRAM CLASSIFICATION / MAPPING GUARD'
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
  AND source_program_code = '93.658'
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
  AND source_program_code = '93.658'
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
      AND source_program_code = '93.658'
      AND valid_from_fiscal_year <= 2024
      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          );


    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.658'
      AND valid_from_fiscal_year <= 2024
      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          );


    IF v_classification_count <> 0
       OR v_mapping_count <> 0
    THEN
        RAISE EXCEPTION
            'ETL-198 PRE-EXISTING PROGRAM GUARD FAILED: classifications=% mappings=%',
            v_classification_count,
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-198 PRE-EXISTING PROGRAM GUARD PASS';

END
$$;


/*
====================================================================================================
5. PRE-EXISTING SOURCE POLICY GUARD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. PRE-EXISTING SOURCE POLICY GUARD'
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

WHERE inflow_family = 'CHILD_WELFARE_ASSISTANCE'
  AND inflow_subfamily = 'FOSTER_CARE_TITLE_IV_E'
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
    WHERE inflow_family = 'CHILD_WELFARE_ASSISTANCE'
      AND inflow_subfamily = 'FOSTER_CARE_TITLE_IV_E'
      AND valid_from_fiscal_year <= 2024
      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          );


    IF v_policy_count <> 0
    THEN
        RAISE EXCEPTION
            'ETL-198 PRE-EXISTING SOURCE POLICY GUARD FAILED: policies=%',
            v_policy_count;
    END IF;


    RAISE NOTICE
        'ETL-198 PRE-EXISTING SOURCE POLICY GUARD PASS';

END
$$;


/*
====================================================================================================
6. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. INSERT SOURCE POLICY'
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
    'CHILD_WELFARE_ASSISTANCE',
    'FOSTER_CARE_TITLE_IV_E',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'AL 93.658 represents federal HHS Administration for Children and Families '
    || 'Foster Care Title IV-E assistance. ETL-197B certified 70 Washington '
    || 'FY2020-FY2024 transactions, 23 awards, 3 recipients, and '
    || '$762,368,121.74 net federal action obligation. No focal award identifier '
    || 'was cross-listed under another Assistance Listing. Related child-welfare '
    || 'programs and shared administering recipients are not duplicate-dollar '
    || 'evidence. Downstream expenditures financed from these transfers are uses '
    || 'of the federal transfer and are not a second federal inflow. Transaction '
    || 'action-date fiscal year controls ledger assignment; descriptive fiscal-year '
    || 'labels embedded in award identifiers or descriptions do not override it. '
    || 'County beneficiary/economic incidence remains unresolved.',

    'ANALYSIS-198-v1',
    2020,
    2024
);


DROP TABLE IF EXISTS pg_temp.m198_policy;

CREATE TEMP TABLE m198_policy AS

SELECT *
FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'CHILD_WELFARE_ASSISTANCE'
  AND inflow_subfamily = 'FOSTER_CARE_TITLE_IV_E'
  AND methodology_version = 'ANALYSIS-198-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m198_policy;


    IF v_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-198 SOURCE POLICY INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-198 SOURCE POLICY INSERT PASS';

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

FROM m198_policy;


/*
====================================================================================================
7. SOURCE POLICY ATTRIBUTE CERTIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad
    FROM m198_policy

    WHERE inflow_family <> 'CHILD_WELFARE_ASSISTANCE'
       OR inflow_subfamily <> 'FOSTER_CARE_TITLE_IV_E'
       OR accounting_measure <> 'NET_FEDERAL_ACTION_OBLIGATION'
       OR preferred_source <> 'USASPENDING_ASSISTANCE'
       OR allocation_source <> 'UNRESOLVED'
       OR overlapping_sources <> ARRAY[]::text[]
       OR ledger_treatment <> 'INCLUDE'
       OR methodology_version <> 'ANALYSIS-198-v1'
       OR valid_from_fiscal_year <> 2020
       OR valid_through_fiscal_year <> 2024;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-198 SOURCE POLICY ATTRIBUTE CERTIFICATION FAILED';
    END IF;


    RAISE NOTICE
        'ETL-198 SOURCE POLICY ATTRIBUTE CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
8. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. INSERT PROGRAM CLASSIFICATION'
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
    '93.658',
    'Foster Care Title IV-E',
    'CHILD_WELFARE_ASSISTANCE',
    'FOSTER_CARE_TITLE_IV_E',
    'NONE',
    FALSE,
    FALSE,

    'ETL-197B certified AL 93.658 as a homogeneous Foster Care Title IV-E '
    || 'federal assistance stream for statewide accounting. No focal award '
    || 'identifier was cross-listed under another Assistance Listing. Related '
    || 'child-welfare programs and shared recipients do not by themselves '
    || 'constitute duplicate-dollar evidence.',

    'ANALYSIS-198-v1',
    2020,
    2024
);


DROP TABLE IF EXISTS pg_temp.m198_classification;

CREATE TEMP TABLE m198_classification AS

SELECT *
FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.658'
  AND methodology_version = 'ANALYSIS-198-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m198_classification;


    IF v_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-198 PROGRAM CLASSIFICATION INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-198 PROGRAM CLASSIFICATION INSERT PASS';

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

FROM m198_classification;


/*
====================================================================================================
9. PROGRAM CLASSIFICATION ATTRIBUTE CERTIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad
    FROM m198_classification

    WHERE source_system <> 'USASPENDING_ASSISTANCE'
       OR source_program_code <> '93.658'
       OR inflow_family <> 'CHILD_WELFARE_ASSISTANCE'
       OR inflow_subfamily <> 'FOSTER_CARE_TITLE_IV_E'
       OR overlap_risk <> 'NONE'
       OR covid_relevance IS DISTINCT FROM FALSE
       OR extraordinary_relevance IS DISTINCT FROM FALSE
       OR methodology_version <> 'ANALYSIS-198-v1'
       OR valid_from_fiscal_year <> 2020
       OR valid_through_fiscal_year <> 2024;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-198 PROGRAM CLASSIFICATION ATTRIBUTE CERTIFICATION FAILED';
    END IF;


    RAISE NOTICE
        'ETL-198 PROGRAM CLASSIFICATION ATTRIBUTE CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
10. INSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. INSERT PROGRAM -> POLICY MAPPING'
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
    '93.658',
    federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'AL 93.658 is included once as additive federal child-welfare assistance '
    || 'using USAspending net federal action obligation. Downstream expenditures '
    || 'financed by the Title IV-E transfer are not separately additive.',

    'ANALYSIS-198-v1',
    2020,
    2024

FROM m198_policy;


DROP TABLE IF EXISTS pg_temp.m198_mapping;

CREATE TEMP TABLE m198_mapping AS

SELECT *
FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.658'
  AND methodology_version = 'ANALYSIS-198-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m198_mapping;


    IF v_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-198 PROGRAM MAPPING INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-198 PROGRAM MAPPING INSERT PASS';

END
$$;


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version

FROM m198_mapping;


/*
====================================================================================================
11. PROGRAM MAPPING ATTRIBUTE CERTIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad

    FROM m198_mapping m

    CROSS JOIN m198_policy p

    WHERE m.source_system <> 'USASPENDING_ASSISTANCE'
       OR m.source_program_code <> '93.658'
       OR m.federal_inflow_source_policy_id <>
          p.federal_inflow_source_policy_id
       OR m.resolved_accounting_disposition <> 'INCLUDE_ADDITIVE'
       OR m.methodology_version <> 'ANALYSIS-198-v1'
       OR m.valid_from_fiscal_year <> 2020
       OR m.valid_through_fiscal_year <> 2024;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-198 PROGRAM MAPPING ATTRIBUTE CERTIFICATION FAILED';
    END IF;


    RAISE NOTICE
        'ETL-198 PROGRAM MAPPING ATTRIBUTE CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
12. RECONSTRUCT EFFECTIVE ACCOUNTING DISPOSITION

Do not merely trust the inserted rows.

Reconstruct the effective treatment from:
    certified assistance ledger
        ->
    program policy mapping
        ->
    source policy
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m198_effective;

CREATE TEMP TABLE m198_effective AS

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

FROM m198_foster f

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


ANALYZE m198_effective;


/*
====================================================================================================
13. EFFECTIVE DISPOSITION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EFFECTIVE DISPOSITION CONTROL'
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

FROM m198_effective

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
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_extraordinary
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

    FROM m198_effective

    WHERE resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';


    SELECT COUNT(*)
    INTO v_bad
    FROM m198_effective

    WHERE resolved_accounting_disposition IS DISTINCT FROM
          'INCLUDE_ADDITIVE'

       OR inflow_family IS DISTINCT FROM
          'CHILD_WELFARE_ASSISTANCE'

       OR inflow_subfamily IS DISTINCT FROM
          'FOSTER_CARE_TITLE_IV_E'

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
          'ANALYSIS-198-v1';


    IF v_tx <> 70
       OR v_awards <> 23
       OR ROUND(v_amount, 2) <> 762368121.74
       OR ROUND(v_covid, 2) <> 0.00
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 0.00
       OR v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-198 EFFECTIVE DISPOSITION FAILED: tx=% awards=% amount=% COVID=% IIJA=% extraordinary=% bad_rows=%',
            v_tx,
            v_awards,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2),
            v_bad;
    END IF;


    RAISE NOTICE
        'ETL-198 EFFECTIVE DISPOSITION PASS: all 70 transactions / $762,368,121.74 INCLUDE_ADDITIVE';

END
$$;


/*
====================================================================================================
14. PROVENANCE PRESERVATION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. PROVENANCE PRESERVATION CONTROL'
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

FROM m198_effective

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
    FROM m198_effective

    WHERE is_covid IS DISTINCT FROM FALSE
       OR is_iija IS DISTINCT FROM FALSE
       OR is_extraordinary IS DISTINCT FROM FALSE;


    IF v_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-198 PROVENANCE PRESERVATION FAILED: unexpected provenance rows=%',
            v_bad;
    END IF;


    RAISE NOTICE
        'ETL-198 PROVENANCE PRESERVATION PASS';

END
$$;


/*
====================================================================================================
15. PERSISTED OBJECT CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. PERSISTED OBJECT CERTIFICATION'
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

FROM m198_policy p

CROSS JOIN m198_classification c

CROSS JOIN m198_mapping m;


DO $$
DECLARE
    v_policy         bigint;
    v_classification bigint;
    v_mapping        bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'CHILD_WELFARE_ASSISTANCE'
      AND inflow_subfamily = 'FOSTER_CARE_TITLE_IV_E'
      AND methodology_version = 'ANALYSIS-198-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    SELECT COUNT(*)
    INTO v_classification
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.658'
      AND methodology_version = 'ANALYSIS-198-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    SELECT COUNT(*)
    INTO v_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.658'
      AND methodology_version = 'ANALYSIS-198-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    IF v_policy <> 1
       OR v_classification <> 1
       OR v_mapping <> 1
    THEN
        RAISE EXCEPTION
            'ETL-198 PERSISTED OBJECT CERTIFICATION FAILED: policy=% classification=% mapping=%',
            v_policy,
            v_classification,
            v_mapping;
    END IF;


    RAISE NOTICE
        'ETL-198 PERSISTED OBJECT CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
16. FINAL EXACT ACCOUNTING CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FINAL EXACT ACCOUNTING CERTIFICATION'
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

FROM m198_effective

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
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_extraordinary
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

    FROM m198_effective

    WHERE resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';


    IF v_tx <> 70
       OR v_awards <> 23
       OR v_recip <> 3
       OR ROUND(v_amount, 2) <> 762368121.74
       OR ROUND(v_covid, 2) <> 0.00
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 0.00
    THEN
        RAISE EXCEPTION
            'ETL-198 FINAL CERTIFICATION FAILED: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-198 FINAL CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
17. CERTIFICATION SUMMARY
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-198 CERTIFICATION COMPLETE'
\echo ''
\echo 'Accounting treatment:'
\echo '  CHILD_WELFARE_ASSISTANCE / FOSTER_CARE_TITLE_IV_E'
\echo '  USASPENDING_ASSISTANCE'
\echo '  NET_FEDERAL_ACTION_OBLIGATION'
\echo '  INCLUDE_ADDITIVE'
\echo '  allocation_source = UNRESOLVED'
\echo ''
\echo 'Certified FY2020-FY2024 population:'
\echo '  70 transactions'
\echo '  23 awards'
\echo '  3 recipients'
\echo '  $762,368,121.74 net federal action obligation'
\echo '  $0 COVID'
\echo '  $0 IIJA'
\echo '  $0 extraordinary'
\echo ''
\echo 'Double-count prohibition:'
\echo '  downstream expenditures financed by Foster Care Title IV-E transfers'
\echo '  are uses of the federal transfer and are NOT a second federal inflow.'
\echo ''
\echo 'Related child-welfare Assistance Listings are not duplicates merely'
\echo 'because they share administering recipients.'
\echo ''
\echo 'Transaction action-date fiscal year controls ledger assignment.'
\echo 'County beneficiary/economic incidence remains unresolved.'
\echo '===================================================================================================='
\echo ''


COMMIT;

\echo ''
\echo 'ETL-198 COMMIT COMPLETE'
\echo ''