/*
====================================================================================================
ETL-189D
RAILROAD SOCIAL INSURANCE ACCOUNTING PARTITION
AL 57.001
====================================================================================================

Purpose:
    Partition Washington FY2020-FY2024 USAspending AL 57.001 into
    mutually exclusive economic/payment components using the actual
    canonical award descriptions exposed by ETL-189C.

This is a diagnostic partition only.

It does NOT:
    - persist an accounting classification,
    - decide additive/excluded treatment,
    - infer county economic incidence,
    - alter the principal ledger.

Primary requirements:
    1. Every focal transaction receives exactly one partition.
    2. No transaction is duplicated.
    3. Partition totals reconstruct the certified focal population:
           12,511 transactions
           $1,357,308,008.42
    4. Fiscal-year partitions also reconstruct the focal population.
    5. Unknown/unclassified descriptions are surfaced explicitly.

Known semantic classes from ETL-189C:
    - Railroad Retirement Act pension paid from Social Security Equivalent Account
    - Railroad Retirement Act pension paid from Railroad Retirement Account
    - Railroad Retirement Act pension recipient
    - Railroad Retirement Act pension paid from Vested Dual Benefit Account
    - Railroad Unemployment Insurance Trust Fund benefit payments
    - Railroad Unemployment Insurance Act benefit claimant
    - CARES/CARWA/ARPA enhanced unemployment benefits
    - CARES/CARWA/ARPA extended unemployment benefits
    - CARES/CARWA/ARPA waiting-period waiver payments
    - Supplemental CARES Act funding

Methodology:
    ANALYSIS-189D-v1

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-189D - RAILROAD SOCIAL INSURANCE ACCOUNTING PARTITION'
\echo 'AL 57.001'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m189d_rr;

CREATE TEMP TABLE m189d_rr AS

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

FROM m189d_rr;


DO $$
DECLARE
    v_tx      bigint;
    v_awards  bigint;
    v_recip   bigint;
    v_amount  numeric;
    v_covid   numeric;
    v_iija    numeric;
    v_extra   numeric;
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

    FROM m189d_rr;


    IF v_tx <> 12511
       OR v_awards <> 12511
       OR v_recip <> 1
       OR ROUND(v_amount, 2) <> 1357308008.42
       OR ROUND(v_covid, 2) <> 752151.14
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 752151.14 THEN

        RAISE EXCEPTION
            'ETL-189D focal control mismatch: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-189D FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
3. BUILD MUTUALLY EXCLUSIVE SEMANTIC PARTITION

Ordering is deliberate.

COVID-specific RUIA descriptions are classified before generic
unemployment/sickness language.

Pension-account descriptions are classified explicitly.

Anything not recognized falls to UNCLASSIFIED_REVIEW.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. BUILD MUTUALLY EXCLUSIVE SEMANTIC PARTITION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m189d_partition;

CREATE TEMP TABLE m189d_partition AS

SELECT
    assistance_transaction_id,

    action_date,
    action_date_fiscal_year,

    federal_action_obligation,

    is_covid,
    is_iija,
    is_extraordinary,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,

    canonical_award_description,

    transaction_description,

    CASE

        /*
        ----------------------------------------------------------------------
        RAILROAD RETIREMENT PENSION COMPONENTS
        ----------------------------------------------------------------------
        */

        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%PENSION PAID FROM THE SOCIAL SECURITY EQUIVALENT ACCOUNT%'
            THEN 'RR_RETIREMENT_SSEB_ACCOUNT'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%PENSION PAID FROM THE RAILROAD RETIREMENT ACCOUNT%'
            THEN 'RR_RETIREMENT_ACCOUNT'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%PENSION PAID FROM THE VESTED DUAL BENEFIT ACCOUNT%'
            THEN 'RR_VESTED_DUAL_BENEFIT_ACCOUNT'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%RAILROAD RETIREMENT ACT PENSION RECIPIENT%'
            THEN 'RR_RETIREMENT_PENSION_RECIPIENT'


        /*
        ----------------------------------------------------------------------
        COVID / EXTRAORDINARY RUIA COMPONENTS
        ----------------------------------------------------------------------
        */

        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%SUPPLEMENTAL FUNDING FOR THE CARES ACT%'
            THEN 'RUIA_COVID_SUPPLEMENTAL_FUNDING'


        WHEN
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%ENHANCED BENEFIT%'
            AND
            (
                   UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARES%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARWA%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%AMERICAN RESCUE PLAN%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%ARPA%'
            )
            THEN 'RUIA_COVID_ENHANCED_BENEFIT'


        WHEN
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%EXTENDED%'
            AND
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%BENEFIT%'
            AND
            (
                   UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARES%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARWA%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%AMERICAN RESCUE PLAN%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%ARPA%'
            )
            THEN 'RUIA_COVID_EXTENDED_BENEFIT'


        WHEN
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%WAITING PERIOD%'
            AND
            (
                   UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARES%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARWA%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%AMERICAN RESCUE PLAN%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%ARPA%'
            )
            THEN 'RUIA_COVID_WAITING_PERIOD_WAIVER'


        /*
        ----------------------------------------------------------------------
        ORDINARY RUIA COMPONENTS
        ----------------------------------------------------------------------
        */

        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%RAILROAD UNEMPLOYMENT INSURANCE TRUST FUND BENEFIT PAYMENTS%'
            THEN 'RUIA_TRUST_FUND_BENEFITS'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%RAILROAD UNEMPLOYMENT INSURANCE ACT BENEFIT CLAIMANT%'
            THEN 'RUIA_BENEFIT_CLAIMANT'


        /*
        ----------------------------------------------------------------------
        FAIL-CLOSED RESIDUAL
        ----------------------------------------------------------------------
        */

        ELSE 'UNCLASSIFIED_REVIEW'

    END AS accounting_partition

