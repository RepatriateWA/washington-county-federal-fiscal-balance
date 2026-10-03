/*
====================================================================================================
ETL-193
PROJECT-BASED RENTAL ASSISTANCE (PBRA)
ASSISTANCE ACCOUNTING POLICY
AL 14.195
====================================================================================================

Purpose:
    Resolve Washington FY2020-FY2024 USAspending Assistance Listing 14.195
    for statewide federal-inflow accounting.

Evidence:
    ETL-192A established:

        transactions                         9,620
        awards                               3,054
        recipients                             361
        net obligation          $1,097,139,340.00
        COVID                      $14,247,895.00
        IIJA                                $0.00
        extraordinary             $183,638,108.00

    Fiscal-year net obligations:

        FY2020                    $202,504,842.00
        FY2021                    $199,471,958.00
        FY2022                    $211,041,810.00
        FY2023                    $230,698,774.00
        FY2024                    $253,421,956.00

    Transaction signs:

        positive transactions               9,583
        positive obligations     $1,100,201,842.00

        negative transactions                  37
        negative obligations        -$3,062,502.00

PBRA / HCV distinction:
    ETL-192A established that AL 14.195 represents HUD project-based
    Section 8 Housing Assistance Payment contracts.

    AL 14.195 is distinct from the previously resolved Housing Choice
    Voucher program, AL 14.871.

    Mechanical award-ID collision test:
        shared PBRA / HCV award identifiers = 0

    References to Housing Choice Vouchers within PBRA award descriptions
    do not by themselves establish accounting overlap. Such language can
    describe project eligibility or tenant subsidy circumstances.

Accounting decision:
    - PBRA is genuine additive federal housing assistance to Washington.
    - USAspending assistance is the principal statewide accounting source.
    - Accounting measure is NET FEDERAL ACTION OBLIGATION.
    - No identified accounting overlap exists with AL 14.871.
    - County allocation remains unresolved.

PROVENANCE RULE:
    COVID, IIJA, and extraordinary status are orthogonal reporting
    dimensions and are not additional accounting paths.

    IIJA is explicitly controlled in this migration even though the
    certified AL 14.195 IIJA amount is zero.

DOUBLE-COUNT SAFEGUARD:
    Subsequent owner payments, rental subsidies, property-level
    distributions, reimbursements, or other downstream uses funded from
    already-counted AL 14.195 obligations are not second federal inflows.

Methodology:
    ANALYSIS-193-v1

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-193 - PBRA ASSISTANCE ACCOUNTING POLICY'
\echo 'AL 14.195'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. PRE-MIGRATION FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION FOCAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m193_pbra;

CREATE TEMP TABLE m193_pbra AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '14.195';


SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    COUNT(DISTINCT recipient_id) AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS extraordinary_amount

FROM m193_pbra;


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
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        ), 0)

    INTO
        v_tx,
        v_awards,
        v_recip,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m193_pbra;


    IF v_tx <> 9620
       OR v_awards <> 3054
       OR v_recip <> 361
       OR ROUND(v_amount, 2) <> 1097139340.00
       OR ROUND(v_covid, 2) <> 14247895.00
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 183638108.00 THEN

        RAISE EXCEPTION
            'ETL-193 focal control failed: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;

    RAISE NOTICE
        'ETL-193 PRE-MIGRATION FOCAL CONTROL PASS';
END
$$;


/*
====================================================================================================
2. FISCAL-YEAR CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FISCAL-YEAR CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation
FROM m193_pbra
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


DO $$
DECLARE
    v_2020 numeric;
    v_2021 numeric;
    v_2022 numeric;
    v_2023 numeric;
    v_2024 numeric;
BEGIN
    SELECT
        COALESCE(SUM(CASE WHEN action_date_fiscal_year = 2020
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN action_date_fiscal_year = 2021
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN action_date_fiscal_year = 2022
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN action_date_fiscal_year = 2023
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN action_date_fiscal_year = 2024
                          THEN federal_action_obligation ELSE 0 END), 0)

    INTO
        v_2020,
        v_2021,
        v_2022,
        v_2023,
        v_2024

    FROM m193_pbra;


    IF ROUND(v_2020, 2) <> 202504842.00
       OR ROUND(v_2021, 2) <> 199471958.00
       OR ROUND(v_2022, 2) <> 211041810.00
       OR ROUND(v_2023, 2) <> 230698774.00
       OR ROUND(v_2024, 2) <> 253421956.00 THEN

        RAISE EXCEPTION
            'ETL-193 fiscal-year control failed';
    END IF;

    RAISE NOTICE
        'ETL-193 FISCAL-YEAR CONTROL PASS';
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

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193_pbra
GROUP BY 1
ORDER BY 1;


DO $$
DECLARE
    v_positive_tx       bigint;
    v_positive_amount   numeric;
    v_negative_tx       bigint;
    v_negative_amount   numeric;
    v_zero_tx           bigint;
BEGIN
    SELECT
        COUNT(*) FILTER (
            WHERE federal_action_obligation > 0
        ),

        COALESCE(SUM(
            CASE WHEN federal_action_obligation > 0
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COUNT(*) FILTER (
            WHERE federal_action_obligation < 0
        ),

        COALESCE(SUM(
            CASE WHEN federal_action_obligation < 0
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COUNT(*) FILTER (
            WHERE federal_action_obligation = 0
        )

    INTO
        v_positive_tx,
        v_positive_amount,
        v_negative_tx,
        v_negative_amount,
        v_zero_tx

    FROM m193_pbra;


    IF v_positive_tx <> 9583
       OR ROUND(v_positive_amount, 2) <> 1100201842.00
       OR v_negative_tx <> 37
       OR ROUND(v_negative_amount, 2) <> -3062502.00
       OR v_zero_tx <> 0 THEN

        RAISE EXCEPTION
            'ETL-193 transaction-sign control failed';
    END IF;

    RAISE NOTICE
        'ETL-193 TRANSACTION-SIGN CONTROL PASS';
END
$$;


/*
====================================================================================================
4. PBRA / HCV AWARD COLLISION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PBRA / HCV AWARD COLLISION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_shared bigint;
BEGIN
    WITH pbra_awards AS
    (
        SELECT DISTINCT
            COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            ) AS award_identifier
        FROM m193_pbra
    ),

    hcv_awards AS
    (
        SELECT DISTINCT
            COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            ) AS award_identifier
        FROM analysis.v_certified_assistance_ledger
        WHERE reference_state_abbreviation = 'WA'
          AND action_date_fiscal_year BETWEEN 2020 AND 2024
          AND cfda_number = '14.871'
    )

    SELECT COUNT(*)
    INTO v_shared
    FROM pbra_awards p
    JOIN hcv_awards h
      ON h.award_identifier = p.award_identifier
    WHERE p.award_identifier IS NOT NULL;


    IF v_shared <> 0 THEN
        RAISE EXCEPTION
            'ETL-193 PBRA/HCV award collision control failed: % shared award identifier(s)',
            v_shared;
    END IF;

    RAISE NOTICE
        'ETL-193 PBRA/HCV AWARD COLLISION CONTROL PASS';
END
$$;


/*
====================================================================================================
5. HCV NON-INTERFERENCE CONTROL

The existing HCV policy must remain independently mapped as INCLUDE_ADDITIVE.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. HCV NON-INTERFERENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.ledger_treatment

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id
     = m.federal_inflow_source_policy_id

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '14.871';


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id
         = m.federal_inflow_source_policy_id

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '14.871'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND m.methodology_version = 'ANALYSIS-174B-5Y-v1'
      AND p.inflow_family = 'HOUSING_ASSISTANCE'
      AND p.inflow_subfamily = 'HOUSING_CHOICE_VOUCHERS'
      AND p.preferred_source = 'USASPENDING_ASSISTANCE'
      AND p.ledger_treatment = 'INCLUDE';


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-193 HCV non-interference pre-control failed';
    END IF;

    RAISE NOTICE
        'ETL-193 HCV NON-INTERFERENCE PRE-CONTROL PASS';
END
$$;


/*
====================================================================================================
6. PRE-EXISTING PBRA CLASSIFICATION / MAPPING CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. PRE-EXISTING PBRA CLASSIFICATION / MAPPING CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_classification_count bigint;
    v_mapping_count        bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_classification_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.195';

    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.195';


    IF v_classification_count <> 0
       OR v_mapping_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-193 refuses to proceed: existing PBRA classification %, mapping %',
            v_classification_count,
            v_mapping_count;
    END IF;

    RAISE NOTICE
        'ETL-193 PRE-EXISTING PBRA CONTROL PASS';
END
$$;


/*
====================================================================================================
7. INSERT PBRA SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. INSERT PBRA SOURCE POLICY'
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
    'HOUSING_ASSISTANCE',
    'PROJECT_BASED_RENTAL_ASSISTANCE',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'ETL-192A established AL 14.195 as additive federal Project-Based Rental Assistance to Washington. HUD Office of Multifamily Housing provides project-based Section 8 Housing Assistance Payment contracts directly with owners. AL 14.195 is distinct from Housing Choice Voucher AL 14.871; the FY2020-FY2024 PBRA/HCV award-identifier collision screen found zero shared identifiers. References to Housing Choice Vouchers in PBRA descriptions do not independently establish accounting overlap. USAspending net federal action obligation is the principal statewide accounting measure. COVID, IIJA, and extraordinary status are orthogonal provenance dimensions and not additional accounting paths. Later owner payments, rental subsidies, property-level distributions, reimbursements, or other downstream uses funded from already-counted AL 14.195 obligations are not second federal inflows. County allocation remains unresolved.',

    'ANALYSIS-193-v1',
    2020,
    2024

WHERE NOT EXISTS
(
    SELECT 1
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'HOUSING_ASSISTANCE'
      AND inflow_subfamily = 'PROJECT_BASED_RENTAL_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-193-v1'
);


/*
====================================================================================================
8. SOURCE POLICY PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. SOURCE POLICY PERSISTENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

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

WHERE inflow_family = 'HOUSING_ASSISTANCE'
  AND inflow_subfamily = 'PROJECT_BASED_RENTAL_ASSISTANCE'
  AND methodology_version = 'ANALYSIS-193-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'HOUSING_ASSISTANCE'
      AND inflow_subfamily = 'PROJECT_BASED_RENTAL_ASSISTANCE'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND allocation_source = 'UNRESOLVED'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-193-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-193 source-policy persistence failed';
    END IF;

    RAISE NOTICE
        'ETL-193 SOURCE POLICY PERSISTENCE PASS';
END
$$;


/*
====================================================================================================
9. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. INSERT PROGRAM CLASSIFICATION'
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
    '14.195',
    'Section 8 Housing Assistance Payments Program',
    'HOUSING_ASSISTANCE',
    'PROJECT_BASED_RENTAL_ASSISTANCE',
    'NONE',
    true,
    true,

    'ETL-192A established Washington FY2020-FY2024 AL 14.195 as HUD project-based Section 8 Housing Assistance Payment assistance: 9,620 transactions, 3,054 awards, 361 recipients, and $1,097,139,340.00 net obligations. The population contains $14,247,895.00 COVID, $0.00 IIJA, and $183,638,108.00 extraordinary obligations. PBRA is distinct from AL 14.871 Housing Choice Vouchers; the award-identifier collision screen found zero shared identifiers. No separate principal accounting source was identified that already captures these PBRA obligations.',

    'ANALYSIS-193-v1',
    2020,
    2024
);


/*
====================================================================================================
10. PROGRAM CLASSIFICATION PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. PROGRAM CLASSIFICATION PERSISTENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

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
  AND source_program_code = '14.195'
  AND methodology_version = 'ANALYSIS-193-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.195'
      AND methodology_version = 'ANALYSIS-193-v1'
      AND inflow_family = 'HOUSING_ASSISTANCE'
      AND inflow_subfamily = 'PROJECT_BASED_RENTAL_ASSISTANCE'
      AND overlap_risk = 'NONE'
      AND covid_relevance = true
      AND extraordinary_relevance = true;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-193 program-classification persistence failed';
    END IF;

    RAISE NOTICE
        'ETL-193 PROGRAM CLASSIFICATION PERSISTENCE PASS';
END
$$;


/*
====================================================================================================
11. INSERT PROGRAM POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. INSERT PROGRAM POLICY MAPPING'
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
    '14.195',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'AL 14.195 PBRA is additive federal housing assistance on the WCFFBP net-obligation basis. It is distinct from AL 14.871 Housing Choice Vouchers. COVID, IIJA, and extraordinary status remain orthogonal provenance dimensions. Downstream use of already-counted PBRA obligations is not a second federal inflow.',

    'ANALYSIS-193-v1',
    2020,
    2024

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'HOUSING_ASSISTANCE'
  AND p.inflow_subfamily = 'PROJECT_BASED_RENTAL_ASSISTANCE'
  AND p.methodology_version = 'ANALYSIS-193-v1';


/*
====================================================================================================
12. PROGRAM POLICY MAPPING PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. PROGRAM POLICY MAPPING PERSISTENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id
     = m.federal_inflow_source_policy_id

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '14.195'
  AND m.methodology_version = 'ANALYSIS-193-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id
         = m.federal_inflow_source_policy_id

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '14.195'
      AND m.methodology_version = 'ANALYSIS-193-v1'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND p.inflow_family = 'HOUSING_ASSISTANCE'
      AND p.inflow_subfamily = 'PROJECT_BASED_RENTAL_ASSISTANCE'
      AND p.accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND p.preferred_source = 'USASPENDING_ASSISTANCE'
      AND p.allocation_source = 'UNRESOLVED'
      AND p.ledger_treatment = 'INCLUDE';


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-193 program-policy mapping persistence failed';
    END IF;

    RAISE NOTICE
        'ETL-193 PROGRAM POLICY MAPPING PERSISTENCE PASS';
END
$$;


/*
====================================================================================================
13. HCV POST-INSERT NON-INTERFERENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. HCV POST-INSERT NON-INTERFERENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping m

    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id
         = m.federal_inflow_source_policy_id

    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '14.871'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND m.methodology_version = 'ANALYSIS-174B-5Y-v1'
      AND p.inflow_family = 'HOUSING_ASSISTANCE'
      AND p.inflow_subfamily = 'HOUSING_CHOICE_VOUCHERS'
      AND p.preferred_source = 'USASPENDING_ASSISTANCE'
      AND p.ledger_treatment = 'INCLUDE';


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-193 HCV post-insert non-interference failed';
    END IF;

    RAISE NOTICE
        'ETL-193 HCV POST-INSERT NON-INTERFERENCE PASS';
END
$$;


/*
====================================================================================================
14. EFFECTIVE PBRA RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EFFECTIVE PBRA RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m193_effective;

CREATE TEMP TABLE m193_effective AS

SELECT
    b.assistance_transaction_id,
    b.action_date_fiscal_year,
    b.federal_action_obligation,
    b.is_covid,
    b.is_iija,
    b.is_extraordinary,

    m.resolved_accounting_disposition
        AS accounting_disposition

FROM m193_pbra b

LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = '14.195'
 AND m.methodology_version = 'ANALYSIS-193-v1';


SELECT
    accounting_disposition,

    COUNT(*) AS transaction_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS extraordinary_amount

FROM m193_effective

GROUP BY accounting_disposition
ORDER BY accounting_disposition;


/*
====================================================================================================
15. EFFECTIVE RESOLUTION HARD CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. EFFECTIVE RESOLUTION HARD CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_rows       bigint;
    v_distinct   bigint;
    v_additive   bigint;
    v_null       bigint;
    v_amount     numeric;
    v_covid      numeric;
    v_iija       numeric;
    v_extra      numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),

        COUNT(*) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ),

        COUNT(*) FILTER (
            WHERE accounting_disposition IS NULL
        ),

        COALESCE(SUM(
            CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                       AND is_covid
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                       AND is_iija
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                       AND is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        ), 0)

    INTO
        v_rows,
        v_distinct,
        v_additive,
        v_null,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m193_effective;


    IF v_rows <> 9620
       OR v_distinct <> 9620
       OR v_additive <> 9620
       OR v_null <> 0
       OR ROUND(v_amount, 2) <> 1097139340.00
       OR ROUND(v_covid, 2) <> 14247895.00
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 183638108.00 THEN

        RAISE EXCEPTION
            'ETL-193 effective resolution failed: rows %, distinct %, additive %, null %, amount %, COVID %, IIJA %, extraordinary %',
            v_rows,
            v_distinct,
            v_additive,
            v_null,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;

    RAISE NOTICE
        'ETL-193 EFFECTIVE RESOLUTION HARD CONTROL PASS';
END
$$;


/*
====================================================================================================
16. FINAL CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FINAL CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS focal_transactions,

    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_focal_transactions,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS focal_net_obligation,

    COUNT(*) FILTER (
        WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
    ) AS additive_transactions,

    ROUND(SUM(
        CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS additive_net_obligation,

    ROUND(SUM(
        CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                  AND is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS additive_covid,

    ROUND(SUM(
        CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                  AND is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS additive_iija,

    ROUND(SUM(
        CASE WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                  AND is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS additive_extraordinary

FROM m193_effective;


DO $$
BEGIN
    RAISE NOTICE
        'ETL-193 HARD CERTIFICATION PASS';
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-193 COMPLETE'
\echo ''
\echo 'Expected accounting result:'
\echo '  AL 14.195 focal amount          $1,097,139,340.00'
\echo '  INCLUDE_ADDITIVE                $1,097,139,340.00'
\echo '  COVID                              $14,247,895.00'
\echo '  IIJA                                        $0.00'
\echo '  Extraordinary                     $183,638,108.00'
\echo '  PBRA/HCV shared award IDs                     0'
\echo '  Overlap risk                                NONE'
\echo '  County-incidence decision                   NONE'
\echo ''
\echo 'PROVENANCE RULE:'
\echo 'COVID / IIJA / extraordinary are reporting dimensions,'
\echo 'not additional additive accounting paths.'
\echo '===================================================================================================='
\echo ''

COMMIT;