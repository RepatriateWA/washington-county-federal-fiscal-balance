/*
====================================================================================================
ETL-195
SEED PBGC SPECIAL FINANCIAL ASSISTANCE ACCOUNTING POLICY
AL 86.001 - PENSION PLAN TERMINATION INSURANCE
====================================================================================================

Purpose:
    Establish WCFFBP statewide accounting treatment for Washington
    FY2020-FY2024 USAspending Assistance Listing 86.001.

Evidence:
    ETL-194A established that the nonzero Washington AL 86.001 population is
    not ordinary recurring PBGC pension-benefit activity.

    The entire $989,322,322.39 nonzero population consists of two Special
    Financial Assistance (SFA) awards to multiemployer pension plans pursuant
    to the American Rescue Plan Act of 2021 and section 4262 of ERISA:

        FY2023   $75,805,291.21
        FY2024  $913,517,031.18
                 --------------
        Total   $989,322,322.39

    The remaining ten observations are zero-dollar direct-loan records.

Overlap conclusion:
    No identified overlap pathway exists between these PBGC SFA transfers and
    WCFFBP's principal SSA OASDI or Railroad Retirement beneficiary-payment
    accounting paths.

    ETL-194A also found no shared AL 86.001 award identifiers under another
    Assistance Listing in the Washington FY2020-FY2024 certified assistance
    population.

Accounting boundary:
    The federal inflow is recognized at the PBGC -> multiemployer pension plan
    Special Financial Assistance transfer.

    Subsequent pension payments, distributions, investment activity, or other
    uses of the already-counted SFA assets are not additional federal inflows.

Principal accounting treatment:

    inflow_family:
        PENSION_ASSISTANCE

    inflow_subfamily:
        PBGC_SPECIAL_FINANCIAL_ASSISTANCE

    accounting_measure:
        NET_FEDERAL_ACTION_OBLIGATION

    preferred_source:
        USASPENDING_ASSISTANCE

    allocation_source:
        UNRESOLVED

    overlap_risk:
        NONE

    ledger_treatment:
        INCLUDE

    resolved_accounting_disposition:
        INCLUDE_ADDITIVE

Provenance:
    All nonzero FY2020-FY2024 AL 86.001 obligations are COVID/ARPA and
    extraordinary under the certified assistance ledger provenance flags.

    IIJA amount is zero.

Important:
    This policy applies to the empirically profiled FY2020-FY2024 Washington
    AL 86.001 population. It does not authorize extrapolation of this semantic
    composition to other fiscal periods.

County incidence remains unresolved.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-195 - SEED PBGC SPECIAL FINANCIAL ASSISTANCE ACCOUNTING POLICY'
\echo 'AL 86.001'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m195_pbgc;

CREATE TEMP TABLE m195_pbgc AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '86.001';


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

FROM m195_pbgc;


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

    FROM m195_pbgc;


    IF v_tx <> 12 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-CONTROL FAILED: expected 12 transactions; found %',
            v_tx;
    END IF;


    IF v_awards <> 12 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-CONTROL FAILED: expected 12 awards; found %',
            v_awards;
    END IF;


    IF v_recip <> 3 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-CONTROL FAILED: expected 3 recipients; found %',
            v_recip;
    END IF;


    IF ROUND(v_amount, 2) <> 989322322.39 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-CONTROL FAILED: expected net obligation 989322322.39; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 989322322.39 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-CONTROL FAILED: expected COVID amount 989322322.39; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-CONTROL FAILED: expected IIJA amount 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 989322322.39 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-CONTROL FAILED: expected extraordinary amount 989322322.39; found %',
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-195 PRE-CONTROL PASS: tx=% awards=% recipients=% amount=% COVID=% IIJA=% extraordinary=%',
        v_tx,
        v_awards,
        v_recip,
        ROUND(v_amount, 2),
        ROUND(v_covid, 2),
        ROUND(v_iija, 2),
        ROUND(v_extra, 2);

END
$$;


/*
====================================================================================================
3. FISCAL-YEAR CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FISCAL-YEAR CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

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

FROM m195_pbgc

GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. NONZERO-TRANSACTION SEMANTIC GUARD

ETL-194A established that the only nonzero observations are the two ARPA
Special Financial Assistance transfers.

Fail closed if the number, amount, assistance mechanism, or descriptions
change materially before migration.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. NONZERO SPECIAL FINANCIAL ASSISTANCE GUARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    action_date,
    recipient_name,
    assistance_type_code,
    federal_action_obligation,
    transaction_description,
    canonical_award_description

FROM m195_pbgc

WHERE federal_action_obligation <> 0

ORDER BY action_date;


DO $$
DECLARE
    v_nonzero_tx       bigint;
    v_nonzero_amount   numeric;
    v_bad_type         bigint;
    v_bad_semantics    bigint;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),

        COUNT(*) FILTER
        (
            WHERE assistance_type_code IS DISTINCT FROM '06'
        ),

        COUNT(*) FILTER
        (
            WHERE LOWER(
                COALESCE(transaction_description, '')
                || ' '
                || COALESCE(canonical_award_description, '')
            ) NOT LIKE '%special financial assistance%'
        )

    INTO
        v_nonzero_tx,
        v_nonzero_amount,
        v_bad_type,
        v_bad_semantics

    FROM m195_pbgc

    WHERE federal_action_obligation <> 0;


    IF v_nonzero_tx <> 2 THEN
        RAISE EXCEPTION
            'ETL-195 SFA GUARD FAILED: expected 2 nonzero transactions; found %',
            v_nonzero_tx;
    END IF;


    IF ROUND(v_nonzero_amount, 2) <> 989322322.39 THEN
        RAISE EXCEPTION
            'ETL-195 SFA GUARD FAILED: expected nonzero amount 989322322.39; found %',
            ROUND(v_nonzero_amount, 2);
    END IF;


    IF v_bad_type <> 0 THEN
        RAISE EXCEPTION
            'ETL-195 SFA GUARD FAILED: % nonzero observations are not assistance type 06',
            v_bad_type;
    END IF;


    IF v_bad_semantics <> 0 THEN
        RAISE EXCEPTION
            'ETL-195 SFA GUARD FAILED: % nonzero observations lack Special Financial Assistance semantics',
            v_bad_semantics;
    END IF;


    RAISE NOTICE
        'ETL-195 SFA GUARD PASS: 2 nonzero SFA transactions totaling 989322322.39';

END
$$;


/*
====================================================================================================
5. ZERO-DOLLAR LEGACY LOAN GUARD

The remaining ten observations are retained for provenance but contribute
nothing to NET_FEDERAL_ACTION_OBLIGATION.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. ZERO-DOLLAR LEGACY LOAN GUARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    assistance_type_code,
    assistance_type_description,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m195_pbgc

WHERE federal_action_obligation = 0

GROUP BY
    assistance_type_code,
    assistance_type_description

ORDER BY assistance_type_code;


DO $$
DECLARE
    v_zero_tx     bigint;
    v_bad_type    bigint;
BEGIN

    SELECT
        COUNT(*),

        COUNT(*) FILTER
        (
            WHERE assistance_type_code IS DISTINCT FROM '07'
        )

    INTO
        v_zero_tx,
        v_bad_type

    FROM m195_pbgc

    WHERE federal_action_obligation = 0;


    IF v_zero_tx <> 10 THEN
        RAISE EXCEPTION
            'ETL-195 ZERO-DOLLAR GUARD FAILED: expected 10 zero-dollar observations; found %',
            v_zero_tx;
    END IF;


    IF v_bad_type <> 0 THEN
        RAISE EXCEPTION
            'ETL-195 ZERO-DOLLAR GUARD FAILED: % zero-dollar observations are not assistance type 07',
            v_bad_type;
    END IF;


    RAISE NOTICE
        'ETL-195 ZERO-DOLLAR LEGACY LOAN GUARD PASS';

END
$$;


/*
====================================================================================================
6. PRE-EXISTING POLICY GUARD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. PRE-EXISTING POLICY GUARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '86.001'
  AND valid_through_fiscal_year IS NULL;


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '86.001'
  AND valid_through_fiscal_year IS NULL;


DO $$
DECLARE
    v_class_count bigint;
    v_map_count   bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_class_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '86.001'
      AND valid_through_fiscal_year IS NULL;


    SELECT COUNT(*)
    INTO v_map_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '86.001'
      AND valid_through_fiscal_year IS NULL;


    IF v_class_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-EXISTING POLICY GUARD FAILED: active AL 86.001 classification already exists';
    END IF;


    IF v_map_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-195 PRE-EXISTING POLICY GUARD FAILED: active AL 86.001 policy mapping already exists';
    END IF;


    RAISE NOTICE
        'ETL-195 PRE-EXISTING POLICY GUARD PASS';

END
$$;


/*
====================================================================================================
7. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. INSERT PBGC SPECIAL FINANCIAL ASSISTANCE SOURCE POLICY'
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

SELECT
    'PENSION_ASSISTANCE',

    'PBGC_SPECIAL_FINANCIAL_ASSISTANCE',

    'NET_FEDERAL_ACTION_OBLIGATION',

    'USASPENDING_ASSISTANCE',

    'UNRESOLVED',

    ARRAY[]::text[],

    'INCLUDE',

    'ETL-194A established that the nonzero Washington FY2020-FY2024 '
    ||
    'Assistance Listing 86.001 population consists entirely of two Pension '
    ||
    'Benefit Guaranty Corporation Special Financial Assistance transfers to '
    ||
    'multiemployer pension plans pursuant to the American Rescue Plan Act of '
    ||
    '2021 and section 4262 of ERISA. The two nonzero transactions total '
    ||
    '$989,322,322.39. Ten additional AL 86.001 observations are zero-dollar '
    ||
    'direct-loan records and therefore contribute zero under the net federal '
    ||
    'action obligation accounting measure. No identified overlap pathway '
    ||
    'exists with WCFFBP principal SSA OASDI or Railroad Retirement beneficiary '
    ||
    'payment accounting. ETL-194A found no shared AL 86.001 award identifiers '
    ||
    'under another Washington Assistance Listing for FY2020-FY2024. The federal '
    ||
    'inflow is recognized at the PBGC-to-multiemployer-plan SFA transfer. '
    ||
    'Subsequent pension payments, distributions, investment activity, or other '
    ||
    'uses of the already-counted SFA assets are not additional federal inflows. '
    ||
    'All nonzero obligations carry COVID/ARPA and extraordinary provenance; '
    ||
    'IIJA amount is zero. County incidence remains unresolved.',

    'ANALYSIS-195-v1',

    2020,

    NULL

WHERE NOT EXISTS
(
    SELECT 1

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'PENSION_ASSISTANCE'
      AND inflow_subfamily = 'PBGC_SPECIAL_FINANCIAL_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-195-v1'
);


SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'PENSION_ASSISTANCE'
  AND inflow_subfamily = 'PBGC_SPECIAL_FINANCIAL_ASSISTANCE'
  AND methodology_version = 'ANALYSIS-195-v1';


/*
====================================================================================================
8. ASSERT SOURCE POLICY
====================================================================================================
*/

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'PENSION_ASSISTANCE'
      AND inflow_subfamily = 'PBGC_SPECIAL_FINANCIAL_ASSISTANCE'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND allocation_source = 'UNRESOLVED'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-195-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year IS NULL;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-195 SOURCE POLICY ASSERTION FAILED: expected exactly 1 policy; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-195 SOURCE POLICY ASSERTION PASS';

