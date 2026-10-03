/*
====================================================================================================
ETL-189A
SOCIAL INSURANCE FOR RAILROAD WORKERS PROFILE
AL 57.001
====================================================================================================

Purpose:
    Compact overlap-risk profile of USAspending AL 57.001,
    Social Insurance for Railroad Workers, Washington FFY2020-FFY2024.

Primary question:
    Does AL 57.001 represent genuine federal social-insurance benefit
    payments not otherwise captured by a WCFFBP principal source, or
    is there an identified overlap pathway requiring reconciliation?

Known residual control:
    transactions       12,511
    net obligation     $1,357,308,008.42
    COVID              $752,151.14
    IIJA               $0.00
    extraordinary      $752,151.14

Diagnostic only.
No persistent writes.
No accounting decision.
No county-incidence inference.
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-189A - SOCIAL INSURANCE FOR RAILROAD WORKERS PROFILE'
\echo 'AL 57.001'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m189a_rr;

CREATE TEMP TABLE m189a_rr AS

SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '57.001';


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

FROM m189a_rr;


DO $$
DECLARE
    v_tx      bigint;
    v_amount  numeric;
    v_covid   numeric;
    v_iija    numeric;
    v_extra   numeric;
BEGIN

    SELECT
        COUNT(*),
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
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m189a_rr;


    IF v_tx <> 12511
       OR ROUND(v_amount, 2) <> 1357308008.42
       OR ROUND(v_covid, 2) <> 752151.14
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 752151.14 THEN

        RAISE EXCEPTION
            'ETL-189A focal mismatch: tx %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-189A FOCAL CONTROL PASS';

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
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS extraordinary_amount

FROM m189a_rr

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
4. FUNDING / AWARDING AGENCY PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FUNDING / AWARDING AGENCY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    funding_agency_name,
    awarding_agency_name,

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
    ) AS net_obligation

FROM m189a_rr

GROUP BY
    funding_agency_name,
    awarding_agency_name

ORDER BY net_obligation DESC;


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
    recipient_name,

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
    ) AS net_obligation

FROM m189a_rr

GROUP BY recipient_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. AWARD IDENTIFIER PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TOP AWARD IDENTIFIERS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, ''),
        '[NULL]'
    ) AS source_award_identifier,

    COUNT(*) AS transaction_count,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m189a_rr

GROUP BY 1

ORDER BY net_obligation DESC

LIMIT 25;


/*
====================================================================================================
7. TRANSACTION SIGN PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TRANSACTION SIGN PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    CASE
        WHEN federal_action_obligation < 0
            THEN 'NEGATIVE'
        WHEN federal_action_obligation > 0
            THEN 'POSITIVE'
        ELSE 'ZERO'
    END AS obligation_sign,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m189a_rr

GROUP BY 1

ORDER BY 1;


/*
====================================================================================================
8. PROVENANCE PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. PROVENANCE PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    is_covid,
    is_iija,
    is_extraordinary,

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
    ) AS net_obligation

FROM m189a_rr

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
9. CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS closure_transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS closure_net_obligation

FROM m189a_rr;


DO $$
DECLARE
    v_tx     bigint;
    v_amount numeric;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_amount

    FROM m189a_rr;


    IF v_tx <> 12511
       OR ROUND(v_amount, 2) <> 1357308008.42 THEN

        RAISE EXCEPTION
            'ETL-189A closure failed: tx %, amount %',
            v_tx,
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-189A FOCAL CLOSURE PASS';

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-189A COMPLETE'
\echo 'AL 57.001 Social Insurance for Railroad Workers'
\echo 'Diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;