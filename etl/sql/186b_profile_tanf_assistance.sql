/*
====================================================================================================
ETL-186B
TANF ASSISTANCE ACCOUNTING PROFILE
====================================================================================================

Program:
    AL 93.558
    TEMPORARY ASSISTANCE FOR NEEDY FAMILIES

Purpose:
    Determine whether the certified USAspending TANF population can be treated
    as additive federal inflow for WCFFBP statewide accounting.

This is a diagnostic profile only.

Questions:
    1. Does the focal population reproduce the ETL-186A control?
    2. What is the fiscal-year distribution?
    3. Which federal agency funds the population?
    4. Who are the recipients?
    5. Are deobligations/material negative adjustments present?
    6. What COVID / IIJA / extraordinary provenance is present?

Not investigated here:
    - county incidence
    - recipient geography
    - descriptions / keyword searches
    - downstream TANF expenditure geography
    - external dollar reconciliation
    - persistent accounting policy

Expected FFY2020-FFY2024 control:
    transactions       285
    awards              91
    recipients          12
    net obligations     $2,202,205,302.12
    COVID               $459,361,851.86
    IIJA                 $0.00
    extraordinary       $459,361,851.86

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-186B - TANF ASSISTANCE ACCOUNTING PROFILE'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. BUILD FOCAL POPULATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. BUILD AL 93.558 FOCAL POPULATION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186b_focal;

CREATE TEMP TABLE m186b_focal AS
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
  AND cfda_number = '93.558';


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

FROM m186b_focal;


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

    FROM m186b_focal;


    IF v_transactions <> 285 THEN
        RAISE EXCEPTION
            'ETL-186B transaction control failed: expected 285, found %',
            v_transactions;
    END IF;


    IF v_awards <> 91 THEN
        RAISE EXCEPTION
            'ETL-186B award control failed: expected 91, found %',
            v_awards;
    END IF;


    IF v_recipients <> 12 THEN
        RAISE EXCEPTION
            'ETL-186B recipient control failed: expected 12, found %',
            v_recipients;
    END IF;


    IF ROUND(v_net, 2) <> 2202205302.12 THEN
        RAISE EXCEPTION
            'ETL-186B net control failed: expected 2202205302.12, found %',
            ROUND(v_net, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 459361851.86 THEN
        RAISE EXCEPTION
            'ETL-186B COVID control failed: expected 459361851.86, found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-186B IIJA control failed: expected 0.00, found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extraordinary, 2) <> 459361851.86 THEN
        RAISE EXCEPTION
            'ETL-186B extraordinary control failed: expected 459361851.86, found %',
            ROUND(v_extraordinary, 2);
    END IF;


    RAISE NOTICE
        'ETL-186B FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
3. FISCAL-YEAR PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. TANF BY FISCAL YEAR'
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
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m186b_focal

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. FUNDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FUNDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(funding_agency_name, ''),
        '[NULL / BLANK]'
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
    ) AS net_obligation

FROM m186b_focal

GROUP BY
    COALESCE(
        NULLIF(funding_agency_name, ''),
        '[NULL / BLANK]'
    )

ORDER BY
    SUM(federal_action_obligation) DESC;


/*
====================================================================================================
5. RECIPIENT PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(recipient_name, ''),
        '[NULL / BLANK]'
    ) AS recipient_name,

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

FROM m186b_focal

GROUP BY
    COALESCE(
        NULLIF(recipient_name, ''),
        '[NULL / BLANK]'
    )

ORDER BY
    SUM(federal_action_obligation) DESC;


/*
====================================================================================================
6. SIGN / DEOBLIGATION PROFILE
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
    ) AS net_obligation

FROM m186b_focal

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
7. COVID / IIJA / EXTRAORDINARY PROVENANCE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. PROVENANCE PROFILE'
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

FROM m186b_focal

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
8. FOCAL CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. FOCAL CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

WITH control AS
(
    SELECT
        COUNT(*) AS transaction_count,

        COALESCE(
            SUM(federal_action_obligation),
            0
        ) AS net_obligation

    FROM m186b_focal
),

fy AS
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

            SUM(federal_action_obligation)
                AS net_obligation

        FROM m186b_focal

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

CROSS JOIN fy f;


DO $$
DECLARE
    v_control_transactions bigint;
    v_fy_transactions      bigint;

    v_control_amount       numeric;
    v_fy_amount            numeric;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_control_transactions,
        v_control_amount

    FROM m186b_focal;


    SELECT
        SUM(transaction_count),
        SUM(net_obligation)

    INTO
        v_fy_transactions,
        v_fy_amount

    FROM
    (
        SELECT
            action_date_fiscal_year,

            COUNT(*) AS transaction_count,

            SUM(federal_action_obligation)
                AS net_obligation

        FROM m186b_focal

        GROUP BY action_date_fiscal_year
    ) x;


    IF v_control_transactions <> v_fy_transactions THEN
        RAISE EXCEPTION
            'ETL-186B focal transaction closure failed: control %, FY %',
            v_control_transactions,
            v_fy_transactions;
    END IF;


    IF ROUND(v_control_amount, 2)
       <> ROUND(v_fy_amount, 2) THEN

        RAISE EXCEPTION
            'ETL-186B focal amount closure failed: control %, FY %',
            ROUND(v_control_amount, 2),
            ROUND(v_fy_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-186B FOCAL CLOSURE PASS';

END
$$;


/*
====================================================================================================
9. COMPLETION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-186B COMPLETE'
\echo 'Diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;