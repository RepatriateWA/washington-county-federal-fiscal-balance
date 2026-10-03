/*
====================================================================================================
ETL-195B
UNEMPLOYMENT INSURANCE AWARD-COMPONENT PARTITION AND OVERLAP SCREEN

Assistance Listing:
    17.225 - Unemployment Insurance

Purpose:
    Partition the Washington FY2020-FY2024 AL 17.225 population at the award
    level into empirically supported functional components.

ETL-195A control:
    Transactions       201
    Awards              26
    Recipients           2
    Net obligation      $937,828,270.83
    COVID               $380,145,955.79
    IIJA                          $0.00
    Extraordinary       $380,145,955.79

Why this diagnostic exists:
    ETL-195A established that AL 17.225 is heterogeneous. It contains ordinary
    UI activity, pandemic UI activity, RESEA, integrity/fraud/system grants,
    benefit-related activity, and other specialized components.

    The ETL-195A keyword screen was useful for discovery but is NOT an
    accounting classification because transaction descriptions may contain
    multiple program concepts and generic "Unemployment Insurance" language.

Method:
    1. Preserve the exact certified-ledger population.
    2. Collapse transactions to the 26 award identifiers.
    3. Preserve complete award-description evidence.
    4. Assign a diagnostic component using conservative semantic rules.
    5. Reconcile the component partition exactly to the ETL-195A control.
    6. Separately identify awards whose descriptions indicate actual
       unemployment-benefit funding.
    7. Test focal award identifiers against other Assistance Listings.
    8. Inventory existing WCFFBP policies relevant to possible overlap.

Diagnostic components:
    COVID_PANDEMIC_UI
    UI_ADMINISTRATION
    UI_INTEGRITY_FRAUD_EQUITY
    RESEA
    TRADE_ADJUSTMENT_BENEFITS
    SHORT_TIME_COMPENSATION
    OTHER_IDENTIFIED_UI
    UNRESOLVED

Important:
    These are diagnostic components, NOT accounting dispositions.

    COVID/extraordinary/IIJA remain independent provenance dimensions.

    Recipient address does not establish beneficiary or county incidence.

No persistent writes.
No accounting migration.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-195B'
\echo 'UNEMPLOYMENT INSURANCE AWARD-COMPONENT PARTITION AND OVERLAP SCREEN'
\echo 'AL 17.225'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD EXACT FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m195b_ui;

CREATE TEMP TABLE m195b_ui AS

SELECT
    *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '17.225';


ANALYZE m195b_ui;


/*
====================================================================================================
2. HARD CONTROL AGAINST ETL-195A
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. HARD CONTROL AGAINST ETL-195A'
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
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m195b_ui;


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

        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_extraordinary
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

    FROM m195b_ui;


    IF v_tx <> 201 THEN
        RAISE EXCEPTION
            'ETL-195B CONTROL FAILED: expected 201 transactions; found %',
            v_tx;
    END IF;


    IF v_awards <> 26 THEN
        RAISE EXCEPTION
            'ETL-195B CONTROL FAILED: expected 26 awards; found %',
            v_awards;
    END IF;


    IF v_recip <> 2 THEN
        RAISE EXCEPTION
            'ETL-195B CONTROL FAILED: expected 2 recipients; found %',
            v_recip;
    END IF;


    IF ROUND(v_amount, 2) <> 937828270.83 THEN
        RAISE EXCEPTION
            'ETL-195B CONTROL FAILED: expected 937828270.83; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 380145955.79 THEN
        RAISE EXCEPTION
            'ETL-195B CONTROL FAILED: expected COVID 380145955.79; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-195B CONTROL FAILED: expected IIJA 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 380145955.79 THEN
        RAISE EXCEPTION
            'ETL-195B CONTROL FAILED: expected extraordinary 380145955.79; found %',
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-195B HARD CONTROL PASS';

END
$$;


/*
====================================================================================================
3. BUILD AWARD-LEVEL EVIDENCE

Important:
    STRING_AGG DISTINCT is used so that every materially distinct transaction
    description associated with an award is available to the classifier.

    We deliberately do not classify from only MIN(description).
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m195b_awards;

CREATE TEMP TABLE m195b_awards AS

SELECT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier,

    MIN(recipient_name)
        AS recipient_name,

    MIN(assistance_type_code)
        AS assistance_type_code,

    MIN(assistance_type_description)
        AS assistance_type_description,

    MIN(action_date)
        AS first_action_date,

    MAX(action_date)
        AS last_action_date,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year,

    COUNT(*)
        AS transaction_count,

    COUNT(*) FILTER
    (
        WHERE federal_action_obligation > 0
    ) AS positive_transaction_count,

    COUNT(*) FILTER
    (
        WHERE federal_action_obligation < 0
    ) AS negative_transaction_count,

    COUNT(*) FILTER
    (
        WHERE federal_action_obligation = 0
    ) AS zero_transaction_count,

    SUM(federal_action_obligation)
        AS net_obligation,

    SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0
        END
    ) AS covid_amount,

    SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0
        END
    ) AS iija_amount,

    SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0
        END
    ) AS extraordinary_amount,

    BOOL_OR(is_covid)
        AS has_covid,

    BOOL_OR(is_iija)
        AS has_iija,

    BOOL_OR(is_extraordinary)
        AS has_extraordinary,

    STRING_AGG(
        DISTINCT NULLIF(TRIM(transaction_description), ''),
        ' || '
        ORDER BY NULLIF(TRIM(transaction_description), '')
    ) AS transaction_descriptions,

    STRING_AGG(
        DISTINCT NULLIF(TRIM(canonical_award_description), ''),
        ' || '
        ORDER BY NULLIF(TRIM(canonical_award_description), '')
    ) AS award_descriptions

FROM m195b_ui

GROUP BY
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    );


ANALYZE m195b_awards;


/*
====================================================================================================
4. AWARD-LEVEL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. AWARD-LEVEL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS award_count,
    SUM(transaction_count) AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(covid_amount)::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(iija_amount)::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(extraordinary_amount)::numeric,
        2
    ) AS extraordinary_amount

FROM m195b_awards;


DO $$
DECLARE
    v_awards bigint;
    v_tx     bigint;
    v_amount numeric;
BEGIN

    SELECT
        COUNT(*),
        SUM(transaction_count),
        COALESCE(SUM(net_obligation), 0)

    INTO
        v_awards,
        v_tx,
        v_amount

    FROM m195b_awards;


    IF v_awards <> 26
       OR v_tx <> 201
       OR ROUND(v_amount, 2) <> 937828270.83
    THEN
        RAISE EXCEPTION
            'ETL-195B AWARD COLLAPSE FAILED: awards=% tx=% amount=%',
            v_awards,
            v_tx,
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-195B AWARD COLLAPSE PASS';

END
$$;


/*
====================================================================================================
5. CREATE NORMALIZED SEMANTIC TEXT
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m195b_award_semantics;

CREATE TEMP TABLE m195b_award_semantics AS

SELECT
    a.*,

    LOWER(
        COALESCE(a.transaction_descriptions, '')
        || ' '
        || COALESCE(a.award_descriptions, '')
    ) AS semantic_text

FROM m195b_awards a;


/*
====================================================================================================
6. EMPIRICAL AWARD-COMPONENT PARTITION

Rule ordering matters.

Specific program semantics are evaluated before generic UI terminology.

COVID_PANDEMIC_UI intentionally captures an award when its evidence explicitly
identifies one or more of the temporary pandemic unemployment-compensation
programs or describes COVID-pandemic UI benefit funding.

The classifier does NOT attempt to split administration from benefits inside
a single pandemic award. That question is retained for the overlap screen.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m195b_partition;

CREATE TEMP TABLE m195b_partition AS

SELECT
    s.*,

    CASE

        /*
        ---------------------------------------------------------------------------------------------
        PANDEMIC UI
        ---------------------------------------------------------------------------------------------
        */

        WHEN
               semantic_text LIKE '%pandemic unemployment assistance%'
            OR semantic_text LIKE '%pandemic emergency unemployment compensation%'
            OR semantic_text LIKE '%federal pandemic unemployment compensation%'
            OR semantic_text LIKE '%mixed earners unemployment compensation%'
            OR semantic_text LIKE '%covid-19 pandemic ui%'
            OR semantic_text LIKE '%covid 19 pandemic ui%'
            OR semantic_text LIKE '%temporary emergency increase in unemployment compensation%'
        THEN 'COVID_PANDEMIC_UI'


        /*
        ---------------------------------------------------------------------------------------------
        TRADE ADJUSTMENT BENEFIT SUPPORT
        ---------------------------------------------------------------------------------------------
        */

        WHEN
               semantic_text LIKE '%trade adjustment assistance%'
            OR semantic_text LIKE '%trade readjustment allowance%'
            OR semantic_text LIKE '%trade readjustment allowances%'
        THEN 'TRADE_ADJUSTMENT_BENEFITS'


        /*
        ---------------------------------------------------------------------------------------------
        RESEA
        ---------------------------------------------------------------------------------------------
        */

        WHEN
               semantic_text LIKE '%reemployment services and eligibility assessment%'
            OR semantic_text LIKE '%reemployment services and eligibility assessments%'
            OR semantic_text LIKE '%resea%'
        THEN 'RESEA'


        /*
        ---------------------------------------------------------------------------------------------
        SHORT-TIME COMPENSATION
        ---------------------------------------------------------------------------------------------
        */

        WHEN
               semantic_text LIKE '%short-time compensation%'
            OR semantic_text LIKE '%short time compensation%'
        THEN 'SHORT_TIME_COMPENSATION'


        /*
        ---------------------------------------------------------------------------------------------
        UI INTEGRITY / FRAUD / EQUITY / SYSTEM IMPROVEMENT
        ---------------------------------------------------------------------------------------------
        */

        WHEN
               semantic_text LIKE '%fraud%'
            OR semantic_text LIKE '%identity verification%'
            OR semantic_text LIKE '%identity theft%'
            OR semantic_text LIKE '%program integrity%'
            OR semantic_text LIKE '%improper payment%'
            OR semantic_text LIKE '%equity%'
            OR semantic_text LIKE '%claimant experience%'
            OR semantic_text LIKE '%modernization%'
            OR semantic_text LIKE '%information technology%'
            OR semantic_text LIKE '%technology improvement%'
            OR semantic_text LIKE '%system improvement%'
        THEN 'UI_INTEGRITY_FRAUD_EQUITY'


        /*
        ---------------------------------------------------------------------------------------------
        ORDINARY UI ADMINISTRATION
        ---------------------------------------------------------------------------------------------
        */

        WHEN
               semantic_text LIKE '%administration of the unemployment insurance%'
            OR semantic_text LIKE '%administration of unemployment insurance%'
            OR semantic_text LIKE '%operate the unemployment insurance%'
            OR semantic_text LIKE '%operation of the unemployment insurance%'
            OR semantic_text LIKE '%costs of operating%'
            OR semantic_text LIKE '%administrative costs%'
            OR semantic_text LIKE '%administrative workload%'
            OR semantic_text LIKE '%unemployment insurance administration%'
        THEN 'UI_ADMINISTRATION'


        /*
        ---------------------------------------------------------------------------------------------
        OTHER IDENTIFIED UI
        ---------------------------------------------------------------------------------------------
        */

        WHEN semantic_text LIKE '%unemployment insurance%'
        THEN 'OTHER_IDENTIFIED_UI'


        ELSE 'UNRESOLVED'

    END AS diagnostic_component