END
$$;


/*
====================================================================================================
9. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. INSERT AL 86.001 PROGRAM CLASSIFICATION'
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

SELECT
    'USASPENDING_ASSISTANCE',

    '86.001',

    'PENSION PLAN TERMINATION INSURANCE',

    'PENSION_ASSISTANCE',

    'PBGC_SPECIAL_FINANCIAL_ASSISTANCE',

    'NONE',

    TRUE,

    TRUE,

    'ETL-194A established that all nonzero Washington FY2020-FY2024 '
    ||
    'AL 86.001 obligations are PBGC Special Financial Assistance transfers '
    ||
    'to multiemployer pension plans pursuant to ARPA and section 4262 of '
    ||
    'ERISA. No principal-source overlap pathway was identified with SSA OASDI '
    ||
    'or Railroad Retirement, and no focal award identifier appeared under '
    ||
    'another Assistance Listing. Ten additional AL 86.001 direct-loan '
    ||
    'observations have zero federal action obligation.',

    'ANALYSIS-195-v1',

    2020,

    NULL

WHERE NOT EXISTS
(
    SELECT 1

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '86.001'
      AND methodology_version = 'ANALYSIS-195-v1'
);


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
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '86.001'
  AND methodology_version = 'ANALYSIS-195-v1';


/*
====================================================================================================
10. ASSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '86.001'
      AND inflow_family = 'PENSION_ASSISTANCE'
      AND inflow_subfamily = 'PBGC_SPECIAL_FINANCIAL_ASSISTANCE'
      AND overlap_risk = 'NONE'
      AND covid_relevance = TRUE
      AND extraordinary_relevance = TRUE
      AND methodology_version = 'ANALYSIS-195-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year IS NULL;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-195 PROGRAM CLASSIFICATION ASSERTION FAILED: expected exactly 1 classification; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-195 PROGRAM CLASSIFICATION ASSERTION PASS';

END
$$;


/*
====================================================================================================
11. INSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. INSERT AL 86.001 PROGRAM POLICY MAPPING'
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

    '86.001',

    p.federal_inflow_source_policy_id,

    'INCLUDE_ADDITIVE',

    'Washington FY2020-FY2024 AL 86.001 is included additively using '
    ||
    'USAspending net federal action obligations. The entire nonzero amount '
    ||
    'consists of two PBGC ARPA Special Financial Assistance transfers to '
    ||
    'multiemployer pension plans. No identified principal-source overlap '
    ||
    'pathway exists. Downstream uses of already-counted SFA assets are not '
    ||
    'second federal inflows.',

    'ANALYSIS-195-v1',

    2020,

    NULL

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'PENSION_ASSISTANCE'
  AND p.inflow_subfamily = 'PBGC_SPECIAL_FINANCIAL_ASSISTANCE'
  AND p.methodology_version = 'ANALYSIS-195-v1'

  AND NOT EXISTS
  (
      SELECT 1

      FROM reference.federal_inflow_program_policy_mapping m

      WHERE m.source_system = 'USASPENDING_ASSISTANCE'
        AND m.source_program_code = '86.001'
        AND m.methodology_version = 'ANALYSIS-195-v1'
  );


SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.federal_inflow_source_policy_id,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping m

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '86.001'
  AND m.methodology_version = 'ANALYSIS-195-v1';


/*
====================================================================================================
12. ASSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '86.001'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND m.methodology_version = 'ANALYSIS-195-v1'
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year IS NULL

      AND p.inflow_family = 'PENSION_ASSISTANCE'
      AND p.inflow_subfamily = 'PBGC_SPECIAL_FINANCIAL_ASSISTANCE'
      AND p.accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND p.preferred_source = 'USASPENDING_ASSISTANCE'
      AND p.ledger_treatment = 'INCLUDE';


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-195 PROGRAM POLICY MAPPING ASSERTION FAILED: expected exactly 1 mapping; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-195 PROGRAM POLICY MAPPING ASSERTION PASS';

END
$$;


/*
====================================================================================================
13. EFFECTIVE ACCOUNTING RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EFFECTIVE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m195_effective;

CREATE TEMP TABLE m195_effective AS

SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year,
    l.cfda_number,
    l.federal_action_obligation,
    l.is_covid,
    l.is_iija,
    l.is_extraordinary,

    m.resolved_accounting_disposition,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment

FROM analysis.v_certified_assistance_ledger l

LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = l.cfda_number
 AND l.action_date_fiscal_year >= m.valid_from_fiscal_year
 AND (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= m.valid_through_fiscal_year
     )

LEFT JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
 AND l.action_date_fiscal_year >= p.valid_from_fiscal_year
 AND (
        p.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= p.valid_through_fiscal_year
     )

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number = '86.001';


SELECT
    COALESCE(
        resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_disposition,

    COUNT(*) AS transaction_count,

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

FROM m195_effective

GROUP BY
    COALESCE(
        resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    )

ORDER BY effective_disposition;


/*
====================================================================================================
14. EXACT POST-MIGRATION CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EXACT POST-MIGRATION CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_tx          bigint;
    v_amount      numeric;
    v_covid       numeric;
    v_iija        numeric;
    v_extra       numeric;
    v_unresolved  bigint;
    v_policy_id   bigint;
BEGIN

    SELECT
        COUNT(*),

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
        ), 0),

        COUNT(*) FILTER
        (
            WHERE resolved_accounting_disposition IS DISTINCT FROM
                  'INCLUDE_ADDITIVE'
        ),

        MIN(federal_inflow_source_policy_id)

    INTO
        v_tx,
        v_amount,
        v_covid,
        v_iija,
        v_extra,
        v_unresolved,
        v_policy_id

    FROM m195_effective;


    IF v_tx <> 12 THEN
        RAISE EXCEPTION
            'ETL-195 POST-CONTROL FAILED: expected 12 transactions; found %',
            v_tx;
    END IF;


    IF ROUND(v_amount, 2) <> 989322322.39 THEN
        RAISE EXCEPTION
            'ETL-195 POST-CONTROL FAILED: expected amount 989322322.39; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 989322322.39 THEN
        RAISE EXCEPTION
            'ETL-195 POST-CONTROL FAILED: expected COVID 989322322.39; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-195 POST-CONTROL FAILED: expected IIJA 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 989322322.39 THEN
        RAISE EXCEPTION
            'ETL-195 POST-CONTROL FAILED: expected extraordinary 989322322.39; found %',
            ROUND(v_extra, 2);
    END IF;


    IF v_unresolved <> 0 THEN
        RAISE EXCEPTION
            'ETL-195 POST-CONTROL FAILED: % focal transactions are not INCLUDE_ADDITIVE',
            v_unresolved;
    END IF;


    IF v_policy_id IS NULL THEN
        RAISE EXCEPTION
            'ETL-195 POST-CONTROL FAILED: source policy ID is NULL';
    END IF;


    RAISE NOTICE
        'ETL-195 POST-CONTROL PASS: tx=% amount=% COVID=% IIJA=% extraordinary=% policy_id=%',
        v_tx,
        ROUND(v_amount, 2),
        ROUND(v_covid, 2),
        ROUND(v_iija, 2),
        ROUND(v_extra, 2),
        v_policy_id;

END
$$;


/*
====================================================================================================
15. FISCAL-YEAR POST-MIGRATION BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. FISCAL-YEAR POST-MIGRATION BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

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

FROM m195_effective

GROUP BY
    action_date_fiscal_year,
    resolved_accounting_disposition

ORDER BY
    action_date_fiscal_year,
    resolved_accounting_disposition;


/*
====================================================================================================
16. FINAL PERSISTED-OBJECT CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FINAL PERSISTED-OBJECT CERTIFICATION'
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
    c.methodology_version
        AS classification_methodology_version,

    m.federal_inflow_program_policy_mapping_id,
    m.resolved_accounting_disposition,
    m.methodology_version
        AS mapping_methodology_version

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id

JOIN reference.federal_inflow_program_classification c
  ON c.source_system = m.source_system
 AND c.source_program_code = m.source_program_code
 AND c.methodology_version = 'ANALYSIS-195-v1'

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '86.001'
  AND m.methodology_version = 'ANALYSIS-195-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id

    JOIN reference.federal_inflow_program_classification c
      ON c.source_system = m.source_system
     AND c.source_program_code = m.source_program_code
     AND c.methodology_version = 'ANALYSIS-195-v1'

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '86.001'
      AND m.methodology_version = 'ANALYSIS-195-v1'

      AND m.resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'

      AND p.inflow_family =
          'PENSION_ASSISTANCE'

      AND p.inflow_subfamily =
          'PBGC_SPECIAL_FINANCIAL_ASSISTANCE'

      AND p.accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'

      AND p.preferred_source =
          'USASPENDING_ASSISTANCE'

      AND p.allocation_source =
          'UNRESOLVED'

      AND p.ledger_treatment =
          'INCLUDE'

      AND c.overlap_risk =
          'NONE'

      AND c.covid_relevance =
          TRUE

      AND c.extraordinary_relevance =
          TRUE;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-195 FINAL CERTIFICATION FAILED: expected exactly 1 complete PBGC SFA policy chain; found %',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-195 FINAL CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
17. COMMIT
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-195 CERTIFICATION COMPLETE'
\echo ''
\echo 'AL 86.001'
\echo 'Pension Plan Termination Insurance'
\echo ''
\echo 'Empirically identified nonzero FY2020-FY2024 population:'
\echo '  PBGC Special Financial Assistance under ARPA / ERISA section 4262'
\echo ''
\echo 'Accounting treatment:'
\echo '  PENSION_ASSISTANCE'
\echo '  PBGC_SPECIAL_FINANCIAL_ASSISTANCE'
\echo '  NET_FEDERAL_ACTION_OBLIGATION'
\echo '  USASPENDING_ASSISTANCE'
\echo '  INCLUDE_ADDITIVE'
\echo ''
\echo 'Exact FY2020-FY2024 focal control:'
\echo '  Transactions        12'
\echo '  Awards               12'
\echo '  Recipients            3'
\echo '  Nonzero transactions  2'
\echo '  Net obligation   $989,322,322.39'
\echo '  COVID            $989,322,322.39'
\echo '  IIJA                       $0.00'
\echo '  Extraordinary     $989,322,322.39'
\echo ''
\echo 'Ten zero-dollar legacy loan observations preserved.'
\echo 'Downstream use of SFA assets is not a second federal inflow.'
\echo 'County incidence remains unresolved.'
\echo '===================================================================================================='
\echo ''

COMMIT;

\echo ''
\echo 'ETL-195 COMMIT COMPLETE'
\echo ''