/*
====================================================================================================
MIGRATION 185
SEED FEMA PUBLIC ASSISTANCE ACCOUNTING POLICY
ASSISTANCE LISTING 97.036
====================================================================================================

ETL branch:
    ETL-174B-5Z

Methodology version:
    ANALYSIS-174B-5Z-v1

Accounting determination
------------------------
AL 97.036 FEMA Public Assistance is genuine federal inflow to Washington.

No identified overlap pathway exists with an independently acquired WCFFBP
principal accounting source.

WCFFBP overlap-risk triage rule:

    No identified overlap pathway
        -> presume additive after basic semantic/accounting validation.

Accounting source:
    USASPENDING_ASSISTANCE

Accounting measure:
    NET_FEDERAL_ACTION_OBLIGATION

Accounting disposition:
    INCLUDE_ADDITIVE

County incidence:
    UNRESOLVED

Certified FFY2020-FFY2024 controls:
    transactions                3,240
    awards                         29
    recipients                      4
    net obligations       2,756,169,246.03
    COVID                 2,726,566,347.12
    IIJA                              0.00
    extraordinary         2,727,558,787.32

Expected post-M185 unresolved:
    transactions              815,260
    programs                    1,273
    obligations        54,439,794,160.88
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 185 - FEMA PUBLIC ASSISTANCE ACCOUNTING POLICY'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. PRE-MIGRATION SOURCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION AL 97.036 SOURCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185_focal;

CREATE TEMP TABLE m185_focal AS
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
  AND cfda_number = '97.036';


SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m185_focal;


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
        COUNT(DISTINCT source_award_identifier),
        COUNT(DISTINCT recipient_name),
        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(
            SUM(
                CASE WHEN is_covid
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE WHEN is_iija
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE WHEN is_extraordinary
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

    FROM m185_focal;


    IF v_transactions <> 3240 THEN
        RAISE EXCEPTION
            'M185 transaction control failed: expected 3240, found %',
            v_transactions;
    END IF;

    IF v_awards <> 29 THEN
        RAISE EXCEPTION
            'M185 award control failed: expected 29, found %',
            v_awards;
    END IF;

    IF v_recipients <> 4 THEN
        RAISE EXCEPTION
            'M185 recipient control failed: expected 4, found %',
            v_recipients;
    END IF;

    IF ROUND(v_net, 2) <> 2756169246.03 THEN
        RAISE EXCEPTION
            'M185 net control failed: expected 2756169246.03, found %',
            ROUND(v_net, 2);
    END IF;

    IF ROUND(v_covid, 2) <> 2726566347.12 THEN
        RAISE EXCEPTION
            'M185 COVID control failed: expected 2726566347.12, found %',
            ROUND(v_covid, 2);
    END IF;

    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'M185 IIJA control failed: expected 0.00, found %',
            ROUND(v_iija, 2);
    END IF;

    IF ROUND(v_extraordinary, 2) <> 2727558787.32 THEN
        RAISE EXCEPTION
            'M185 extraordinary control failed: expected 2727558787.32, found %',
            ROUND(v_extraordinary, 2);
    END IF;

    RAISE NOTICE
        'M185 PRE-MIGRATION FEMA PUBLIC ASSISTANCE CONTROL PASS';

END
$$;


/*
====================================================================================================
2. SEED SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. SEED SOURCE POLICY'
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
    'FEMA_PUBLIC_ASSISTANCE',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'AL 97.036 is genuine federal inflow to Washington. '
    || 'ETL-174B-5Z identified no plausible overlap pathway with an independently '
    || 'acquired WCFFBP principal accounting source. Under the WCFFBP overlap-risk '
    || 'triage rule, USAspending net federal_action_obligation is accepted as the '
    || 'statewide accounting measure without unnecessary external-source reconciliation. '
    || 'COVID and extraordinary classifications remain provenance dimensions. '
    || 'County incidence remains unresolved.',

    'ANALYSIS-174B-5Z-v1',
    2020,
    2024
)
ON CONFLICT DO NOTHING;


/*
====================================================================================================
3. RESOLVE SOURCE POLICY ID
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. RESOLVE SOURCE POLICY ID'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185_policy;

CREATE TEMP TABLE m185_policy AS
SELECT
    federal_inflow_source_policy_id

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'DISASTER_ASSISTANCE'
  AND inflow_subfamily = 'FEMA_PUBLIC_ASSISTANCE'
  AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
  AND preferred_source = 'USASPENDING_ASSISTANCE'
  AND methodology_version = 'ANALYSIS-174B-5Z-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM m185_policy;

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'M185 source policy resolution failed: expected exactly 1 row, found %',
            v_count;
    END IF;

    RAISE NOTICE
        'M185 SOURCE POLICY RESOLUTION PASS';

END
$$;


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
    '97.036',
    'Disaster Grants - Public Assistance (Presidentially Declared Disasters)',
    'DISASTER_ASSISTANCE',
    'FEMA_PUBLIC_ASSISTANCE',
    'NONE',
    TRUE,
    TRUE,

    'ETL-174B-5Z certified 3,240 transactions, 29 awards, 4 recipients, '
    || '$2,756,169,246.03 net obligations, $2,726,566,347.12 COVID-tagged, '
    || '$0 IIJA-tagged, and $2,727,558,787.32 extraordinary-tagged. '
    || 'No identified overlap pathway requires external-source reconciliation.',

    'ANALYSIS-174B-5Z-v1',
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
5. SEED PROGRAM POLICY MAPPING
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
    '97.036',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'FEMA Public Assistance is additive federal inflow. '
    || 'No identified overlap pathway exists with an independently acquired '
    || 'WCFFBP principal accounting source. Statewide accounting is accepted '
    || 'using USAspending net federal_action_obligation; county incidence '
    || 'remains unresolved.',

    'ANALYSIS-174B-5Z-v1',
    2020,
    2024

FROM m185_policy p

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
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'DISASTER_ASSISTANCE'
  AND inflow_subfamily = 'FEMA_PUBLIC_ASSISTANCE'
  AND methodology_version = 'ANALYSIS-174B-5Z-v1';


SELECT
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

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '97.036'
  AND methodology_version = 'ANALYSIS-174B-5Z-v1';


SELECT
    m.source_system,
    m.source_program_code,
    m.federal_inflow_source_policy_id,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year

FROM reference.federal_inflow_program_policy_mapping m

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '97.036'
  AND m.methodology_version = 'ANALYSIS-174B-5Z-v1';


/*
====================================================================================================
7. RECONSTRUCT EFFECTIVE POST-M185 ACCOUNTING BRIDGE
====================================================================================================

Precedence:

    AWARD CLASSIFICATION
        >
    PROGRAM POLICY MAPPING
        >
    UNCLASSIFIED_REVIEW
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. RECONSTRUCT POST-M185 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185_ledger;

CREATE TEMP TABLE m185_ledger AS
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


CREATE INDEX ON m185_ledger (assistance_transaction_id);
CREATE INDEX ON m185_ledger (cfda_number);
CREATE INDEX ON m185_ledger (source_award_identifier);
CREATE INDEX ON m185_ledger (action_date_fiscal_year);


/*
----------------------------------------------------------------------------------------------------
7A. AWARD-LEVEL RESOLUTION
----------------------------------------------------------------------------------------------------
*/

