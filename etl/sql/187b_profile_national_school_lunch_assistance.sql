/*
====================================================================================================
ETL-187B
NATIONAL SCHOOL LUNCH PROGRAM ASSISTANCE PROFILE
AL 10.555
====================================================================================================

Purpose:
    Compact accounting profile of USAspending AL 10.555,
    National School Lunch Program, for Washington FFY2020-FFY2024.

Question:
    Is there an identified/plausible overlap pathway with an existing
    WCFFBP principal accounting source that requires reconciliation
    before statewide inclusion?

Diagnostic only.
No persistent writes.
No accounting decision.
No county-incidence inference.
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-187B - NATIONAL SCHOOL LUNCH PROGRAM ASSISTANCE PROFILE'
\echo 'AL 10.555'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m187b_lunch;

CREATE TEMP TABLE m187b_lunch AS

SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '10.555';


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
    COUNT(DISTINCT COALESCE(NULLIF(award_id_fain, ''), NULLIF(award_id_uri, '')))
        AS award_count,
    COUNT(DISTINCT recipient_id) AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS extraordinary_amount

FROM m187b_lunch;


DO $$
DECLARE
    v_tx       bigint;
    v_amount   numeric;
    v_covid    numeric;
    v_iija     numeric;
    v_extra    numeric;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0 END
        ), 0)

    INTO
        v_tx,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m187b_lunch;


    IF v_tx <> 68
       OR ROUND(v_amount, 2) <> 2149804327.66
       OR ROUND(v_covid, 2) <> 178329137.37
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 178329137.37 THEN

        RAISE EXCEPTION
            'ETL-187B focal control mismatch: tx %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-187B FOCAL CONTROL PASS';

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

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m187b_lunch

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
    funding_agency_name,
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
    ) AS net_obligation

FROM m187b_lunch

GROUP BY funding_agency_name

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

FROM m187b_lunch

GROUP BY recipient_name

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. TRANSACTION SIGN PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TRANSACTION SIGN PROFILE'
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

FROM m187b_lunch

GROUP BY 1

ORDER BY 1;


/*
====================================================================================================
7. PROVENANCE PROFILE
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
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m187b_lunch

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
8. CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS closure_transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS closure_net_obligation

FROM m187b_lunch;


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

    FROM m187b_lunch;


    IF v_tx <> 68
       OR ROUND(v_amount, 2) <> 2149804327.66 THEN

        RAISE EXCEPTION
            'ETL-187B closure failed: tx %, amount %',
            v_tx,
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-187B FOCAL CLOSURE PASS';

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-187B COMPLETE'
\echo 'AL 10.555 National School Lunch Program'
\echo 'Diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;