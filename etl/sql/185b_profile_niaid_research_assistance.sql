/*
====================================================================================================
ETL-185B
PROFILE ALLERGY AND INFECTIOUS DISEASES RESEARCH ASSISTANCE
ASSISTANCE LISTING 93.855
====================================================================================================

Purpose
-------
Profile the largest remaining post-M185 unresolved USAspending assistance
program:

    93.855 - ALLERGY AND INFECTIOUS DISEASES RESEARCH

This is a narrow accounting-risk profile.

Question
--------
Does the observed transaction structure provide any reason to suspect a
plausible overlap with an independently acquired WCFFBP principal accounting
source?

If no plausible overlap pathway is identified, the WCFFBP methodology is to
avoid unnecessary secondary reconciliation and proceed toward accounting
classification after basic semantic validation.

Known ETL-185A controls
-----------------------
Transactions       : 3,361
Awards             : 812
Recipients         : 41
Net obligations    : $2,385,155,445.79
COVID              : $1,466,316,577.46
IIJA               : $0.00
Extraordinary      : $1,466,316,577.46

Scope
-----
Washington
FFY2020-FFY2024
USAspending assistance
AL 93.855

Diagnostic only:
    - no persistent database writes
    - no accounting classification
    - no external-source reconciliation
    - no county-incidence inference

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-185B - AL 93.855 ALLERGY AND INFECTIOUS DISEASES RESEARCH'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION

IMPORTANT:
Use only fields already demonstrated successfully by ETL-185A.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. BUILD AL 93.855 FOCAL POPULATION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185b_focal;

CREATE TEMP TABLE m185b_focal AS
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
    funding_agency_name,

    defc_codes,
    funding_families,

    is_covid,
    is_iija,
    is_extraordinary

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.855';


/*
====================================================================================================
2. HARD FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. HARD FOCAL CONTROL'
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

FROM m185b_focal;


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

    FROM m185b_focal;


    IF v_transactions <> 3361 THEN
        RAISE EXCEPTION
            'ETL-185B transaction control failed: expected 3361, found %',
            v_transactions;
    END IF;


    IF v_awards <> 812 THEN
        RAISE EXCEPTION
            'ETL-185B award control failed: expected 812, found %',
            v_awards;
    END IF;


    IF v_recipients <> 41 THEN
        RAISE EXCEPTION
            'ETL-185B recipient control failed: expected 41, found %',
            v_recipients;
    END IF;


    IF ROUND(v_net, 2) <> 2385155445.79 THEN
        RAISE EXCEPTION
            'ETL-185B net control failed: expected 2385155445.79, found %',
            ROUND(v_net, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 1466316577.46 THEN
        RAISE EXCEPTION
            'ETL-185B COVID control failed: expected 1466316577.46, found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-185B IIJA control failed: expected 0.00, found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extraordinary, 2) <> 1466316577.46 THEN
        RAISE EXCEPTION
            'ETL-185B extraordinary control failed: expected 1466316577.46, found %',
            ROUND(v_extraordinary, 2);
    END IF;


    RAISE NOTICE
        'ETL-185B FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
3. FISCAL-YEAR PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FISCAL-YEAR PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year,

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

FROM m185b_focal

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. FUNDING-AGENCY PROFILE

Question:
Does the focal population remain within the expected federal research-funding
family, or does the database expose another funding source that merits
investigation?
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FUNDING-AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        funding_agency_name,
        '<NULL>'
    ) AS funding_agency_name,

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
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m185b_focal

GROUP BY funding_agency_name

ORDER BY
    SUM(federal_action_obligation) DESC;


/*
====================================================================================================
5. RECIPIENT PROFILE

Administrative recipient geography is deliberately excluded.
This profile concerns statewide accounting, not county incidence.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. TOP 25 RECIPIENTS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    recipient_name,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year,

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

FROM m185b_focal

GROUP BY recipient_name

ORDER BY
    SUM(federal_action_obligation) DESC

LIMIT 25;


/*
====================================================================================================
6. SIGN / DEOBLIGATION PROFILE

Negative transactions remain part of net federal-action-obligation accounting.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. SIGN / DEOBLIGATION PROFILE'
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

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM m185b_focal

GROUP BY
    CASE
        WHEN federal_action_obligation > 0
            THEN 'POSITIVE'

        WHEN federal_action_obligation < 0
            THEN 'NEGATIVE'

        ELSE 'ZERO'
    END

ORDER BY obligation_sign;


/*
====================================================================================================
7. PROVENANCE PROFILE

Use the certified ledger's inherited provenance flags.
Do not rederive COVID, IIJA, or extraordinary status here.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. COVID / IIJA / EXTRAORDINARY PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    is_covid,
    is_iija,
    is_extraordinary,

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
    ) AS net_obligation

FROM m185b_focal

GROUP BY
    is_covid,
    is_iija,
    is_extraordinary

ORDER BY
    is_covid DESC,
    is_iija DESC,
    is_extraordinary DESC;


/*
====================================================================================================
8. FOCAL CLOSURE CHECK

The profile dimensions must continue to reconcile to the focal population.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. FOCAL CLOSURE CHECK'
\echo '----------------------------------------------------------------------------------------------------'

WITH control AS
(
    SELECT
        COUNT(*) AS transaction_count,

        SUM(
            federal_action_obligation
        ) AS net_obligation

    FROM m185b_focal
),

fy_rollup AS
(
    SELECT
        SUM(transaction_count)
            AS transaction_count,

        SUM(net_obligation)
            AS net_obligation

    FROM
    (
        SELECT
            action_date_fiscal_year,

            COUNT(*) AS transaction_count,

            SUM(
                federal_action_obligation
            ) AS net_obligation

        FROM m185b_focal

        GROUP BY action_date_fiscal_year
    ) x
)

SELECT
    c.transaction_count
        AS control_transactions,

    f.transaction_count
        AS fy_transactions,

    c.transaction_count
        - f.transaction_count
        AS transaction_difference,

    ROUND(
        c.net_obligation::numeric,
        2
    ) AS control_net_obligation,

    ROUND(
        f.net_obligation::numeric,
        2
    ) AS fy_net_obligation,

    ROUND(
        (
            c.net_obligation
            - f.net_obligation
        )::numeric,
        2
    ) AS obligation_difference

FROM control c
CROSS JOIN fy_rollup f;


DO $$
DECLARE
    v_transaction_difference bigint;
    v_obligation_difference  numeric;
BEGIN

    WITH control AS
    (
        SELECT
            COUNT(*) AS transaction_count,

            SUM(
                federal_action_obligation
            ) AS net_obligation

        FROM m185b_focal
    ),

    fy_rollup AS
    (
        SELECT
            SUM(transaction_count)
                AS transaction_count,

            SUM(net_obligation)
                AS net_obligation

        FROM
        (
            SELECT
                action_date_fiscal_year,

                COUNT(*) AS transaction_count,

                SUM(
                    federal_action_obligation
                ) AS net_obligation

            FROM m185b_focal

            GROUP BY action_date_fiscal_year
        ) x
    )

    SELECT
        c.transaction_count
            - f.transaction_count,

        c.net_obligation
            - f.net_obligation

    INTO
        v_transaction_difference,
        v_obligation_difference

    FROM control c
    CROSS JOIN fy_rollup f;


    IF v_transaction_difference <> 0 THEN
        RAISE EXCEPTION
            'ETL-185B focal transaction closure failed: difference=%',
            v_transaction_difference;
    END IF;


    IF ROUND(v_obligation_difference, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-185B focal obligation closure failed: difference=%',
            ROUND(v_obligation_difference, 2);
    END IF;


    RAISE NOTICE
        'ETL-185B FOCAL CLOSURE PASS';

END
$$;


/*
====================================================================================================
9. COMPLETION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-185B COMPLETE'
\echo '===================================================================================================='
\echo 'Diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No external-source reconciliation.'
\echo 'No county-incidence inference.'
\echo ''

ROLLBACK;