DROP TABLE IF EXISTS pg_temp.m185_award_matches;

CREATE TEMP TABLE m185_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM m185_ledger l

JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = l.cfda_number
 AND a.source_award_identifier = l.source_award_identifier

WHERE
    (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= a.valid_from_fiscal_year
    )
AND
    (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= a.valid_through_fiscal_year
    );


/*
----------------------------------------------------------------------------------------------------
7B. PROGRAM-LEVEL RESOLUTION
----------------------------------------------------------------------------------------------------
*/

DROP TABLE IF EXISTS pg_temp.m185_program_matches;

CREATE TEMP TABLE m185_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM m185_ledger l

JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = l.cfda_number

WHERE
    (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= m.valid_from_fiscal_year
    )
AND
    (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= m.valid_through_fiscal_year
    );


/*
----------------------------------------------------------------------------------------------------
7C. FAIL-CLOSED UNIQUENESS CHECK
----------------------------------------------------------------------------------------------------
*/

DO $$
DECLARE
    v_duplicate_award_matches   bigint;
    v_duplicate_program_matches bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_duplicate_award_matches
    FROM
    (
        SELECT assistance_transaction_id
        FROM m185_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;


    SELECT COUNT(*)
    INTO v_duplicate_program_matches
    FROM
    (
        SELECT assistance_transaction_id
        FROM m185_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;


    IF v_duplicate_award_matches <> 0 THEN
        RAISE EXCEPTION
            'M185 duplicate award-level resolution detected for % transactions',
            v_duplicate_award_matches;
    END IF;


    IF v_duplicate_program_matches <> 0 THEN
        RAISE EXCEPTION
            'M185 duplicate program-level resolution detected for % transactions',
            v_duplicate_program_matches;
    END IF;


    RAISE NOTICE
        'M185 RESOLUTION UNIQUENESS PASS';

END
$$;


/*
----------------------------------------------------------------------------------------------------
7D. EFFECTIVE RESOLUTION
----------------------------------------------------------------------------------------------------
*/

DROP TABLE IF EXISTS pg_temp.m185_resolved;

CREATE TEMP TABLE m185_resolved AS
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

FROM m185_ledger l

LEFT JOIN m185_award_matches a
  ON a.assistance_transaction_id = l.assistance_transaction_id

LEFT JOIN m185_program_matches p
  ON p.assistance_transaction_id = l.assistance_transaction_id;


/*
====================================================================================================
8. POST-M185 BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. POST-M185 ASSISTANCE BRIDGE'
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
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m185_resolved

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


/*
====================================================================================================
9. POST-M185 HARD CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. POST-M185 HARD CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_gross_total       numeric;
    v_bridge_total      numeric;

    v_unclassified_tx   bigint;
    v_unclassified_prog bigint;
    v_unclassified_amt  numeric;

    v_fema_tx           bigint;
    v_fema_amt          numeric;

    v_fema_bad_disp     bigint;
BEGIN

    SELECT
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_gross_total
    FROM m185_ledger;


    SELECT
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_bridge_total
    FROM m185_resolved;


    IF ROUND(v_gross_total, 2) <> 348524407674.34 THEN
        RAISE EXCEPTION
            'M185 gross ledger control failed: expected 348524407674.34, found %',
            ROUND(v_gross_total, 2);
    END IF;


    IF ROUND(v_bridge_total, 2) <> ROUND(v_gross_total, 2) THEN
        RAISE EXCEPTION
            'M185 bridge closure failed: gross %, bridge %',
            ROUND(v_gross_total, 2),
            ROUND(v_bridge_total, 2);
    END IF;


    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_unclassified_tx,
        v_unclassified_prog,
        v_unclassified_amt

    FROM m185_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW';


    IF v_unclassified_tx <> 815260 THEN
        RAISE EXCEPTION
            'M185 unresolved transaction control failed: expected 815260, found %',
            v_unclassified_tx;
    END IF;


    IF v_unclassified_prog <> 1273 THEN
        RAISE EXCEPTION
            'M185 unresolved program control failed: expected 1273, found %',
            v_unclassified_prog;
    END IF;


    IF ROUND(v_unclassified_amt, 2) <> 54439794160.88 THEN
        RAISE EXCEPTION
            'M185 unresolved amount control failed: expected 54439794160.88, found %',
            ROUND(v_unclassified_amt, 2);
    END IF;


    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_fema_tx,
        v_fema_amt

    FROM m185_resolved

    WHERE cfda_number = '97.036';


    IF v_fema_tx <> 3240 THEN
        RAISE EXCEPTION
            'M185 FEMA transaction control failed: expected 3240, found %',
            v_fema_tx;
    END IF;


    IF ROUND(v_fema_amt, 2) <> 2756169246.03 THEN
        RAISE EXCEPTION
            'M185 FEMA amount control failed: expected 2756169246.03, found %',
            ROUND(v_fema_amt, 2);
    END IF;


    SELECT COUNT(*)
    INTO v_fema_bad_disp

    FROM m185_resolved

    WHERE cfda_number = '97.036'
      AND effective_accounting_disposition <> 'INCLUDE_ADDITIVE';


    IF v_fema_bad_disp <> 0 THEN
        RAISE EXCEPTION
            'M185 FEMA disposition control failed: % transactions are not INCLUDE_ADDITIVE',
            v_fema_bad_disp;
    END IF;


    RAISE NOTICE
        'M185 FINAL CERTIFICATION PASS: unresolved_tx=% unresolved_programs=% unresolved=%',
        v_unclassified_tx,
        v_unclassified_prog,
        ROUND(v_unclassified_amt, 2);

END
$$;


/*
====================================================================================================
10. COMMIT
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 185 COMPLETE'
\echo '===================================================================================================='
\echo 'FEMA Public Assistance / AL 97.036 persisted as INCLUDE_ADDITIVE.'
\echo 'Accounting source: USASPENDING_ASSISTANCE.'
\echo 'Accounting measure: NET_FEDERAL_ACTION_OBLIGATION.'
\echo 'County allocation remains unresolved.'
\echo ''

COMMIT;