FROM m189d_rr;


/*
====================================================================================================
4. PARTITION SUMMARY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PARTITION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    accounting_partition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT source_award_identifier
    ) AS award_count,

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

FROM m189d_partition

GROUP BY accounting_partition

ORDER BY net_obligation DESC;


/*
====================================================================================================
5. PARTITION x FISCAL YEAR
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. PARTITION x FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    accounting_partition,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount

FROM m189d_partition

GROUP BY
    action_date_fiscal_year,
    accounting_partition

ORDER BY
    action_date_fiscal_year,
    net_obligation DESC;


/*
====================================================================================================
6. UNCLASSIFIED DESCRIPTION REVIEW

This is the key fail-closed diagnostic.

If anything remains here, we inspect it before Migration 190.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. UNCLASSIFIED DESCRIPTION REVIEW'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        canonical_award_description,
        '[NULL]'
    ) AS canonical_award_description,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount

FROM m189d_partition

WHERE accounting_partition = 'UNCLASSIFIED_REVIEW'

GROUP BY canonical_award_description

ORDER BY net_obligation DESC;


/*
====================================================================================================
7. PARTITION UNIQUENESS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. PARTITION UNIQUENESS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS partition_row_count,

    COUNT(
        DISTINCT assistance_transaction_id
    ) AS distinct_transaction_count

FROM m189d_partition;


DO $$
DECLARE
    v_rows     bigint;
    v_distinct bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id)

    INTO
        v_rows,
        v_distinct

    FROM m189d_partition;


    IF v_rows <> 12511 THEN

        RAISE EXCEPTION
            'ETL-189D partition row-count failure: expected 12511, found %',
            v_rows;

    END IF;


    IF v_rows <> v_distinct THEN

        RAISE EXCEPTION
            'ETL-189D partition uniqueness failure: rows %, distinct transactions %',
            v_rows,
            v_distinct;

    END IF;


    RAISE NOTICE
        'ETL-189D PARTITION UNIQUENESS PASS';

END
$$;


/*
====================================================================================================
8. PARTITION CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. PARTITION CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS closure_transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS closure_net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS closure_covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS closure_iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS closure_extraordinary_amount

FROM m189d_partition;


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

        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

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

    FROM m189d_partition;


    IF v_tx <> 12511
       OR ROUND(v_amount, 2) <> 1357308008.42
       OR ROUND(v_covid, 2) <> 752151.14
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 752151.14 THEN

        RAISE EXCEPTION
            'ETL-189D partition closure failure: tx %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);

    END IF;


    RAISE NOTICE
        'ETL-189D PARTITION CLOSURE PASS';

END
$$;


/*
====================================================================================================
9. RETIREMENT vs RUIA HIGH-LEVEL BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. RETIREMENT vs RUIA HIGH-LEVEL BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    CASE

        WHEN accounting_partition LIKE 'RR_RETIREMENT%'
          OR accounting_partition = 'RR_VESTED_DUAL_BENEFIT_ACCOUNT'
            THEN 'RAILROAD_RETIREMENT'

        WHEN accounting_partition LIKE 'RUIA_%'
            THEN 'RAILROAD_UNEMPLOYMENT_SICKNESS'

        ELSE 'UNCLASSIFIED_REVIEW'

    END AS high_level_component,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount

FROM m189d_partition

GROUP BY 1

ORDER BY net_obligation DESC;


/*
====================================================================================================
10. DESCRIPTION / PARTITION AUDIT
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. DESCRIPTION / PARTITION AUDIT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    accounting_partition,

    canonical_award_description,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m189d_partition

GROUP BY
    accounting_partition,
    canonical_award_description

ORDER BY
    accounting_partition,
    net_obligation DESC;


/*
====================================================================================================
11. FINAL DIAGNOSTIC STATUS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. FINAL DIAGNOSTIC STATUS'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_unclassified_tx     bigint;
    v_unclassified_amount numeric;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_unclassified_tx,
        v_unclassified_amount

    FROM m189d_partition

    WHERE accounting_partition = 'UNCLASSIFIED_REVIEW';


    RAISE NOTICE
        'ETL-189D UNCLASSIFIED: tx=% amount=%',
        v_unclassified_tx,
        ROUND(v_unclassified_amount, 2);


    IF v_unclassified_tx = 0 THEN

        RAISE NOTICE
            'ETL-189D SEMANTIC PARTITION COMPLETE';

    ELSE

        RAISE NOTICE
            'ETL-189D SEMANTIC PARTITION REQUIRES REVIEW BEFORE ACCOUNTING MIGRATION';

    END IF;

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-189D COMPLETE'
\echo 'AL 57.001 Social Insurance for Railroad Workers'
\echo 'Diagnostic semantic partition only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;