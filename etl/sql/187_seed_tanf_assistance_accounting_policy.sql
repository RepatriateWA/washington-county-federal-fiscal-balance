/*
====================================================================================================
ETL-187
SEED TANF ASSISTANCE ACCOUNTING POLICY
====================================================================================================

Program:
    AL 93.558
    Temporary Assistance for Needy Families

Purpose:
    Encode the WCFFBP statewide accounting treatment for TANF assistance
    after successful ETL-186B profiling.

Accounting decision:
    Federal inflow family:
        INCOME_SECURITY_ASSISTANCE

    Federal inflow subfamily:
        TEMPORARY_ASSISTANCE_FOR_NEEDY_FAMILIES

    Preferred accounting source:
        USASPENDING_ASSISTANCE

    Accounting measure:
        NET_FEDERAL_ACTION_OBLIGATION

    Statewide accounting:
        INCLUDE_ADDITIVE

    County allocation:
        UNRESOLVED

    Initial federal-inflow overlap risk:
        NONE

Important downstream double-count rule:
    TANF funds may subsequently be transferred into or expended through
    other assistance programs. Such downstream use must not be treated as
    a second federal inflow if the underlying TANF federal transfer has
    already been counted here.

COVID / extraordinary provenance:
    Preserve existing transaction-level provenance.

Expected FY2020-FY2024 control:
    transactions       285
    awards              91
    recipients          12
    net obligations     $2,202,205,302.12
    COVID               $459,361,851.86
    IIJA                 $0.00
    extraordinary       $459,361,851.86

Expected post-ETL-187 bridge, assuming no higher-precedence mapping:
    INCLUDE_ADDITIVE
        56,214 transactions
        20 programs
        $63,148,717,534.63

    UNCLASSIFIED_REVIEW
        811,614 transactions
        1,271 programs
        $49,852,433,412.97

Methodology:
    ANALYSIS-187-v1

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-187 - SEED TANF ASSISTANCE ACCOUNTING POLICY'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. PRE-MIGRATION TANF CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION TANF CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m187_tanf_control;

CREATE TEMP TABLE m187_tanf_control AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year,
    federal_action_obligation,

    cfda_number,
    cfda_title,

    award_id_fain,
    award_id_uri,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,

    recipient_name,

    is_covid,
    is_iija,
    is_extraordinary

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.558';


SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT recipient_name
    ) AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m187_tanf_control;


DO $$
DECLARE
    v_transactions  bigint;
    v_awards        bigint;
    v_recipients    bigint;
    v_net           numeric;
    v_covid         numeric;
    v_iija          numeric;
    v_extraordinary numeric;
BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT source_award_identifier
        ),

        COUNT(
            DISTINCT recipient_name
        ),

        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

        COALESCE(
            SUM(
                CASE
                    WHEN is_covid
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE
                    WHEN is_iija
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE
                    WHEN is_extraordinary
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        )

    INTO
        v_transactions,
        v_awards,
        v_recipients,
        v_net,
        v_covid,
        v_iija,
        v_extraordinary

    FROM m187_tanf_control;


    IF v_transactions <> 285 THEN
        RAISE EXCEPTION
            'ETL-187 TANF transaction control failed: expected 285, found %',
            v_transactions;
    END IF;


    IF v_awards <> 91 THEN
        RAISE EXCEPTION
            'ETL-187 TANF award control failed: expected 91, found %',
            v_awards;
    END IF;


    IF v_recipients <> 12 THEN
        RAISE EXCEPTION
            'ETL-187 TANF recipient control failed: expected 12, found %',
            v_recipients;
    END IF;


    IF ROUND(v_net, 2) <> 2202205302.12 THEN
        RAISE EXCEPTION
            'ETL-187 TANF net control failed: expected 2202205302.12, found %',
            ROUND(v_net, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 459361851.86 THEN
        RAISE EXCEPTION
            'ETL-187 TANF COVID control failed: expected 459361851.86, found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-187 TANF IIJA control failed: expected 0.00, found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extraordinary, 2) <> 459361851.86 THEN
        RAISE EXCEPTION
            'ETL-187 TANF extraordinary control failed: expected 459361851.86, found %',
            ROUND(v_extraordinary, 2);
    END IF;


    RAISE NOTICE
        'ETL-187 PRE-MIGRATION TANF CONTROL PASS';

END
$$;


/*
====================================================================================================
2. PRECONDITION: TANF MUST NOT ALREADY HAVE THIS METHODOLOGY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. PRECONDITION CHECK'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.558'
      AND methodology_version = 'ANALYSIS-187-v1';


    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-187 precondition failed: ANALYSIS-187-v1 TANF mapping already exists (% rows)',
            v_count;
    END IF;


    RAISE NOTICE
        'ETL-187 PRECONDITION PASS';

END
$$;


/*
====================================================================================================
3. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. INSERT TANF SOURCE POLICY'
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
    'INCOME_SECURITY_ASSISTANCE',
    'TEMPORARY_ASSISTANCE_FOR_NEEDY_FAMILIES',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',
    'AL 93.558 TANF is treated as an additive federal-to-Washington assistance inflow. '
    || 'USAspending certified net federal action obligations are the preferred statewide accounting measure. '
    || 'No independent principal accounting source has been identified that creates a duplicate initial '
    || 'federal inflow pathway for this population. Downstream transfers or expenditures of TANF funds '
    || 'through other programs must not be counted as a second federal inflow. County incidence remains unresolved.',
    'ANALYSIS-187-v1',
    2020,
    2024
)
RETURNING
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    methodology_version;


/*
====================================================================================================
4. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. INSERT TANF PROGRAM CLASSIFICATION'
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
    '93.558',
    'Temporary Assistance for Needy Families',
    'INCOME_SECURITY_ASSISTANCE',
    'TEMPORARY_ASSISTANCE_FOR_NEEDY_FAMILIES',
    'NONE',
    TRUE,
    TRUE,
    'ETL-186B reproduced the certified FY2020-FY2024 TANF population at '
    || '285 transactions, 91 awards, 12 recipients, and $2,202,205,302.12 '
    || 'in net federal action obligations. $459,361,851.86 is COVID/extraordinary-tagged. '
    || 'TANF is a federal assistance/block-grant inflow. No duplicate principal accounting '
    || 'source has been identified for the initial federal-to-Washington transfer. '
    || 'Downstream TANF transfers remain subject to explicit double-count protection.',
    'ANALYSIS-187-v1',
    2020,
    2024
)
RETURNING
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version;


/*
====================================================================================================
5. INSERT PROGRAM -> POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. INSERT TANF PROGRAM-POLICY MAPPING'
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
    '93.558',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'AL 93.558 is included as additive statewide federal assistance inflow using '
    || 'certified USAspending net federal action obligations. County incidence remains unresolved. '
    || 'Any downstream expenditure or transfer of already-counted TANF funds must not be added again.',
    'ANALYSIS-187-v1',
    2020,
    2024

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'INCOME_SECURITY_ASSISTANCE'
  AND p.inflow_subfamily = 'TEMPORARY_ASSISTANCE_FOR_NEEDY_FAMILIES'
  AND p.methodology_version = 'ANALYSIS-187-v1';


/*
====================================================================================================
6. PERSISTENCE / UNIQUENESS CHECK
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. POLICY PERSISTENCE CHECK'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
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
  AND m.source_program_code = '93.558'
  AND m.methodology_version = 'ANALYSIS-187-v1';


DO $$
DECLARE
    v_policy_count         bigint;
    v_classification_count bigint;
    v_mapping_count        bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy_count

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'INCOME_SECURITY_ASSISTANCE'
      AND inflow_subfamily = 'TEMPORARY_ASSISTANCE_FOR_NEEDY_FAMILIES'
      AND methodology_version = 'ANALYSIS-187-v1';


    SELECT COUNT(*)
    INTO v_classification_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.558'
      AND methodology_version = 'ANALYSIS-187-v1';


    SELECT COUNT(*)
    INTO v_mapping_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.558'
      AND methodology_version = 'ANALYSIS-187-v1';


    IF v_policy_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-187 persistence failed: expected 1 TANF policy, found %',
            v_policy_count;
    END IF;


    IF v_classification_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-187 persistence failed: expected 1 TANF classification, found %',
            v_classification_count;
    END IF;


    IF v_mapping_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-187 persistence failed: expected 1 TANF mapping, found %',
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'ETL-187 POLICY PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
7. RECONSTRUCT EFFECTIVE ASSISTANCE ACCOUNTING RESOLUTION
====================================================================================================

Precedence:
    Award-level classification
        >
    Program-level mapping
        >
    UNCLASSIFIED_REVIEW

This reconstruction is independent of any cached post-migration result.

====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. RECONSTRUCT EFFECTIVE ASSISTANCE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m187_effective_resolution;

CREATE TEMP TABLE m187_effective_resolution AS
WITH ledger AS
(
    SELECT
        assistance_transaction_id,
        federal_action_obligation,
        cfda_number,
        award_id_fain,
        award_id_uri,

        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS source_award_identifier

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

award_resolution AS
(
    SELECT
        l.assistance_transaction_id,

        a.accounting_disposition AS resolved_accounting_disposition,

        ROW_NUMBER() OVER
        (
            PARTITION BY l.assistance_transaction_id

            ORDER BY
                a.federal_inflow_award_classification_id DESC
        ) AS rn

    FROM ledger l

    JOIN reference.federal_inflow_award_classification a
        ON a.source_system = 'USASPENDING_ASSISTANCE'
       AND a.source_award_identifier = l.source_award_identifier
       AND a.valid_from_fiscal_year <= 2024
       AND
       (
           a.valid_through_fiscal_year IS NULL
           OR a.valid_through_fiscal_year >= 2020
       )
),

program_resolution AS
(
    SELECT
        l.assistance_transaction_id,

        m.resolved_accounting_disposition,

        ROW_NUMBER() OVER
        (
            PARTITION BY l.assistance_transaction_id

            ORDER BY
                m.federal_inflow_program_policy_mapping_id DESC
        ) AS rn

    FROM ledger l

    JOIN reference.federal_inflow_program_policy_mapping m
        ON m.source_system = 'USASPENDING_ASSISTANCE'
       AND m.source_program_code = l.cfda_number
       AND m.valid_from_fiscal_year <= 2024
       AND
       (
           m.valid_through_fiscal_year IS NULL
           OR m.valid_through_fiscal_year >= 2020
       )
)

SELECT
    l.assistance_transaction_id,
    l.federal_action_obligation,
    l.cfda_number,

    CASE
        WHEN ar.assistance_transaction_id IS NOT NULL
            THEN 'AWARD'

        WHEN pr.assistance_transaction_id IS NOT NULL
            THEN 'PROGRAM'

        ELSE 'NONE'
    END AS resolution_level,

    COALESCE(
        ar.resolved_accounting_disposition,
        pr.resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS resolved_accounting_disposition

FROM ledger l

LEFT JOIN award_resolution ar
    ON ar.assistance_transaction_id
       = l.assistance_transaction_id
   AND ar.rn = 1

LEFT JOIN program_resolution pr
    ON pr.assistance_transaction_id
       = l.assistance_transaction_id
   AND pr.rn = 1;


/*
====================================================================================================
8. RESOLUTION UNIQUENESS / LEDGER CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. RESOLUTION UNIQUENESS / LEDGER CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS resolved_transaction_count,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transaction_count

FROM m187_effective_resolution;


DO $$
DECLARE
    v_resolved bigint;
    v_distinct bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id)

    INTO
        v_resolved,
        v_distinct

    FROM m187_effective_resolution;


    IF v_resolved <> v_distinct THEN
        RAISE EXCEPTION
            'ETL-187 resolution uniqueness failed: rows %, distinct transactions %',
            v_resolved,
            v_distinct;
    END IF;


    IF v_resolved <> 942243 THEN
        RAISE EXCEPTION
            'ETL-187 ledger closure failed: expected 942243 transactions, found %',
            v_resolved;
    END IF;


    RAISE NOTICE
        'ETL-187 RESOLUTION UNIQUENESS / LEDGER CLOSURE PASS';

END
$$;


/*
====================================================================================================
9. POST-MIGRATION ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. POST-ETL-187 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m187_effective_resolution

GROUP BY resolved_accounting_disposition

ORDER BY resolved_accounting_disposition;


/*
====================================================================================================
10. TANF EFFECTIVE RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. TANF EFFECTIVE RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_level,
    resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m187_effective_resolution

WHERE cfda_number = '93.558'

GROUP BY
    resolution_level,
    resolved_accounting_disposition

ORDER BY
    resolution_level,
    resolved_accounting_disposition;


/*
====================================================================================================
11. HARD POST-MIGRATION CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. HARD POST-MIGRATION CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_tanf_transactions bigint;
    v_tanf_amount       numeric;

    v_include_tx         bigint;
    v_include_programs   bigint;
    v_include_amount     numeric;

    v_unclassified_tx       bigint;
    v_unclassified_programs bigint;
    v_unclassified_amount   numeric;
BEGIN

    /*
    ------------------------------------------------------------------------------------------------
    TANF itself must resolve entirely to INCLUDE_ADDITIVE.
    ------------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_tanf_transactions,
        v_tanf_amount

    FROM m187_effective_resolution

    WHERE cfda_number = '93.558'
      AND resolved_accounting_disposition
          = 'INCLUDE_ADDITIVE';


    IF v_tanf_transactions <> 285 THEN
        RAISE EXCEPTION
            'ETL-187 TANF post-control failed: expected 285 INCLUDE_ADDITIVE transactions, found %',
            v_tanf_transactions;
    END IF;


    IF ROUND(v_tanf_amount, 2) <> 2202205302.12 THEN
        RAISE EXCEPTION
            'ETL-187 TANF post-control failed: expected 2202205302.12 INCLUDE_ADDITIVE, found %',
            ROUND(v_tanf_amount, 2);
    END IF;


    /*
    ------------------------------------------------------------------------------------------------
    INCLUDE_ADDITIVE expected bridge.
    ------------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_include_tx,
        v_include_programs,
        v_include_amount

    FROM m187_effective_resolution

    WHERE resolved_accounting_disposition
          = 'INCLUDE_ADDITIVE';


    IF v_include_tx <> 56214 THEN
        RAISE EXCEPTION
            'ETL-187 INCLUDE_ADDITIVE transaction bridge failed: expected 56214, found %',
            v_include_tx;
    END IF;


    IF v_include_programs <> 20 THEN
        RAISE EXCEPTION
            'ETL-187 INCLUDE_ADDITIVE program bridge failed: expected 20, found %',
            v_include_programs;
    END IF;


    IF ROUND(v_include_amount, 2)
       <> 63148717534.63 THEN

        RAISE EXCEPTION
            'ETL-187 INCLUDE_ADDITIVE amount bridge failed: expected 63148717534.63, found %',
            ROUND(v_include_amount, 2);
    END IF;


    /*
    ------------------------------------------------------------------------------------------------
    UNCLASSIFIED_REVIEW expected bridge.
    ------------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_unclassified_tx,
        v_unclassified_programs,
        v_unclassified_amount

    FROM m187_effective_resolution

    WHERE resolved_accounting_disposition
          = 'UNCLASSIFIED_REVIEW';


    IF v_unclassified_tx <> 811614 THEN
        RAISE EXCEPTION
            'ETL-187 UNCLASSIFIED transaction bridge failed: expected 811614, found %',
            v_unclassified_tx;
    END IF;


    IF v_unclassified_programs <> 1271 THEN
        RAISE EXCEPTION
            'ETL-187 UNCLASSIFIED program bridge failed: expected 1271, found %',
            v_unclassified_programs;
    END IF;


    IF ROUND(v_unclassified_amount, 2)
       <> 49852433412.97 THEN

        RAISE EXCEPTION
            'ETL-187 UNCLASSIFIED amount bridge failed: expected 49852433412.97, found %',
            ROUND(v_unclassified_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-187 HARD POST-MIGRATION CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
12. FINAL CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-187 CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'
\echo 'AL 93.558 TANF'
\echo 'Statewide disposition : INCLUDE_ADDITIVE'
\echo 'Preferred source       : USASPENDING_ASSISTANCE'
\echo 'Accounting measure     : NET_FEDERAL_ACTION_OBLIGATION'
\echo 'FY2020-FY2024 amount   : $2,202,205,302.12'
\echo 'COVID / extraordinary : $459,361,851.86'
\echo 'IIJA                    : $0.00'
\echo 'County allocation       : UNRESOLVED'
\echo ''
\echo 'IMPORTANT: downstream transfer/expenditure of already-counted TANF funds'
\echo 'must not be counted as a second federal inflow.'
\echo '----------------------------------------------------------------------------------------------------'
\echo 'ETL-187 PASS - COMMITTING'
\echo '===================================================================================================='
\echo ''

COMMIT;