FROM m195b_award_semantics s;


/*
====================================================================================================
7. COMPLETE 26-AWARD PARTITION

This is the central output of ETL-195B.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. COMPLETE 26-AWARD COMPONENT PARTITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    award_identifier,
    diagnostic_component,
    recipient_name,
    assistance_type_code,
    first_action_date,
    last_action_date,
    transaction_count,
    positive_transaction_count,
    negative_transaction_count,
    zero_transaction_count,

    ROUND(net_obligation::numeric, 2)
        AS net_obligation,

    ROUND(covid_amount::numeric, 2)
        AS covid_amount,

    ROUND(iija_amount::numeric, 2)
        AS iija_amount,

    ROUND(extraordinary_amount::numeric, 2)
        AS extraordinary_amount,

    LEFT(
        COALESCE(award_descriptions, transaction_descriptions),
        1000
    ) AS evidence_excerpt

FROM m195b_partition

ORDER BY
    diagnostic_component,
    ABS(net_obligation) DESC,
    award_identifier;


/*
====================================================================================================
8. COMPONENT SUMMARY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. COMPONENT SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    diagnostic_component,

    COUNT(*) AS award_count,

    SUM(transaction_count)
        AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(covid_amount)::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(iija_amount)::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(extraordinary_amount)::numeric,
        2
    ) AS extraordinary_amount

FROM m195b_partition

GROUP BY diagnostic_component

ORDER BY
    ABS(SUM(net_obligation)) DESC;


/*
====================================================================================================
9. EXACT COMPONENT RECONCILIATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. EXACT COMPONENT RECONCILIATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_awards bigint;
    v_tx     bigint;
    v_amount numeric;
    v_covid  numeric;
    v_iija   numeric;
    v_extra  numeric;
BEGIN

    SELECT
        COUNT(*),
        SUM(transaction_count),
        COALESCE(SUM(net_obligation), 0),
        COALESCE(SUM(covid_amount), 0),
        COALESCE(SUM(iija_amount), 0),
        COALESCE(SUM(extraordinary_amount), 0)

    INTO
        v_awards,
        v_tx,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m195b_partition;


    IF v_awards <> 26 THEN
        RAISE EXCEPTION
            'ETL-195B PARTITION FAILED: expected 26 awards; found %',
            v_awards;
    END IF;


    IF v_tx <> 201 THEN
        RAISE EXCEPTION
            'ETL-195B PARTITION FAILED: expected 201 transactions; found %',
            v_tx;
    END IF;


    IF ROUND(v_amount, 2) <> 937828270.83 THEN
        RAISE EXCEPTION
            'ETL-195B PARTITION FAILED: expected 937828270.83; found %',
            ROUND(v_amount, 2);
    END IF;


    IF ROUND(v_covid, 2) <> 380145955.79 THEN
        RAISE EXCEPTION
            'ETL-195B PARTITION FAILED: expected COVID 380145955.79; found %',
            ROUND(v_covid, 2);
    END IF;


    IF ROUND(v_iija, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-195B PARTITION FAILED: expected IIJA 0.00; found %',
            ROUND(v_iija, 2);
    END IF;


    IF ROUND(v_extra, 2) <> 380145955.79 THEN
        RAISE EXCEPTION
            'ETL-195B PARTITION FAILED: expected extraordinary 380145955.79; found %',
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-195B EXACT COMPONENT RECONCILIATION PASS';

END
$$;


/*
====================================================================================================
10. COMPONENT x FISCAL YEAR

Use original transactions here rather than allocating an award total across
years.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. COMPONENT x FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    l.action_date_fiscal_year
        AS fiscal_year,

    p.diagnostic_component,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        )
    ) AS award_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN l.is_covid
             THEN l.federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS covid_amount

FROM m195b_ui l

JOIN m195b_partition p
  ON p.award_identifier =
     COALESCE(
         NULLIF(l.award_id_fain, ''),
         NULLIF(l.award_id_uri, '')
     )

GROUP BY
    l.action_date_fiscal_year,
    p.diagnostic_component

ORDER BY
    l.action_date_fiscal_year,
    ABS(SUM(l.federal_action_obligation)) DESC;


/*
====================================================================================================
11. BENEFIT-LIKE AWARD SCREEN

This is deliberately broader than the component classifier.

Question:
    Which awards contain explicit evidence that federal dollars fund actual
    unemployment compensation / benefits paid to individuals?

This does NOT conclude duplication. It identifies the population for which
overlap deserves special scrutiny.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m195b_benefit_screen;

CREATE TEMP TABLE m195b_benefit_screen AS

SELECT
    p.*,

    CASE

        WHEN
               semantic_text LIKE '%additional unemployment benefits paid%'
            OR semantic_text LIKE '%unemployment benefits paid out%'
            OR semantic_text LIKE '%pay unemployment compensation%'
            OR semantic_text LIKE '%pays unemployment compensation%'
            OR semantic_text LIKE '%unemployment compensation to individual%'
            OR semantic_text LIKE '%benefit payments to eligible individual%'
            OR semantic_text LIKE '%benefits to eligible individual%'
            OR semantic_text LIKE '%trade readjustment allowance%'
            OR semantic_text LIKE '%trade readjustment allowances%'
        THEN TRUE

        ELSE FALSE

    END AS explicit_benefit_funding

FROM m195b_partition p;


/*
====================================================================================================
12. BENEFIT-LIKE POPULATION SUMMARY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. BENEFIT-LIKE POPULATION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    explicit_benefit_funding,

    COUNT(*) AS award_count,

    SUM(transaction_count)
        AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(covid_amount)::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(extraordinary_amount)::numeric,
        2
    ) AS extraordinary_amount

FROM m195b_benefit_screen

GROUP BY explicit_benefit_funding

ORDER BY explicit_benefit_funding DESC;


/*
====================================================================================================
13. BENEFIT-LIKE AWARD DETAIL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. BENEFIT-LIKE AWARD DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    award_identifier,
    diagnostic_component,
    recipient_name,
    first_action_date,
    last_action_date,
    transaction_count,

    ROUND(net_obligation::numeric, 2)
        AS net_obligation,

    ROUND(covid_amount::numeric, 2)
        AS covid_amount,

    LEFT(
        COALESCE(award_descriptions, transaction_descriptions),
        2000
    ) AS evidence_excerpt

FROM m195b_benefit_screen

WHERE explicit_benefit_funding

ORDER BY ABS(net_obligation) DESC;


/*
====================================================================================================
14. BENEFIT-LIKE TRANSACTIONS BY FISCAL YEAR
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. BENEFIT-LIKE TRANSACTIONS BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    l.action_date_fiscal_year
        AS fiscal_year,

    b.diagnostic_component,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(l.award_id_fain, ''),
            NULLIF(l.award_id_uri, '')
        )
    ) AS award_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN l.is_covid
             THEN l.federal_action_obligation
             ELSE 0
        END
    )::numeric, 2) AS covid_amount

FROM m195b_ui l

JOIN m195b_benefit_screen b
  ON b.award_identifier =
     COALESCE(
         NULLIF(l.award_id_fain, ''),
         NULLIF(l.award_id_uri, '')
     )

WHERE b.explicit_benefit_funding

GROUP BY
    l.action_date_fiscal_year,
    b.diagnostic_component

ORDER BY
    l.action_date_fiscal_year,
    b.diagnostic_component;


/*
====================================================================================================
15. PANDEMIC AWARD DETAIL

We want to see the complete award-level population that the classifier regards
as COVID pandemic UI, including whether individual awards mix COVID and
non-COVID transactions.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. COVID PANDEMIC UI AWARD DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    award_identifier,
    recipient_name,
    first_action_date,
    last_action_date,
    transaction_count,

    ROUND(net_obligation::numeric, 2)
        AS net_obligation,

    ROUND(covid_amount::numeric, 2)
        AS covid_amount,

    ROUND(
        (net_obligation - covid_amount)::numeric,
        2
    ) AS non_covid_amount,

    LEFT(
        COALESCE(award_descriptions, transaction_descriptions),
        2000
    ) AS evidence_excerpt

FROM m195b_partition

WHERE diagnostic_component = 'COVID_PANDEMIC_UI'

ORDER BY ABS(net_obligation) DESC;


/*
====================================================================================================
16. PANDEMIC AWARD x PROVENANCE

This is important because ETL-195A showed that at least some award identifiers
can contain both COVID and non-COVID observations.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. PANDEMIC AWARD x PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ) AS award_identifier,

    l.is_covid,
    l.is_extraordinary,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m195b_ui l

JOIN m195b_partition p
  ON p.award_identifier =
     COALESCE(
         NULLIF(l.award_id_fain, ''),
         NULLIF(l.award_id_uri, '')
     )

WHERE p.diagnostic_component = 'COVID_PANDEMIC_UI'

GROUP BY
    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ),
    l.is_covid,
    l.is_extraordinary

ORDER BY
    award_identifier,
    is_covid DESC,
    is_extraordinary DESC;


/*
====================================================================================================
17. TRANSACTION-LEVEL PANDEMIC DETAIL

Limited to pandemic awards. This lets us determine whether individual
transactions within those awards have descriptions specific enough for a
benefit/admin partition if one proves necessary.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. TRANSACTION-LEVEL PANDEMIC DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    l.action_date_fiscal_year
        AS fiscal_year,

    l.action_date,

    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ) AS award_identifier,

    l.federal_action_obligation,
    l.is_covid,
    l.is_extraordinary,
    l.assistance_type_code,

    LEFT(
        COALESCE(l.transaction_description, ''),
        2500
    ) AS transaction_description

FROM m195b_ui l

JOIN m195b_partition p
  ON p.award_identifier =
     COALESCE(
         NULLIF(l.award_id_fain, ''),
         NULLIF(l.award_id_uri, '')
     )

WHERE p.diagnostic_component = 'COVID_PANDEMIC_UI'

ORDER BY
    award_identifier,
    l.action_date,
    l.assistance_transaction_id;


/*
====================================================================================================
18. UNRESOLVED AWARDS

A nonzero unresolved population means we should NOT proceed to migration
without reviewing those awards.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. UNRESOLVED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    award_identifier,
    recipient_name,
    transaction_count,

    ROUND(net_obligation::numeric, 2)
        AS net_obligation,

    ROUND(covid_amount::numeric, 2)
        AS covid_amount,

    LEFT(
        COALESCE(award_descriptions, transaction_descriptions),
        3000
    ) AS evidence_excerpt

FROM m195b_partition

WHERE diagnostic_component = 'UNRESOLVED'

ORDER BY ABS(net_obligation) DESC;


/*
====================================================================================================
19. SHARED AWARD IDENTIFIER SCREEN

Repeat ETL-195A independently at the award-partition stage.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '19. SHARED AWARD IDENTIFIER SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH other_al AS
(
    SELECT
        p.award_identifier,
        p.diagnostic_component,

        l.cfda_number
            AS other_assistance_listing,

        COUNT(*) AS transaction_count,

        ROUND(
            SUM(l.federal_action_obligation)::numeric,
            2
        ) AS net_obligation

    FROM m195b_partition p

    JOIN analysis.v_certified_assistance_ledger l
      ON p.award_identifier =
         COALESCE(
             NULLIF(l.award_id_fain, ''),
             NULLIF(l.award_id_uri, '')
         )

    WHERE l.reference_state_abbreviation = 'WA'
      AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
      AND l.cfda_number <> '17.225'

    GROUP BY
        p.award_identifier,
        p.diagnostic_component,
        l.cfda_number
)

SELECT *
FROM other_al

ORDER BY
    ABS(net_obligation) DESC,
    award_identifier,
    other_assistance_listing;


/*
====================================================================================================
20. EXISTING SOURCE-POLICY OVERLAP SCREEN

This is not an automatic overlap determination.

It simply puts the existing WCFFBP social-insurance / income-security policies
next to the benefit-like AL 17.225 population for methodological review.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '20. EXISTING POTENTIALLY RELATED SOURCE POLICIES'
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

WHERE
       UPPER(COALESCE(inflow_family, '')) LIKE '%UNEMPLOY%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%UNEMPLOY%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%INCOME%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%INCOME%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%LABOR%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%LABOR%'

ORDER BY
    inflow_family,
    inflow_subfamily,
    federal_inflow_source_policy_id;


/*
====================================================================================================
21. CURRENT 17.225 CLASSIFICATION / MAPPING GUARD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '21. CURRENT AL 17.225 CLASSIFICATION / MAPPING GUARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '17.225';


SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '17.225';


/*
====================================================================================================
22. FINAL DECISION TABLE

Compact table intended to be the principal human-review artifact.

No accounting disposition is assigned here.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '22. FINAL AWARD DECISION TABLE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    p.award_identifier,
    p.diagnostic_component,

    b.explicit_benefit_funding,

    p.has_covid,
    p.has_extraordinary,

    p.first_fiscal_year,
    p.last_fiscal_year,

    p.transaction_count,

    ROUND(p.net_obligation::numeric, 2)
        AS net_obligation,

    ROUND(p.covid_amount::numeric, 2)
        AS covid_amount,

    p.recipient_name

FROM m195b_partition p

JOIN m195b_benefit_screen b
  ON b.award_identifier = p.award_identifier

ORDER BY
    ABS(p.net_obligation) DESC,
    p.award_identifier;


/*
====================================================================================================
23. FINAL CONTROL AND CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '23. FINAL CONTROL AND CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS award_count,

    SUM(transaction_count)
        AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(covid_amount)::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(iija_amount)::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(extraordinary_amount)::numeric,
        2
    ) AS extraordinary_amount,

    COUNT(*) FILTER
    (
        WHERE diagnostic_component = 'UNRESOLVED'
    ) AS unresolved_award_count,

    ROUND(
        COALESCE(
            SUM(net_obligation) FILTER
            (
                WHERE diagnostic_component = 'UNRESOLVED'
            ),
            0
        )::numeric,
        2
    ) AS unresolved_net_obligation

FROM m195b_partition;


DO $$
DECLARE
    v_awards       bigint;
    v_tx           bigint;
    v_amount       numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
BEGIN

    SELECT
        COUNT(*),
        SUM(transaction_count),
        COALESCE(SUM(net_obligation), 0),
        COALESCE(SUM(covid_amount), 0),
        COALESCE(SUM(iija_amount), 0),
        COALESCE(SUM(extraordinary_amount), 0)

    INTO
        v_awards,
        v_tx,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m195b_partition;


    IF v_awards <> 26
       OR v_tx <> 201
       OR ROUND(v_amount, 2) <> 937828270.83
       OR ROUND(v_covid, 2) <> 380145955.79
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 380145955.79
    THEN
        RAISE EXCEPTION
            'ETL-195B FINAL CONTROL FAILED';
    END IF;


    RAISE NOTICE
        'ETL-195B FINAL CONTROL PASS: awards=% tx=% amount=% COVID=% IIJA=% extraordinary=%',
        v_awards,
        v_tx,
        ROUND(v_amount, 2),
        ROUND(v_covid, 2),
        ROUND(v_iija, 2),
        ROUND(v_extra, 2);

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-195B COMPLETE'
\echo ''
\echo 'Expected focal population:'
\echo '  201 transactions'
\echo '   26 awards'
\echo '    2 recipients'
\echo '  $937,828,270.83 net obligation'
\echo '  $380,145,955.79 COVID / extraordinary'
\echo '  $0 IIJA'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting disposition assigned.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;