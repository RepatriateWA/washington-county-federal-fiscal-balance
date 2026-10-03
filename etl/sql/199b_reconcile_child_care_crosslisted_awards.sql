/*
====================================================================================================
ETL-199B
CHILD CARE MANDATORY / MATCHING FUNDS
CROSS-LISTED AWARD RECONCILIATION
AL 93.596

Purpose
-------
Reconcile the seven AL 93.596 award identifiers identified by ETL-199A as
appearing under one or more additional Assistance Listings.

Primary question
----------------
Do shared award identifiers represent:

    A. duplicate federal dollars;
    B. distinct federal program components administered under a common
       award / P.L. 102-477 structure; or
    C. a mixture requiring award-level accounting treatment?

This diagnostic is intentionally narrow.

No persistent database writes.
No accounting classification.
No county-incidence inference.

Known-good source columns are taken directly from ETL-199A.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-199B'
\echo 'CHILD CARE MANDATORY / MATCHING FUNDS'
\echo 'CROSS-LISTED AWARD RECONCILIATION'
\echo 'AL 93.596'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD NORMALIZED WA FY2020-FY2024 ASSISTANCE POPULATION

Create normalized diagnostic fields here so later sections do not depend on
unverified shorthand column names in the certified ledger view.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m199b_all;

CREATE TEMP TABLE m199b_all AS
SELECT
    l.*,

    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ) AS diagnostic_award_identifier,

    l.cfda_number
        AS diagnostic_program_code,

    l.cfda_title
        AS diagnostic_program_title,

    COALESCE(
        NULLIF(TRIM(l.transaction_description), ''),
        NULLIF(TRIM(l.canonical_award_description), ''),
        ''
    ) AS diagnostic_description

FROM analysis.v_certified_assistance_ledger AS l

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;


ANALYZE m199b_all;


/*
====================================================================================================
2. BUILD FOCAL AL 93.596 POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m199b_focal;

CREATE TEMP TABLE m199b_focal AS
SELECT *
FROM m199b_all
WHERE diagnostic_program_code = '93.596';


ANALYZE m199b_focal;


/*
====================================================================================================
3. RECONFIRM AL 93.596 HARD CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. RECONFIRM AL 93.596 HARD CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT diagnostic_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT recipient_id
    ) AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN is_covid
                THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN is_iija
                THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN is_extraordinary
                THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m199b_focal;


/*
====================================================================================================
4. IDENTIFY CROSS-LISTED FOCAL AWARD IDENTIFIERS
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m199b_crosslisted_awards;

CREATE TEMP TABLE m199b_crosslisted_awards AS
SELECT DISTINCT
    f.diagnostic_award_identifier
FROM m199b_focal AS f
WHERE f.diagnostic_award_identifier IS NOT NULL

  AND EXISTS
  (
      SELECT 1
      FROM m199b_all AS x

      WHERE x.diagnostic_award_identifier =
            f.diagnostic_award_identifier

        AND x.diagnostic_program_code <> '93.596'
  );


ANALYZE m199b_crosslisted_awards;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4A. CROSS-LISTED AWARD COUNT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS crosslisted_focal_award_count
FROM m199b_crosslisted_awards;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4B. CROSS-LISTED AWARD IDENTIFIERS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    diagnostic_award_identifier AS award_identifier
FROM m199b_crosslisted_awards
ORDER BY diagnostic_award_identifier;


/*
====================================================================================================
5. FOCAL 93.596 DOLLARS ASSOCIATED WITH CROSS-LISTED AWARDS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. FOCAL 93.596 DOLLARS ASSOCIATED WITH CROSS-LISTED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT f.diagnostic_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT f.recipient_id
    ) AS recipient_count,

    ROUND(
        SUM(f.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN f.federal_action_obligation > 0
                THEN f.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS positive_obligation,

    ROUND(SUM(
        CASE
            WHEN f.federal_action_obligation < 0
                THEN f.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS negative_obligation

FROM m199b_focal AS f

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     f.diagnostic_award_identifier;


/*
====================================================================================================
6. FOCAL 93.596 DOLLARS NOT ASSOCIATED WITH CROSS-LISTED AWARDS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. FOCAL 93.596 DOLLARS NOT ASSOCIATED WITH CROSS-LISTED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT f.diagnostic_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT f.recipient_id
    ) AS recipient_count,

    ROUND(
        SUM(f.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m199b_focal AS f

WHERE NOT EXISTS
(
    SELECT 1
    FROM m199b_crosslisted_awards AS c

    WHERE c.diagnostic_award_identifier =
          f.diagnostic_award_identifier
);


/*
====================================================================================================
7. CROSS-LISTED AWARDS — PROGRAM-BY-PROGRAM ACCOUNTING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. CROSS-LISTED AWARDS - PROGRAM-BY-PROGRAM ACCOUNTING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    x.diagnostic_award_identifier
        AS award_identifier,

    x.diagnostic_program_code
        AS assistance_listing,

    MIN(x.diagnostic_program_title)
        AS program_title,

    COUNT(*)
        AS transaction_count,

    COUNT(DISTINCT x.recipient_id)
        AS recipient_count,

    MIN(x.action_date)
        AS first_action_date,

    MAX(x.action_date)
        AS last_action_date,

    ROUND(SUM(
        CASE
            WHEN x.federal_action_obligation > 0
                THEN x.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS positive_obligation,

    ROUND(SUM(
        CASE
            WHEN x.federal_action_obligation < 0
                THEN x.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS negative_obligation,

    ROUND(
        SUM(x.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m199b_all AS x

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     x.diagnostic_award_identifier

GROUP BY
    x.diagnostic_award_identifier,
    x.diagnostic_program_code

ORDER BY
    x.diagnostic_award_identifier,
    x.diagnostic_program_code;


/*
====================================================================================================
8. EXACT SAME-DATE / SAME-AMOUNT CROSS-PROGRAM COLLISION SCREEN

This is our strongest simple transaction-level duplicate signal.

If the same award identifier, same action date, and same non-zero obligation
occur under different Assistance Listings, inspect those records closely.

Zero-dollar administrative transactions are excluded because identical zero
transactions do not establish duplicated federal dollars.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. EXACT SAME-DATE / SAME-AMOUNT CROSS-PROGRAM COLLISION SCREEN'
\echo '----------------------------------------------------------------------------------------------------'

WITH collision AS
(
    SELECT DISTINCT
        a.diagnostic_award_identifier
            AS award_identifier,

        a.action_date,

        a.diagnostic_program_code
            AS assistance_listing_a,

        a.diagnostic_program_title
            AS program_title_a,

        b.diagnostic_program_code
            AS assistance_listing_b,

        b.diagnostic_program_title
            AS program_title_b,

        a.federal_action_obligation,

        a.recipient_name,

        a.diagnostic_description
            AS description_a,

        b.diagnostic_description
            AS description_b

    FROM m199b_all AS a

    JOIN m199b_all AS b
      ON b.diagnostic_award_identifier =
         a.diagnostic_award_identifier

     AND b.action_date =
         a.action_date

     AND b.federal_action_obligation =
         a.federal_action_obligation

     AND b.diagnostic_program_code >
         a.diagnostic_program_code

    JOIN m199b_crosslisted_awards AS c
      ON c.diagnostic_award_identifier =
         a.diagnostic_award_identifier

    WHERE a.federal_action_obligation <> 0
)

SELECT *
FROM collision

ORDER BY
    award_identifier,
    action_date,
    assistance_listing_a,
    assistance_listing_b,
    federal_action_obligation;


/*
====================================================================================================
9. SAME-DATE CROSS-PROGRAM SCREEN REGARDLESS OF AMOUNT

A same-day occurrence with DIFFERENT amounts may simply represent distinct
program components processed together administratively.

This is contextual evidence, not itself duplicate evidence.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. SAME-DATE CROSS-PROGRAM SCREEN REGARDLESS OF AMOUNT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT DISTINCT
    a.diagnostic_award_identifier
        AS award_identifier,

    a.action_date,

    a.diagnostic_program_code
        AS assistance_listing_a,

    ROUND(
        a.federal_action_obligation::numeric,
        2
    ) AS obligation_a,

    b.diagnostic_program_code
        AS assistance_listing_b,

    ROUND(
        b.federal_action_obligation::numeric,
        2
    ) AS obligation_b,

    a.recipient_name

FROM m199b_all AS a

JOIN m199b_all AS b
  ON b.diagnostic_award_identifier =
     a.diagnostic_award_identifier

 AND b.action_date =
     a.action_date

 AND b.diagnostic_program_code >
     a.diagnostic_program_code

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     a.diagnostic_award_identifier

ORDER BY
    award_identifier,
    action_date,
    assistance_listing_a,
    assistance_listing_b,
    obligation_a,
    obligation_b;


/*
====================================================================================================
10. PROGRAM COMBINATION BY CROSS-LISTED AWARD
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. PROGRAM COMBINATION BY CROSS-LISTED AWARD'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    x.diagnostic_award_identifier
        AS award_identifier,

    STRING_AGG(
        DISTINCT x.diagnostic_program_code,
        ', '
        ORDER BY x.diagnostic_program_code
    ) AS assistance_listings,

    COUNT(
        DISTINCT x.diagnostic_program_code
    ) AS assistance_listing_count,

    ROUND(
        SUM(x.federal_action_obligation)::numeric,
        2
    ) AS combined_net_obligation

FROM m199b_all AS x

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     x.diagnostic_award_identifier

GROUP BY
    x.diagnostic_award_identifier

ORDER BY
    x.diagnostic_award_identifier;


/*
====================================================================================================
11. COMPLETE 93.596 TRANSACTION DETAIL FOR CROSS-LISTED AWARDS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. COMPLETE 93.596 TRANSACTION DETAIL FOR CROSS-LISTED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    f.diagnostic_award_identifier
        AS award_identifier,

    f.action_date,

    f.action_date_fiscal_year
        AS fiscal_year,

    ROUND(
        f.federal_action_obligation::numeric,
        2
    ) AS federal_action_obligation,

    f.recipient_name,

    f.funding_agency_name,
    f.funding_subagency_name,
    f.awarding_agency_name,
    f.awarding_subagency_name,

    f.assistance_type_code,
    f.assistance_type_description,

    f.is_covid,
    f.is_iija,
    f.is_extraordinary,

    LEFT(
        f.diagnostic_description,
        2000
    ) AS description

FROM m199b_focal AS f

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     f.diagnostic_award_identifier

ORDER BY
    award_identifier,
    action_date,
    federal_action_obligation;


/*
====================================================================================================
12. COMPLETE OTHER-PROGRAM TRANSACTION DETAIL FOR CROSS-LISTED AWARDS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. COMPLETE OTHER-PROGRAM TRANSACTION DETAIL FOR CROSS-LISTED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    x.diagnostic_award_identifier
        AS award_identifier,

    x.diagnostic_program_code
        AS assistance_listing,

    x.diagnostic_program_title
        AS program_title,

    x.action_date,

    x.action_date_fiscal_year
        AS fiscal_year,

    ROUND(
        x.federal_action_obligation::numeric,
        2
    ) AS federal_action_obligation,

    x.recipient_name,

    x.funding_agency_name,
    x.funding_subagency_name,
    x.awarding_agency_name,
    x.awarding_subagency_name,

    x.assistance_type_code,
    x.assistance_type_description,

    x.is_covid,
    x.is_iija,
    x.is_extraordinary,

    LEFT(
        x.diagnostic_description,
        2000
    ) AS description

FROM m199b_all AS x

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     x.diagnostic_award_identifier

WHERE x.diagnostic_program_code <> '93.596'

ORDER BY
    award_identifier,
    assistance_listing,
    action_date,
    federal_action_obligation;


/*
====================================================================================================
13. CROSS-LISTED DOLLAR CONCENTRATION BY OTHER ASSISTANCE LISTING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. CROSS-LISTED DOLLAR CONCENTRATION BY OTHER ASSISTANCE LISTING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    x.diagnostic_program_code
        AS assistance_listing,

    MIN(x.diagnostic_program_title)
        AS program_title,

    COUNT(*)
        AS transaction_count,

    COUNT(
        DISTINCT x.diagnostic_award_identifier
    ) AS shared_award_count,

    ROUND(
        SUM(x.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m199b_all AS x

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     x.diagnostic_award_identifier

WHERE x.diagnostic_program_code <> '93.596'

GROUP BY
    x.diagnostic_program_code

ORDER BY
    ABS(SUM(x.federal_action_obligation)) DESC;


/*
====================================================================================================
14. FOCAL CROSS-LISTED AWARD SUMMARY

This isolates only the 93.596 dollars that could conceivably require special
accounting treatment.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. FOCAL CROSS-LISTED AWARD SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    f.diagnostic_award_identifier
        AS award_identifier,

    MIN(f.recipient_name)
        AS recipient_name,

    COUNT(*)
        AS transaction_count,

    MIN(f.action_date)
        AS first_action_date,

    MAX(f.action_date)
        AS last_action_date,

    ROUND(SUM(
        CASE
            WHEN f.federal_action_obligation > 0
                THEN f.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS positive_obligation,

    ROUND(SUM(
        CASE
            WHEN f.federal_action_obligation < 0
                THEN f.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS negative_obligation,

    ROUND(
        SUM(f.federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m199b_focal AS f

JOIN m199b_crosslisted_awards AS c
  ON c.diagnostic_award_identifier =
     f.diagnostic_award_identifier

GROUP BY
    f.diagnostic_award_identifier

ORDER BY
    ABS(SUM(f.federal_action_obligation)) DESC;


/*
====================================================================================================
15. 93.596 CROSS-LISTED VS NON-CROSS-LISTED BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. 93.596 CROSS-LISTED VS NON-CROSS-LISTED BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH bridge AS
(
    SELECT
        CASE
            WHEN c.diagnostic_award_identifier IS NOT NULL
                THEN 'CROSS_LISTED_AWARD'
            ELSE 'NOT_CROSS_LISTED'
        END AS award_group,

        COUNT(*)
            AS transaction_count,

        COUNT(
            DISTINCT f.diagnostic_award_identifier
        ) AS award_count,

        SUM(f.federal_action_obligation)
            AS net_obligation

    FROM m199b_focal AS f

    LEFT JOIN m199b_crosslisted_awards AS c
      ON c.diagnostic_award_identifier =
         f.diagnostic_award_identifier

    GROUP BY 1
)

SELECT
    award_group,
    transaction_count,
    award_count,
    ROUND(net_obligation::numeric, 2)
        AS net_obligation

FROM bridge

UNION ALL

SELECT
    'TOTAL_RECONSTRUCTED',
    SUM(transaction_count),
    SUM(award_count),
    ROUND(
        SUM(net_obligation)::numeric,
        2
    )

FROM bridge

ORDER BY award_group;


/*
====================================================================================================
16. EXACT COLLISION SUMMARY

A concise control for the key duplicate-dollar test.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. EXACT NONZERO SAME-DATE / SAME-AMOUNT COLLISION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH collision AS
(
    SELECT DISTINCT
        a.diagnostic_award_identifier,
        a.action_date,
        a.diagnostic_program_code
            AS program_a,
        b.diagnostic_program_code
            AS program_b,
        a.federal_action_obligation

    FROM m199b_all AS a

    JOIN m199b_all AS b
      ON b.diagnostic_award_identifier =
         a.diagnostic_award_identifier

     AND b.action_date =
         a.action_date

     AND b.federal_action_obligation =
         a.federal_action_obligation

     AND b.diagnostic_program_code >
         a.diagnostic_program_code

    JOIN m199b_crosslisted_awards AS c
      ON c.diagnostic_award_identifier =
         a.diagnostic_award_identifier

    WHERE a.federal_action_obligation <> 0
)

SELECT
    COUNT(*) AS exact_collision_count,

    COUNT(
        DISTINCT diagnostic_award_identifier
    ) AS awards_with_exact_collision,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation),
            0
        )::numeric,
        2
    ) AS collision_obligation_sum

FROM collision;


/*
====================================================================================================
17. FINAL HARD-CONTROL ASSERTION

Expected values come directly from ETL-199A.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. FINAL HARD-CONTROL ASSERTION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_tx             bigint;
    v_awards         bigint;
    v_recipients     bigint;
    v_net            numeric;
    v_covid          numeric;
    v_iija           numeric;
    v_extraordinary  numeric;
    v_crosslisted    bigint;

BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT diagnostic_award_identifier),
        COUNT(DISTINCT recipient_id),

        ROUND(
            SUM(federal_action_obligation)::numeric,
            2
        ),

        ROUND(SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric, 2),

        ROUND(SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric, 2),

        ROUND(SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        )::numeric, 2)

    INTO
        v_tx,
        v_awards,
        v_recipients,
        v_net,
        v_covid,
        v_iija,
        v_extraordinary

    FROM m199b_focal;


    SELECT COUNT(*)
    INTO v_crosslisted
    FROM m199b_crosslisted_awards;


    IF v_tx <> 950 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected 950 focal transactions, found %',
            v_tx;
    END IF;


    IF v_awards <> 271 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected 271 focal awards, found %',
            v_awards;
    END IF;


    IF v_recipients <> 28 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected 28 focal recipients, found %',
            v_recipients;
    END IF;


    IF v_net <> 718504226.60 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected focal net $718,504,226.60, found %',
            v_net;
    END IF;


    IF v_covid <> 19429.00 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected COVID amount $19,429.00, found %',
            v_covid;
    END IF;


    IF v_iija <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected IIJA amount $0.00, found %',
            v_iija;
    END IF;


    IF v_extraordinary <> 19429.00 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected extraordinary amount $19,429.00, found %',
            v_extraordinary;
    END IF;


    IF v_crosslisted <> 7 THEN
        RAISE EXCEPTION
            'ETL-199B FAIL: expected 7 cross-listed focal awards, found %',
            v_crosslisted;
    END IF;


    RAISE NOTICE
        'ETL-199B PASS: focal control and seven-award cross-list population reproduced exactly.';

END
$$;


/*
====================================================================================================
18. FINAL CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '18. FINAL FOCAL CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT diagnostic_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT recipient_id
    ) AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN is_covid
                THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN is_iija
                THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN is_extraordinary
                THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m199b_focal;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-199B COMPLETE'
\echo ''
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;