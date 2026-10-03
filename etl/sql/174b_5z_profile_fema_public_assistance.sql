/*
====================================================================================================
ETL-174B-5Z — PROFILE FEMA PUBLIC ASSISTANCE
ASSISTANCE LISTING 97.036
====================================================================================================

Purpose
-------
Profile Assistance Listing 97.036:

    Disaster Grants - Public Assistance
    (Presidentially Declared Disasters)

within the certified Washington USAspending assistance ledger for FFY2020-FFY2024.

This is an accounting-risk triage profile, not a comprehensive external-source reconciliation.

WCFFBP efficiency rule
----------------------
No identified overlap pathway
    -> presume additive after basic semantic/accounting validation.

Identified or plausible overlap pathway
    -> reconcile before inclusion.

This profile therefore asks only what is necessary to determine:

1. Is the stream genuine federal inflow to Washington?
2. Does its structure reveal a plausible overlap with an existing WCFFBP principal accounting source?
3. Is federal_action_obligation a coherent transaction measure?
4. What COVID / IIJA / extraordinary provenance must be preserved?
5. Can statewide accounting be accepted while county incidence remains separate?

No database writes.
No accounting policy changes.
No county allocation.
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5Z - FEMA PUBLIC ASSISTANCE / AL 97.036'
\echo '===================================================================================================='
\echo 'DIAGNOSTIC PROFILE - NO PERSISTENT DATABASE WRITES'
\echo ''

BEGIN;


/*
====================================================================================================
1. MATERIALIZE FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.fema_pa;

CREATE TEMP TABLE fema_pa AS
SELECT
    assistance_transaction_id,
    action_date,
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
    funding_agency_name,

    defc_codes,
    funding_families,

    is_covid,
    is_iija,
    is_extraordinary

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '97.036';


CREATE INDEX ON fema_pa (source_award_identifier);
CREATE INDEX ON fema_pa (action_date_fiscal_year);
CREATE INDEX ON fema_pa (recipient_name);


/*
====================================================================================================
2. HARD CONTROL
====================================================================================================

Expected from ETL-184A:
    transactions       3,240
    awards             29
    recipients          4
    net obligations    $2,756,169,246.03
    COVID              $2,726,566,347.12
    IIJA                $0.00
    extraordinary      $2,727,558,787.32
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. FOCAL SOURCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

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
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS positive_obligation,

    ROUND(
        SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS negative_obligation,

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

FROM fema_pa;


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

    FROM fema_pa;


    IF v_transactions <> 3240 THEN
        RAISE EXCEPTION
            '97.036 transaction control failed: expected 3240, found %',
            v_transactions;
    END IF;

    IF v_awards <> 29 THEN
        RAISE EXCEPTION
            '97.036 award control failed: expected 29, found %',
            v_awards;
    END IF;

    IF v_recipients <> 4 THEN
        RAISE EXCEPTION
            '97.036 recipient control failed: expected 4, found %',
            v_recipients;
    END IF;

    IF ROUND(v_net, 2) <> 2756169246.03 THEN
        RAISE EXCEPTION
            '97.036 net control failed: expected 2756169246.03, found %',
            ROUND(v_net, 2);
    END IF;

    IF ROUND(v_covid, 2) <> 2726566347.12 THEN
        RAISE EXCEPTION
            '97.036 COVID control failed: expected 2726566347.12, found %',
            ROUND(v_covid, 2);
    END IF;

    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            '97.036 IIJA control failed: expected 0.00, found %',
            ROUND(v_iija, 2);
    END IF;

    IF ROUND(v_extraordinary, 2) <> 2727558787.32 THEN
        RAISE EXCEPTION
            '97.036 extraordinary control failed: expected 2727558787.32, found %',
            ROUND(v_extraordinary, 2);
    END IF;

    RAISE NOTICE
        'ETL-174B-5Z FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
3. FUNDING AGENCY SCREEN
====================================================================================================

Unexpected funding agencies would be a reason to stop before classification.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FUNDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    funding_agency_name,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM fema_pa

GROUP BY funding_agency_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
4. FISCAL-YEAR PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FISCAL-YEAR PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

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

FROM fema_pa

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
5. RECIPIENT CONCENTRATION
====================================================================================================

This is an administrative recipient profile only.

Recipient location must NOT be interpreted as county economic incidence.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    recipient_name,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

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
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM fema_pa

GROUP BY recipient_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. AWARD CONCENTRATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. AWARD PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_award_identifier,

    MAX(recipient_name) AS recipient_name,

    COUNT(*) AS transaction_count,

    MIN(action_date) AS first_action_date,

    MAX(action_date) AS last_action_date,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(
            CASE
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS positive_obligation,

    ROUND(
        SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS negative_obligation,

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
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM fema_pa

GROUP BY source_award_identifier

ORDER BY net_obligation DESC;


/*
====================================================================================================
7. TRANSACTION SIGN PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TRANSACTION SIGN PROFILE'
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

FROM fema_pa

GROUP BY 1

ORDER BY 1;


/*
====================================================================================================
8. PROVENANCE COMBINATION PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. COVID / IIJA / EXTRAORDINARY COMBINATIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    is_covid,
    is_iija,
    is_extraordinary,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM fema_pa

GROUP BY
    is_covid,
    is_iija,
    is_extraordinary

ORDER BY net_obligation DESC;


/*
====================================================================================================
9. DEFC / FUNDING-FAMILY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. DEFC / FUNDING-FAMILY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    defc_codes,
    funding_families,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM fema_pa

GROUP BY
    defc_codes,
    funding_families

ORDER BY net_obligation DESC;


/*
====================================================================================================
10. COMPLETION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5Z PROFILE COMPLETE'
\echo '===================================================================================================='
\echo 'No persistent database writes.'
\echo 'No accounting classification made.'
\echo 'No external-source reconciliation performed.'
\echo 'No county-incidence inference made.'
\echo ''

ROLLBACK;