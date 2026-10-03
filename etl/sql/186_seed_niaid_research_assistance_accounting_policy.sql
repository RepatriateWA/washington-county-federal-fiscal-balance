/*
====================================================================================================
MIGRATION 186
SEED NIAID / ALLERGY AND INFECTIOUS DISEASES RESEARCH ASSISTANCE ACCOUNTING POLICY
====================================================================================================

Methodology:
    ANALYSIS-185B-v1

Program:
    USAspending Assistance Listing 93.855
    ALLERGY AND INFECTIOUS DISEASES RESEARCH

Accounting conclusion:
    INCLUDE_ADDITIVE

Principal accounting source:
    USASPENDING_ASSISTANCE

Accounting measure:
    NET_FEDERAL_ACTION_OBLIGATION

Overlap assessment:
    No identified plausible overlap pathway with an independently acquired
    WCFFBP principal accounting source.

    The program is federal research assistance funded through HHS.
    ETL-185B identified no database evidence requiring deeper reconciliation.

Statewide accounting control, FFY2020-FFY2024:
    transactions       3,361
    awards               812
    recipients            41
    net obligations     $2,385,155,445.79
    COVID               $1,466,316,577.46
    IIJA                         $0.00
    extraordinary       $1,466,316,577.46

County allocation:
    UNRESOLVED

Expected post-M186 unresolved bridge:
    transactions       811,899
    programs             1,272
    net obligations     $52,054,638,715.09

IMPORTANT:
    Statewide accounting inclusion does not constitute a county-incidence
    allocation decision.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 186 - NIAID RESEARCH ASSISTANCE ACCOUNTING POLICY'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. PRE-MIGRATION FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION AL 93.855 CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186_focal;

CREATE TEMP TABLE m186_focal AS
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
  AND cfda_number = '93.855';


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

FROM m186_focal;


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

    FROM m186_focal;


    IF v_transactions <> 3361 THEN
        RAISE EXCEPTION
            'M186 transaction control failed: expected 3361, found %',
            v_transactions;
    END IF;


    IF v_awards <> 812 THEN
        RAISE EXCEPTION
            'M186 award control failed: expected 812, found %',
            v_awards;
    END IF;


    IF v_recipients <> 41 THEN
        RAISE EXCEPTION
            'M186 recipient control failed: expected 41, found %',
            v_recipients;
    END IF;


    IF ROUND(v_net, 2) <> 2385155445.79 THEN
        RAISE EXCEPTION
            'M186 net control failed: expected 2385155445.79, found %',
            ROUND(v_net, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 1466316577.46 THEN
        RAISE EXCEPTION
            'M186 COVID control failed: expected 1466316577.46, found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'M186 IIJA control failed: expected 0.00, found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extraordinary, 2) <> 1466316577.46 THEN
        RAISE EXCEPTION
            'M186 extraordinary control failed: expected 1466316577.46, found %',
            ROUND(v_extraordinary, 2);
    END IF;


    RAISE NOTICE
        'M186 PRE-MIGRATION FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
2. SEED SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. SEED FEDERAL INFLOW SOURCE POLICY'
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
    'RESEARCH_ASSISTANCE',
    'ALLERGY_INFECTIOUS_DISEASE_RESEARCH',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'AL 93.855 is federal research assistance funded through HHS. '
    || 'ETL-185B confirmed the focal USAspending population and identified '
    || 'no plausible overlap pathway with an independently acquired WCFFBP '
    || 'principal accounting source. USAspending net federal action '
    || 'obligation is therefore the principal statewide accounting measure. '
    || 'COVID and extraordinary provenance are retained. County incidence '
    || 'remains unresolved.',

    'ANALYSIS-185B-v1',
    2020,
    2024
)
ON CONFLICT DO NOTHING;


/*
====================================================================================================
3. RESOLVE POLICY ID
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. RESOLVE SOURCE POLICY ID'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186_policy;

CREATE TEMP TABLE m186_policy AS
SELECT
    federal_inflow_source_policy_id

FROM reference.federal_inflow_source_policy

WHERE inflow_family =
        'RESEARCH_ASSISTANCE'

  AND inflow_subfamily =
        'ALLERGY_INFECTIOUS_DISEASE_RESEARCH'

  AND accounting_measure =
        'NET_FEDERAL_ACTION_OBLIGATION'

  AND preferred_source =
        'USASPENDING_ASSISTANCE'

  AND methodology_version =
        'ANALYSIS-185B-v1'

  AND valid_from_fiscal_year = 2020

  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m186_policy;


    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'M186 source policy resolution failed: expected 1 row, found %',
            v_count;
    END IF;


    RAISE NOTICE
        'M186 SOURCE POLICY RESOLUTION PASS';

END
$$;


SELECT
    federal_inflow_source_policy_id

FROM m186_policy;


/*
====================================================================================================
4. SEED PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. SEED PROGRAM CLASSIFICATION'
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
    '93.855',
    'Allergy and Infectious Diseases Research',

    'RESEARCH_ASSISTANCE',
    'ALLERGY_INFECTIOUS_DISEASE_RESEARCH',

    'NONE',

    TRUE,
    TRUE,

    'ETL-185B confirmed 3,361 transactions, 812 awards, 41 recipients, '
    || '$2,385,155,445.79 net federal action obligations, '
    || '$1,466,316,577.46 COVID-tagged obligations, and '
    || '$1,466,316,577.46 extraordinary-tagged obligations for '
    || 'Washington FFY2020-FFY2024. All focal obligations were funded '
    || 'through HHS. No identified plausible overlap pathway requires '
    || 'reconciliation with an independently acquired WCFFBP principal '
    || 'accounting source.',

    'ANALYSIS-185B-v1',

    2020,
    2024
)
ON CONFLICT
(
    source_system,
    source_program_code,
    methodology_version
)
DO NOTHING;


/*
====================================================================================================
5. SEED PROGRAM -> POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. SEED PROGRAM POLICY MAPPING'
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
    '93.855',

    p.federal_inflow_source_policy_id,

    'INCLUDE_ADDITIVE',

    'AL 93.855 is treated as additive federal research assistance. '
    || 'USAspending net federal action obligation is the principal '
    || 'statewide accounting measure. No identified principal-source '
    || 'overlap pathway requires exclusion or reconciliation.',

    'ANALYSIS-185B-v1',

    2020,
    2024

FROM m186_policy p

ON CONFLICT
(
    source_system,
    source_program_code,
    methodology_version
)
DO NOTHING;


/*
====================================================================================================
6. PERSISTENCE CHECK
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. PERSISTENCE CHECK'
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

WHERE methodology_version =
    'ANALYSIS-185B-v1';


SELECT
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

WHERE source_system =
        'USASPENDING_ASSISTANCE'

  AND source_program_code =
        '93.855'

  AND methodology_version =
        'ANALYSIS-185B-v1';


SELECT
    m.source_system,
    m.source_program_code,
    m.federal_inflow_source_policy_id,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping m

WHERE m.source_system =
        'USASPENDING_ASSISTANCE'

  AND m.source_program_code =
        '93.855'

  AND m.methodology_version =
        'ANALYSIS-185B-v1';


DO $$
DECLARE
    v_policy_count         bigint;
    v_classification_count bigint;
    v_mapping_count        bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy_count

    FROM reference.federal_inflow_source_policy

    WHERE methodology_version =
        'ANALYSIS-185B-v1'

      AND inflow_family =
        'RESEARCH_ASSISTANCE'

      AND inflow_subfamily =
        'ALLERGY_INFECTIOUS_DISEASE_RESEARCH';


    SELECT COUNT(*)
    INTO v_classification_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system =
            'USASPENDING_ASSISTANCE'

      AND source_program_code =
            '93.855'

      AND methodology_version =
            'ANALYSIS-185B-v1';


    SELECT COUNT(*)
    INTO v_mapping_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system =
            'USASPENDING_ASSISTANCE'

      AND source_program_code =
            '93.855'

      AND methodology_version =
            'ANALYSIS-185B-v1';


    IF v_policy_count <> 1 THEN
        RAISE EXCEPTION
            'M186 persistence failed: source policy count=%',
            v_policy_count;
    END IF;


    IF v_classification_count <> 1 THEN
        RAISE EXCEPTION
            'M186 persistence failed: program classification count=%',
            v_classification_count;
    END IF;


    IF v_mapping_count <> 1 THEN
        RAISE EXCEPTION
            'M186 persistence failed: program mapping count=%',
            v_mapping_count;
    END IF;


    RAISE NOTICE
        'M186 PERSISTENCE CHECK PASS';

END
$$;


/*
====================================================================================================
7. RECONSTRUCT COMPLETE ASSISTANCE ACCOUNTING BRIDGE

Established precedence:

    AWARD CLASSIFICATION
        >
    PROGRAM POLICY MAPPING
        >
    UNCLASSIFIED_REVIEW

This independently reconstructs the effective bridge after the new mapping.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. RECONSTRUCT POST-M186 ASSISTANCE ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186_ledger;

CREATE TEMP TABLE m186_ledger AS
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
    ) AS source_award_identifier

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


DROP TABLE IF EXISTS pg_temp.m186_award_matches;

CREATE TEMP TABLE m186_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM m186_ledger l

JOIN reference.federal_inflow_award_classification a
  ON a.source_system =
        'USASPENDING_ASSISTANCE'

 AND a.source_program_code =
        l.cfda_number

 AND a.source_award_identifier =
        l.source_award_identifier

WHERE
    (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
            a.valid_from_fiscal_year
    )

AND
    (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
            a.valid_through_fiscal_year
    );


DROP TABLE IF EXISTS pg_temp.m186_program_matches;

CREATE TEMP TABLE m186_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM m186_ledger l

JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system =
        'USASPENDING_ASSISTANCE'

 AND m.source_program_code =
        l.cfda_number

WHERE
    (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
            m.valid_from_fiscal_year
    )

AND
    (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
            m.valid_through_fiscal_year
    );


/*
====================================================================================================
8. RESOLUTION UNIQUENESS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. RESOLUTION UNIQUENESS CHECK'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_duplicate_award_matches   bigint;
    v_duplicate_program_matches bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_duplicate_award_matches

    FROM
    (
        SELECT
            assistance_transaction_id

        FROM m186_award_matches

        GROUP BY assistance_transaction_id

        HAVING COUNT(*) > 1
    ) x;


    SELECT COUNT(*)
    INTO v_duplicate_program_matches

    FROM
    (
        SELECT
            assistance_transaction_id

        FROM m186_program_matches

        GROUP BY assistance_transaction_id

        HAVING COUNT(*) > 1
    ) x;


    IF v_duplicate_award_matches <> 0 THEN
        RAISE EXCEPTION
            'M186 duplicate award resolution detected for % transactions',
            v_duplicate_award_matches;
    END IF;


    IF v_duplicate_program_matches <> 0 THEN
        RAISE EXCEPTION
            'M186 duplicate program resolution detected for % transactions',
            v_duplicate_program_matches;
    END IF;


    RAISE NOTICE
        'M186 RESOLUTION UNIQUENESS PASS';

END
$$;


/*
====================================================================================================
9. BUILD EFFECTIVE RESOLUTION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m186_resolved;

CREATE TEMP TABLE m186_resolved AS
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

FROM m186_ledger l

LEFT JOIN m186_award_matches a
  ON a.assistance_transaction_id =
        l.assistance_transaction_id

LEFT JOIN m186_program_matches p
  ON p.assistance_transaction_id =
        l.assistance_transaction_id;


/*
====================================================================================================
10. POST-M186 ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. POST-M186 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM m186_resolved

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


/*
====================================================================================================
11. FOCAL PROGRAM RESOLUTION CHECK
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. AL 93.855 POST-MIGRATION RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m186_resolved

WHERE cfda_number = '93.855'

GROUP BY effective_accounting_disposition;


/*
====================================================================================================
12. FINAL CERTIFICATION

Pre-M186 unresolved:
    transactions       815,260
    programs             1,273
    amount              $54,439,794,160.88

M186 focal:
    transactions         3,361
    programs                 1
    amount               $2,385,155,445.79

Expected post-M186 unresolved:
    transactions       811,899
    programs             1,272
    amount              $52,054,638,715.09
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. FINAL M186 CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_unresolved_transactions bigint;
    v_unresolved_programs     bigint;
    v_unresolved_amount       numeric;

    v_focal_transactions      bigint;
    v_focal_amount            numeric;
    v_focal_dispositions      bigint;

    v_total_transactions      bigint;
    v_total_amount            numeric;
BEGIN

    /*
    -----------------------------------------------------------------------------------------------
    Full ledger closure
    -----------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_total_transactions,
        v_total_amount

    FROM m186_resolved;


    IF v_total_transactions <> 942243 THEN
        RAISE EXCEPTION
            'M186 ledger transaction control failed: expected 942243, found %',
            v_total_transactions;
    END IF;


    IF ROUND(v_total_amount, 2) <> 348524407674.34 THEN
        RAISE EXCEPTION
            'M186 ledger amount control failed: expected 348524407674.34, found %',
            ROUND(v_total_amount, 2);
    END IF;


    /*
    -----------------------------------------------------------------------------------------------
    Focal resolution
    -----------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),
        COALESCE(
            SUM(federal_action_obligation),
            0
        ),
        COUNT(
            DISTINCT effective_accounting_disposition
        )

    INTO
        v_focal_transactions,
        v_focal_amount,
        v_focal_dispositions

    FROM m186_resolved

    WHERE cfda_number = '93.855';


    IF v_focal_transactions <> 3361 THEN
        RAISE EXCEPTION
            'M186 focal post-resolution transaction control failed: expected 3361, found %',
            v_focal_transactions;
    END IF;


    IF ROUND(v_focal_amount, 2) <> 2385155445.79 THEN
        RAISE EXCEPTION
            'M186 focal post-resolution amount control failed: expected 2385155445.79, found %',
            ROUND(v_focal_amount, 2);
    END IF;


    IF v_focal_dispositions <> 1 THEN
        RAISE EXCEPTION
            'M186 focal program resolved to % dispositions; expected exactly 1',
            v_focal_dispositions;
    END IF;


    IF EXISTS
    (
        SELECT 1

        FROM m186_resolved

        WHERE cfda_number = '93.855'

          AND effective_accounting_disposition
                <> 'INCLUDE_ADDITIVE'
    ) THEN
        RAISE EXCEPTION
            'M186 focal program did not resolve entirely to INCLUDE_ADDITIVE';
    END IF;


    /*
    -----------------------------------------------------------------------------------------------
    Remaining unresolved control
    -----------------------------------------------------------------------------------------------
    */

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT cfda_number
        ),

        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_unresolved_transactions,
        v_unresolved_programs,
        v_unresolved_amount

    FROM m186_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW';


    IF v_unresolved_transactions <> 811899 THEN
        RAISE EXCEPTION
            'M186 unresolved transaction control failed: expected 811899, found %',
            v_unresolved_transactions;
    END IF;


    IF v_unresolved_programs <> 1272 THEN
        RAISE EXCEPTION
            'M186 unresolved program control failed: expected 1272, found %',
            v_unresolved_programs;
    END IF;


    IF ROUND(v_unresolved_amount, 2) <> 52054638715.09 THEN
        RAISE EXCEPTION
            'M186 unresolved amount control failed: expected 52054638715.09, found %',
            ROUND(v_unresolved_amount, 2);
    END IF;


    RAISE NOTICE
        'M186 FINAL CERTIFICATION PASS: unresolved_tx=% unresolved_programs=% unresolved_amount=%',
        v_unresolved_transactions,
        v_unresolved_programs,
        ROUND(v_unresolved_amount, 2);

END
$$;


/*
====================================================================================================
13. COMMIT
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 186 PASS'
\echo 'AL 93.855 -> INCLUDE_ADDITIVE'
\echo 'USASPENDING_ASSISTANCE -> principal statewide accounting source'
\echo 'NET_FEDERAL_ACTION_OBLIGATION -> accounting measure'
\echo 'County allocation -> UNRESOLVED'
\echo '===================================================================================================='
\echo ''

COMMIT;