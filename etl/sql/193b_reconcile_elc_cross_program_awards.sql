/*
====================================================================================================
ETL-193B
ELC CROSS-PROGRAM AWARD RECONCILIATION
AL 93.323
====================================================================================================

Purpose:
    Investigate the cross-program award-identifier collisions discovered by
    ETL-193A for Washington FY2020-FY2024 Assistance Listing 93.323:

        Epidemiology and Laboratory Capacity for Infectious Diseases (ELC)

ETL-193A established:

    ELC transactions                         360
    ELC awards                                12
    ELC recipients                             5
    ELC net obligation          $990,041,302.24

    COVID                       $987,883,249.28
    IIJA                                   $0.00
    extraordinary                $987,883,249.28

    ELC award identifiers colliding
        with another AL                       12

    Other AL numbers involved                 17

Primary question:
    Do shared CDC award identifiers merely span multiple Assistance Listings,
    with distinct obligation transactions/components, or do the same federal
    obligation dollars appear under multiple AL numbers?

Accounting principle:
    Shared award identifier != duplicate federal inflow.

    Duplication requires stronger evidence, such as the same award identifier
    carrying the same obligation event under multiple Assistance Listings.

This diagnostic therefore tests progressively stronger collision signatures:

    1. shared award identifier
    2. shared award identifier + action date
    3. shared award identifier + action date + obligation amount
    4. shared award identifier + action date + absolute obligation amount
    5. same-day cross-AL event detail for candidate matches

The absolute-amount screen is included because a positive obligation under one
AL and an equal negative adjustment under another AL may reveal a reclassification
or transfer rather than two independent additive inflows.

Special focus:
    NU50CK000515
        ELC net obligation approximately $974.683M
        also appears under AL 93.354 and AL 93.283

    NH23IP922619
        appears across several other Assistance Listings.

PROVENANCE:
    COVID, IIJA, and extraordinary status remain orthogonal reporting
    dimensions and are not additional accounting paths.

This script is READ ONLY.

It does NOT:
    - classify AL 93.323,
    - classify any comparison AL,
    - change ledger treatment,
    - infer county incidence,
    - modify persistent database objects.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-193B - ELC CROSS-PROGRAM AWARD RECONCILIATION'
\echo 'AL 93.323'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD ELC FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m193b_elc;

CREATE TEMP TABLE m193b_elc AS

SELECT *
FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.323';


/*
====================================================================================================
2. HARD ELC CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. HARD ELC CONTROL'
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

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

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

FROM m193b_elc;


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

    FROM m193b_elc;


    IF v_tx <> 360
       OR v_awards <> 12
       OR v_recip <> 5
       OR ROUND(v_amount, 2) <> 990041302.24
       OR ROUND(v_covid, 2) <> 987883249.28
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 987883249.28 THEN

        RAISE EXCEPTION
            'ETL-193B focal control failed: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;

    RAISE NOTICE
        'ETL-193B HARD ELC CONTROL PASS';
END
$$;


/*
====================================================================================================
3. BUILD SHARED-AWARD COMPARISON POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m193b_shared_awards;

CREATE TEMP TABLE m193b_shared_awards AS

SELECT DISTINCT
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS award_identifier

FROM m193b_elc

WHERE COALESCE(
          NULLIF(award_id_fain, ''),
          NULLIF(award_id_uri, '')
      ) IS NOT NULL;


DROP TABLE IF EXISTS pg_temp.m193b_comparison;

CREATE TEMP TABLE m193b_comparison AS

SELECT
    b.assistance_transaction_id,

    COALESCE(
        NULLIF(b.award_id_fain, ''),
        NULLIF(b.award_id_uri, '')
    ) AS shared_award_identifier,

    b.cfda_number,
    b.action_date,
    b.action_date_fiscal_year,
    b.federal_action_obligation,

    b.is_covid,
    b.is_iija,
    b.is_extraordinary,

    b.transaction_description,
    b.canonical_award_description

FROM analysis.v_certified_assistance_ledger b

WHERE b.reference_state_abbreviation = 'WA'
  AND b.action_date_fiscal_year BETWEEN 2020 AND 2024

  AND COALESCE(
        NULLIF(b.award_id_fain, ''),
        NULLIF(b.award_id_uri, '')
      ) IN
      (
          SELECT award_identifier
          FROM m193b_shared_awards
      );

CREATE INDEX m193b_comparison_award_idx
    ON m193b_comparison (shared_award_identifier);

CREATE INDEX m193b_comparison_award_date_idx
    ON m193b_comparison (
        shared_award_identifier,
        action_date
    );

CREATE INDEX m193b_comparison_signature_idx
    ON m193b_comparison (
        shared_award_identifier,
        action_date,
        federal_action_obligation
    );

ANALYZE m193b_comparison;

/*
====================================================================================================
4. SHARED-AWARD UNIVERSE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. SHARED-AWARD UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(DISTINCT shared_award_identifier)
        AS award_count,

    COUNT(DISTINCT cfda_number)
        AS program_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation

FROM m193b_comparison;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4B. SHARED AWARDS BY ASSISTANCE LISTING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT shared_award_identifier)
        AS shared_award_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

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

FROM m193b_comparison

GROUP BY cfda_number

ORDER BY
    CASE WHEN cfda_number = '93.323' THEN 0 ELSE 1 END,
    ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
5. AWARD × ASSISTANCE-LISTING MATRIX

This shows how each source award identifier is partitioned across AL numbers.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. AWARD x ASSISTANCE-LISTING MATRIX'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    shared_award_identifier,
    cfda_number,

    COUNT(*) AS transaction_count,

    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

    ROUND(SUM(
        CASE WHEN federal_action_obligation > 0
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS positive_obligation,

    ROUND(SUM(
        CASE WHEN federal_action_obligation < 0
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS negative_obligation,

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

FROM m193b_comparison

GROUP BY
    shared_award_identifier,
    cfda_number

ORDER BY
    shared_award_identifier,
    cfda_number;


/*
====================================================================================================
6. SHARED AWARD + ACTION DATE COLLISIONS

A same-day appearance is stronger evidence than award-ID sharing alone,
but still does not prove duplicate dollars.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6A. SHARED AWARD + ACTION DATE COLLISION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH event_days AS
(
    SELECT
        shared_award_identifier,
        action_date,

        COUNT(DISTINCT cfda_number)
            AS program_count,

        COUNT(*) AS transaction_count,

        ROUND(SUM(federal_action_obligation)::numeric, 2)
            AS net_obligation

    FROM m193b_comparison

    GROUP BY
        shared_award_identifier,
        action_date

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    COUNT(*) AS cross_program_award_date_events,

    COUNT(DISTINCT shared_award_identifier)
        AS awards_with_cross_program_same_day_events,

    COALESCE(SUM(transaction_count), 0)
        AS transactions_on_cross_program_event_days

FROM event_days;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6B. SHARED AWARD + ACTION DATE COLLISION DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

WITH collision_days AS
(
    SELECT
        shared_award_identifier,
        action_date

    FROM m193b_comparison

    GROUP BY
        shared_award_identifier,
        action_date

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    c.shared_award_identifier,
    c.action_date,
    c.cfda_number,

    COUNT(*) AS transaction_count,

    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligation,

    MIN(c.transaction_description)
        AS sample_transaction_description

FROM m193b_comparison c

JOIN collision_days d
  ON d.shared_award_identifier = c.shared_award_identifier
 AND d.action_date = c.action_date

GROUP BY
    c.shared_award_identifier,
    c.action_date,
    c.cfda_number

ORDER BY
    c.shared_award_identifier,
    c.action_date,
    c.cfda_number;


/*
====================================================================================================
7. EXACT OBLIGATION-SIGNATURE COLLISIONS

Signature:
    shared award identifier
    + action date
    + exact signed federal action obligation

This is substantially stronger evidence of possible duplication.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7A. EXACT SIGNED OBLIGATION COLLISION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        action_date,
        federal_action_obligation,

        COUNT(DISTINCT cfda_number)
            AS program_count,

        COUNT(*) AS transaction_count

    FROM m193b_comparison

    GROUP BY
        shared_award_identifier,
        action_date,
        federal_action_obligation

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    COUNT(*) AS exact_cross_program_signatures,

    COUNT(DISTINCT shared_award_identifier)
        AS affected_awards,

    COALESCE(SUM(transaction_count), 0)
        AS transactions_in_exact_signatures

FROM signatures;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7B. EXACT SIGNED OBLIGATION COLLISION DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        action_date,
        federal_action_obligation

    FROM m193b_comparison

    GROUP BY
        shared_award_identifier,
        action_date,
        federal_action_obligation

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    c.shared_award_identifier,
    c.action_date,
    c.cfda_number,

    ROUND(c.federal_action_obligation::numeric, 2)
        AS federal_action_obligation,

    c.assistance_transaction_id,

    c.transaction_description,

    c.canonical_award_description

FROM m193b_comparison c

JOIN signatures s
  ON s.shared_award_identifier = c.shared_award_identifier
 AND s.action_date = c.action_date
 AND s.federal_action_obligation = c.federal_action_obligation

ORDER BY
    c.shared_award_identifier,
    c.action_date,
    c.federal_action_obligation,
    c.cfda_number,
    c.assistance_transaction_id;


/*
====================================================================================================
8. ABSOLUTE OBLIGATION-SIGNATURE COLLISIONS

Purpose:
    Detect same award + same day + same absolute dollar amount across different
    AL numbers, including opposite-sign pairs.

Example:
    +$X under one AL
    -$X under another AL

Such pairs may indicate reclassification or correction and deserve special
attention.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8A. ABSOLUTE OBLIGATION COLLISION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        action_date,
        ABS(federal_action_obligation)
            AS absolute_obligation,

        COUNT(DISTINCT cfda_number)
            AS program_count,

        COUNT(*) AS transaction_count

    FROM m193b_comparison

    WHERE federal_action_obligation <> 0

    GROUP BY
        shared_award_identifier,
        action_date,
        ABS(federal_action_obligation)

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    COUNT(*) AS absolute_cross_program_signatures,

    COUNT(DISTINCT shared_award_identifier)
        AS affected_awards,

    COALESCE(SUM(transaction_count), 0)
        AS transactions_in_absolute_signatures

FROM signatures;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8B. ABSOLUTE OBLIGATION COLLISION DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        action_date,
        ABS(federal_action_obligation)
            AS absolute_obligation

    FROM m193b_comparison

    WHERE federal_action_obligation <> 0

    GROUP BY
        shared_award_identifier,
        action_date,
        ABS(federal_action_obligation)

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    c.shared_award_identifier,
    c.action_date,
    c.cfda_number,

    ROUND(c.federal_action_obligation::numeric, 2)
        AS federal_action_obligation,

    c.assistance_transaction_id,

    c.transaction_description,

    c.canonical_award_description

FROM m193b_comparison c

JOIN signatures s
  ON s.shared_award_identifier = c.shared_award_identifier
 AND s.action_date = c.action_date
 AND s.absolute_obligation = ABS(c.federal_action_obligation)

ORDER BY
    c.shared_award_identifier,
    c.action_date,
    ABS(c.federal_action_obligation),
    c.cfda_number,
    c.assistance_transaction_id;


/*
====================================================================================================
9. SAME-DAY CROSS-PROGRAM NETTING SCREEN

Purpose:
    Identify same award/date combinations where multiple AL numbers appear and
    their combined obligations may reveal reclassification or transfer behavior.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. SAME-DAY CROSS-PROGRAM NETTING SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH collision_days AS
(
    SELECT
        shared_award_identifier,
        action_date

    FROM m193b_comparison

    GROUP BY
        shared_award_identifier,
        action_date

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    c.shared_award_identifier,
    c.action_date,

    COUNT(DISTINCT c.cfda_number)
        AS program_count,

    STRING_AGG(
        DISTINCT c.cfda_number,
        ', '
        ORDER BY c.cfda_number
    ) AS program_codes,

    COUNT(*) AS transaction_count,

    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS combined_net_obligation,

    ROUND(SUM(
        CASE WHEN c.federal_action_obligation > 0
             THEN c.federal_action_obligation ELSE 0 END
    )::numeric, 2) AS positive_obligation,

    ROUND(SUM(
        CASE WHEN c.federal_action_obligation < 0
             THEN c.federal_action_obligation ELSE 0 END
    )::numeric, 2) AS negative_obligation

FROM m193b_comparison c

JOIN collision_days d
  ON d.shared_award_identifier = c.shared_award_identifier
 AND d.action_date = c.action_date

GROUP BY
    c.shared_award_identifier,
    c.action_date

ORDER BY
    ABS(SUM(c.federal_action_obligation)) DESC,
    c.shared_award_identifier,
    c.action_date;


/*
====================================================================================================
10. FOCUS AWARD: NU50CK000515

Dominant ELC award. ETL-193A found:
    93.323       +$974,683,109.28
    93.354        -$69,280,349.93
    93.283         +$1,030,895.00
    93.322                 $0.00

Show complete transaction history across all AL numbers.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10A. NU50CK000515 PROGRAM SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    COUNT(*) AS transaction_count,

    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

    ROUND(SUM(
        CASE WHEN federal_action_obligation > 0
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS positive_obligation,

    ROUND(SUM(
        CASE WHEN federal_action_obligation < 0
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS negative_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount

FROM m193b_comparison

WHERE shared_award_identifier = 'NU50CK000515'

GROUP BY cfda_number
ORDER BY cfda_number;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10B. NU50CK000515 COMPLETE TRANSACTION HISTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date,
    action_date_fiscal_year AS fiscal_year,
    cfda_number,

    ROUND(federal_action_obligation::numeric, 2)
        AS federal_action_obligation,

    is_covid,
    is_iija,
    is_extraordinary,

    assistance_transaction_id,

    transaction_description

FROM m193b_comparison

WHERE shared_award_identifier = 'NU50CK000515'

ORDER BY
    action_date,
    cfda_number,
    federal_action_obligation,
    assistance_transaction_id;


/*
====================================================================================================
11. FOCUS AWARD: NH23IP922619

This award identifier appears across numerous Assistance Listings.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11A. NH23IP922619 PROGRAM SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    COUNT(*) AS transaction_count,

    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

    ROUND(SUM(
        CASE WHEN federal_action_obligation > 0
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS positive_obligation,

    ROUND(SUM(
        CASE WHEN federal_action_obligation < 0
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS negative_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount

FROM m193b_comparison

WHERE shared_award_identifier = 'NH23IP922619'

GROUP BY cfda_number
ORDER BY cfda_number;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11B. NH23IP922619 COMPLETE TRANSACTION HISTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date,
    action_date_fiscal_year AS fiscal_year,
    cfda_number,

    ROUND(federal_action_obligation::numeric, 2)
        AS federal_action_obligation,

    is_covid,
    is_iija,
    is_extraordinary,

    assistance_transaction_id,

    transaction_description

FROM m193b_comparison

WHERE shared_award_identifier = 'NH23IP922619'

ORDER BY
    action_date,
    cfda_number,
    federal_action_obligation,
    assistance_transaction_id;


/*
====================================================================================================
12. CROSS-AL EXACT DESCRIPTION SCREEN

Same award + same action date + same transaction description across multiple
AL numbers can provide additional evidence of administrative recoding even
when dollar amounts differ.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12A. CROSS-AL EXACT DESCRIPTION COLLISION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        action_date,
        transaction_description,

        COUNT(DISTINCT cfda_number)
            AS program_count,

        COUNT(*) AS transaction_count

    FROM m193b_comparison

    WHERE NULLIF(BTRIM(transaction_description), '') IS NOT NULL

    GROUP BY
        shared_award_identifier,
        action_date,
        transaction_description

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    COUNT(*) AS description_collision_signatures,

    COUNT(DISTINCT shared_award_identifier)
        AS affected_awards,

    COALESCE(SUM(transaction_count), 0)
        AS transactions_in_description_collisions

FROM signatures;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12B. CROSS-AL EXACT DESCRIPTION COLLISION DETAIL'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        action_date,
        transaction_description

    FROM m193b_comparison

    WHERE NULLIF(BTRIM(transaction_description), '') IS NOT NULL

    GROUP BY
        shared_award_identifier,
        action_date,
        transaction_description

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    c.shared_award_identifier,
    c.action_date,
    c.cfda_number,

    ROUND(c.federal_action_obligation::numeric, 2)
        AS federal_action_obligation,

    c.assistance_transaction_id,

    c.transaction_description

FROM m193b_comparison c

JOIN signatures s
  ON s.shared_award_identifier = c.shared_award_identifier
 AND s.action_date = c.action_date
 AND s.transaction_description = c.transaction_description

ORDER BY
    c.shared_award_identifier,
    c.action_date,
    c.cfda_number,
    c.federal_action_obligation,
    c.assistance_transaction_id;


/*
====================================================================================================
13. CROSS-AL SAME-DOLLAR COLLISIONS WITHOUT DATE

This is intentionally weaker evidence.

Purpose:
    Determine whether the same signed obligation amount repeatedly occurs under
    different AL numbers for the same award, even if action dates differ.

This can reveal delayed recoding/reversal patterns that a same-day test misses.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13A. SAME AWARD + SAME SIGNED DOLLAR, DIFFERENT AL'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        federal_action_obligation,

        COUNT(DISTINCT cfda_number)
            AS program_count,

        COUNT(*) AS transaction_count,

        MIN(action_date) AS first_action_date,
        MAX(action_date) AS last_action_date

    FROM m193b_comparison

    WHERE federal_action_obligation <> 0

    GROUP BY
        shared_award_identifier,
        federal_action_obligation

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    shared_award_identifier,

    ROUND(federal_action_obligation::numeric, 2)
        AS federal_action_obligation,

    program_count,
    transaction_count,
    first_action_date,
    last_action_date

FROM signatures

ORDER BY
    ABS(federal_action_obligation) DESC,
    shared_award_identifier;


/*
====================================================================================================
14. SAME AWARD + SAME ABSOLUTE DOLLAR, DIFFERENT AL

This catches positive/negative transfer or reclassification patterns even when
the dates differ.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14A. SAME AWARD + SAME ABSOLUTE DOLLAR, DIFFERENT AL'
\echo '----------------------------------------------------------------------------------------------------'

WITH signatures AS
(
    SELECT
        shared_award_identifier,
        ABS(federal_action_obligation)
            AS absolute_obligation,

        COUNT(DISTINCT cfda_number)
            AS program_count,

        COUNT(*) AS transaction_count,

        MIN(action_date) AS first_action_date,
        MAX(action_date) AS last_action_date

    FROM m193b_comparison

    WHERE federal_action_obligation <> 0

    GROUP BY
        shared_award_identifier,
        ABS(federal_action_obligation)

    HAVING COUNT(DISTINCT cfda_number) > 1
)

SELECT
    shared_award_identifier,

    ROUND(absolute_obligation::numeric, 2)
        AS absolute_obligation,

    program_count,
    transaction_count,
    first_action_date,
    last_action_date

FROM signatures

ORDER BY
    absolute_obligation DESC,
    shared_award_identifier;


/*
====================================================================================================
15. CLOSURE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. CLOSURE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS closure_elc_transactions,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS closure_elc_awards,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS closure_elc_net_obligation,

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

FROM m193b_elc;


DO $$
DECLARE
    v_tx       bigint;
    v_awards   bigint;
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
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m193b_elc;


    IF v_tx <> 360
       OR v_awards <> 12
       OR ROUND(v_amount, 2) <> 990041302.24
       OR ROUND(v_covid, 2) <> 987883249.28
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 987883249.28 THEN

        RAISE EXCEPTION
            'ETL-193B closure control failed';
    END IF;


    RAISE NOTICE
        'ETL-193B CLOSURE PASS: tx=% awards=% amount=% COVID=% IIJA=% extraordinary=%',
        v_tx,
        v_awards,
        ROUND(v_amount, 2),
        ROUND(v_covid, 2),
        ROUND(v_iija, 2),
        ROUND(v_extra, 2);
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-193B COMPLETE'
\echo ''
\echo 'Interpretation rule:'
\echo '  Shared award identifier alone does NOT establish duplicate inflow.'
\echo '  Same award + same date + same signed/absolute obligation is stronger evidence.'
\echo '  Cross-AL reversal/reclassification patterns require accounting review.'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;