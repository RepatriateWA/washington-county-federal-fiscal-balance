/*
====================================================================================================
ETL-192
BROADBAND EQUITY, ACCESS, AND DEPLOYMENT (BEAD)
ASSISTANCE ACCOUNTING POLICY
AL 11.035
====================================================================================================

Purpose:
    Resolve Washington FY2020-FY2024 USAspending Assistance Listing 11.035
    (Broadband Equity, Access, and Deployment / BEAD) for statewide
    federal-inflow accounting.

Evidence:
    ETL-191A established:

        transactions                         4
        awards                               2
        recipients                           1
        net obligation       $1,227,742,066.00
        COVID                            $0.00
        IIJA                 $1,227,742,066.00
        extraordinary        $1,227,742,066.00

    Fiscal-year profile:

        FY2023                   $5,000,000.00
        FY2024               $1,222,742,066.00

    Transaction structure:
        - Initial $5 million planning obligation.
        - Subsequent +$5 million / -$5 million award-identifier transition.
        - $1.222742066 billion obligation recorded 2024-06-07.
        - Net accounting eliminates the internal +$5M/-$5M movement.

Accounting decision:
    - BEAD is genuine additive federal assistance to Washington.
    - USAspending assistance is the principal statewide accounting source.
    - Accounting measure is NET FEDERAL ACTION OBLIGATION.
    - Entire focal amount is IIJA and extraordinary.
    - No identified overlap pathway exists with another WCFFBP principal
      accounting source.
    - County allocation remains unresolved.

IMPORTANT TIMING INTERPRETATION:
    WCFFBP recognizes BEAD in the assistance ledger when the federal
    obligation is recorded.

    Recognition DOES NOT imply that the same amount was:
        - disbursed,
        - drawn down,
        - expended,
        - subawarded,
        - paid to contractors,
        - or economically incident in Washington

    during the same fiscal year.

    In particular, the FY2024 $1.222742066 billion observation is an
    obligation associated with BEAD Initial Proposal funding and must not
    be described as $1.222742066 billion of FY2024 Washington expenditure.

DOUBLE-COUNT SAFEGUARD:
    Later BEAD subawards, state distributions, reimbursements, contractor
    payments, expenditures, or other downstream uses funded from this
    already-counted federal obligation are not second federal inflows.

Methodology:
    ANALYSIS-192-v1

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-192 - BEAD ASSISTANCE ACCOUNTING POLICY'
\echo 'AL 11.035'
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

DROP TABLE IF EXISTS pg_temp.m192_bead;

CREATE TEMP TABLE m192_bead AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '11.035';


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

FROM m192_bead;


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

        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

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

    FROM m192_bead;


    IF v_tx <> 4
       OR v_awards <> 2
       OR v_recip <> 1
       OR ROUND(v_amount, 2) <> 1227742066.00
       OR ROUND(v_covid, 2) <> 0.00
       OR ROUND(v_iija, 2) <> 1227742066.00
       OR ROUND(v_extra, 2) <> 1227742066.00 THEN

        RAISE EXCEPTION
            'ETL-192 focal control failed: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);

    END IF;


    RAISE NOTICE
        'ETL-192 PRE-MIGRATION FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
2. FISCAL-YEAR TIMING CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FISCAL-YEAR TIMING CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m192_bead

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


DO $$
DECLARE
    v_2023 numeric;
    v_2024 numeric;
BEGIN

    SELECT
        COALESCE(SUM(
            CASE
                WHEN action_date_fiscal_year = 2023
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN action_date_fiscal_year = 2024
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_2023,
        v_2024

    FROM m192_bead;


    IF ROUND(v_2023, 2) <> 5000000.00
       OR ROUND(v_2024, 2) <> 1222742066.00 THEN

        RAISE EXCEPTION
            'ETL-192 fiscal-year timing control failed: FY2023 %, FY2024 %',
            ROUND(v_2023, 2),
            ROUND(v_2024, 2);

    END IF;


    RAISE NOTICE
        'ETL-192 FISCAL-YEAR TIMING CONTROL PASS';

END
$$;


/*
====================================================================================================
3. TRANSACTION-SIGN CONTROL

The +$5M / -$5M history is why BEAD must be accounted on a NET obligation basis.
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

FROM m192_bead

GROUP BY 1

ORDER BY 1;


DO $$
DECLARE
    v_positive_tx       bigint;
    v_positive_amount   numeric;
    v_negative_tx       bigint;
    v_negative_amount   numeric;
BEGIN

    SELECT
        COUNT(*) FILTER (
            WHERE federal_action_obligation > 0
        ),

        COALESCE(SUM(
            CASE
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COUNT(*) FILTER (
            WHERE federal_action_obligation < 0
        ),

        COALESCE(SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_positive_tx,
        v_positive_amount,
        v_negative_tx,
        v_negative_amount

    FROM m192_bead;


    IF v_positive_tx <> 3
       OR ROUND(v_positive_amount, 2) <> 1232742066.00
       OR v_negative_tx <> 1
       OR ROUND(v_negative_amount, 2) <> -5000000.00 THEN

        RAISE EXCEPTION
            'ETL-192 transaction-sign control failed';

    END IF;


    RAISE NOTICE
        'ETL-192 TRANSACTION-SIGN CONTROL PASS';

END
$$;


/*
====================================================================================================
4. LARGE FY2024 OBLIGATION CONTROL

Preserve the exact observation that creates the material timing issue.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. LARGE FY2024 OBLIGATION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date,
    action_date_fiscal_year AS fiscal_year,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,

    recipient_name,

    ROUND(
        federal_action_obligation::numeric,
        2
    ) AS federal_action_obligation,

    is_iija,
    is_extraordinary,
    transaction_description

FROM m192_bead

WHERE federal_action_obligation = 1222742066.00;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM m192_bead

    WHERE action_date = DATE '2024-06-07'
      AND action_date_fiscal_year = 2024
      AND federal_action_obligation = 1222742066.00
      AND is_iija = true
      AND is_extraordinary = true;


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-192 large FY2024 obligation control failed: expected 1 row, found %',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-192 LARGE FY2024 OBLIGATION CONTROL PASS';

END
$$;


/*
====================================================================================================
5. PRE-EXISTING PROGRAM CLASSIFICATION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. PRE-EXISTING PROGRAM CLASSIFICATION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '11.035';


    IF v_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-192 refuses to proceed: 11.035 already has % classification row(s)',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-192 PRE-EXISTING PROGRAM CLASSIFICATION CONTROL PASS';

END
$$;


/*
====================================================================================================
6. PRE-EXISTING PROGRAM POLICY MAPPING CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. PRE-EXISTING PROGRAM POLICY MAPPING CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '11.035';


    IF v_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-192 refuses to proceed: 11.035 already has % policy mapping row(s)',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-192 PRE-EXISTING PROGRAM POLICY MAPPING CONTROL PASS';

END
$$;


/*
====================================================================================================
7. INSERT BEAD SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. INSERT BEAD SOURCE POLICY'
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
    'BROADBAND_ASSISTANCE',
    'BEAD',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'ETL-191A established AL 11.035 BEAD as additive federal broadband assistance to Washington. USAspending net federal action obligation is the principal statewide accounting measure. The FY2024 $1.222742066 billion transaction is an obligation associated with Initial Proposal funding; recognition in the WCFFBP assistance ledger does not imply that the same amount was disbursed, drawn down, expended, subawarded, paid to contractors, or economically incident in Washington during FY2024. Later BEAD subawards, state distributions, reimbursements, contractor payments, expenditures, or other downstream uses funded from this already-counted federal obligation are not second federal inflows. The focal population is entirely IIJA and extraordinary. No identified overlap pathway exists with another WCFFBP principal accounting source. County allocation remains unresolved.',

    'ANALYSIS-192-v1',
    2020,
    2024

WHERE NOT EXISTS
(
    SELECT 1

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'BROADBAND_ASSISTANCE'
      AND inflow_subfamily = 'BEAD'
      AND methodology_version = 'ANALYSIS-192-v1'
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

WHERE inflow_family = 'BROADBAND_ASSISTANCE'
  AND inflow_subfamily = 'BEAD'
  AND methodology_version = 'ANALYSIS-192-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'BROADBAND_ASSISTANCE'
      AND inflow_subfamily = 'BEAD'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND allocation_source = 'UNRESOLVED'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-192-v1';


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-192 source-policy persistence failed';

    END IF;


    RAISE NOTICE
        'ETL-192 SOURCE POLICY PERSISTENCE PASS';

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
    '11.035',
    'Broadband Equity, Access, and Deployment Program',
    'BROADBAND_ASSISTANCE',
    'BEAD',
    'NONE',
    false,
    true,

    'ETL-191A profiled Washington FY2020-FY2024 AL 11.035: 4 transactions, 2 award identifiers, 1 recipient, and $1,227,742,066.00 net federal action obligations. The population is entirely IIJA and extraordinary. The Washington State Department of Commerce is the sole recipient. The large FY2024 observation is Initial Proposal funding and creates a material obligation-versus-expenditure timing distinction, but no identified overlap pathway exists with another WCFFBP principal accounting source.',

    'ANALYSIS-192-v1',
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
  AND source_program_code = '11.035'
  AND methodology_version = 'ANALYSIS-192-v1';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '11.035'
      AND methodology_version = 'ANALYSIS-192-v1'
      AND inflow_family = 'BROADBAND_ASSISTANCE'
      AND inflow_subfamily = 'BEAD'
      AND overlap_risk = 'NONE'
      AND covid_relevance = false
      AND extraordinary_relevance = true;


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-192 program-classification persistence failed';

    END IF;


    RAISE NOTICE
        'ETL-192 PROGRAM CLASSIFICATION PERSISTENCE PASS';

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
    '11.035',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'AL 11.035 BEAD is additive federal assistance on the WCFFBP net-obligation accounting basis. Recognition follows the federal obligation action and does not assert same-year cash disbursement, expenditure, subaward, contractor payment, or economic incidence. Later downstream uses of this already-counted BEAD obligation are not second federal inflows.',

    'ANALYSIS-192-v1',
    2020,
    2024

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'BROADBAND_ASSISTANCE'
  AND p.inflow_subfamily = 'BEAD'
  AND p.methodology_version = 'ANALYSIS-192-v1';


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
  AND m.source_program_code = '11.035'
  AND m.methodology_version = 'ANALYSIS-192-v1';


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
      AND m.source_program_code = '11.035'
      AND m.methodology_version = 'ANALYSIS-192-v1'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND p.inflow_family = 'BROADBAND_ASSISTANCE'
      AND p.inflow_subfamily = 'BEAD'
      AND p.accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND p.preferred_source = 'USASPENDING_ASSISTANCE'
      AND p.allocation_source = 'UNRESOLVED'
      AND p.ledger_treatment = 'INCLUDE';


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-192 program-policy mapping persistence failed';

    END IF;


    RAISE NOTICE
        'ETL-192 PROGRAM POLICY MAPPING PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
13. EFFECTIVE BEAD RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EFFECTIVE BEAD RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m192_effective;

CREATE TEMP TABLE m192_effective AS

SELECT
    b.assistance_transaction_id,
    b.action_date_fiscal_year,
    b.federal_action_obligation,
    b.is_covid,
    b.is_iija,
    b.is_extraordinary,

    m.resolved_accounting_disposition
        AS accounting_disposition

FROM m192_bead b

LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = '11.035'
 AND m.methodology_version = 'ANALYSIS-192-v1';


SELECT
    accounting_disposition,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

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

FROM m192_effective

GROUP BY accounting_disposition

ORDER BY accounting_disposition;


/*
====================================================================================================
14. EFFECTIVE RESOLUTION HARD CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EFFECTIVE RESOLUTION HARD CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_rows       bigint;
    v_distinct   bigint;
    v_additive   bigint;
    v_null       bigint;
    v_amount     numeric;
    v_iija       numeric;
    v_extra      numeric;
BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT assistance_transaction_id
        ),

        COUNT(*) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ),

        COUNT(*) FILTER (
            WHERE accounting_disposition IS NULL
        ),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                 AND is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                 AND is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_rows,
        v_distinct,
        v_additive,
        v_null,
        v_amount,
        v_iija,
        v_extra

    FROM m192_effective;


    IF v_rows <> 4
       OR v_distinct <> 4
       OR v_additive <> 4
       OR v_null <> 0
       OR ROUND(v_amount, 2) <> 1227742066.00
       OR ROUND(v_iija, 2) <> 1227742066.00
       OR ROUND(v_extra, 2) <> 1227742066.00 THEN

        RAISE EXCEPTION
            'ETL-192 effective resolution failed: rows %, distinct %, additive %, null %, amount %, IIJA %, extraordinary %',
            v_rows,
            v_distinct,
            v_additive,
            v_null,
            ROUND(v_amount, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);

    END IF;


    RAISE NOTICE
        'ETL-192 EFFECTIVE RESOLUTION HARD CONTROL PASS';

END
$$;


/*
====================================================================================================
15. FINAL CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. FINAL CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS focal_transactions,

    COUNT(
        DISTINCT assistance_transaction_id
    ) AS distinct_focal_transactions,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS focal_net_obligation,

    COUNT(*) FILTER (
        WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
    ) AS additive_transactions,

    ROUND(SUM(
        CASE
            WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS additive_net_obligation,

    ROUND(SUM(
        CASE
            WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
             AND action_date_fiscal_year = 2023
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS additive_fy2023,

    ROUND(SUM(
        CASE
            WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
             AND action_date_fiscal_year = 2024
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS additive_fy2024

FROM m192_effective;


DO $$
BEGIN

    RAISE NOTICE
        'ETL-192 HARD CERTIFICATION PASS';

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-192 COMPLETE'
\echo ''
\echo 'Expected accounting result:'
\echo '  AL 11.035 focal amount          $1,227,742,066.00'
\echo '  INCLUDE_ADDITIVE                $1,227,742,066.00'
\echo '  FY2023                              $5,000,000.00'
\echo '  FY2024                          $1,222,742,066.00'
\echo '  IIJA / extraordinary            $1,227,742,066.00'
\echo '  COVID                                       $0.00'
\echo '  Overlap risk                                NONE'
\echo '  County-incidence decision                   NONE'
\echo ''
\echo 'IMPORTANT: FY2024 amount is an OBLIGATION measure.'
\echo 'It is not asserted to be FY2024 cash expenditure or economic incidence.'
\echo '===================================================================================================='
\echo ''

COMMIT;