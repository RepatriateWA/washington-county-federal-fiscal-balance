/*
====================================================================================================
ETL-184A — PROFILE POST-HCV UNRESOLVED ASSISTANCE CANVAS
====================================================================================================

Purpose
-------
Reconstruct the effective USAspending assistance accounting disposition after Migration 184 and
rank the remaining UNCLASSIFIED_REVIEW population by Assistance Listing.

This script deliberately reuses the certified accounting-resolution machinery from Migration 184.

Methodological rules
--------------------
1. Source universe:
      analysis.v_certified_assistance_ledger
      Washington
      FFY2020-FFY2024

2. Award-level accounting classifications take precedence over program-policy mappings.

3. Program-policy mappings apply only where no award-level classification resolves the transaction.

4. Transactions resolved by neither mechanism remain UNCLASSIFIED_REVIEW.

5. federal_action_obligation is the transaction accounting amount.

6. COVID, IIJA, and extraordinary status are inherited from the certified assistance ledger.
   They are provenance dimensions, not separate additive flows.

7. Negative obligations are retained.

8. No accounting policy, program classification, program mapping, accounting-source decision,
   or county allocation is created by this script.

Expected post-M184 unresolved control
-------------------------------------
transactions       = 818,500
programs           = 1,274
net obligations    = $57,195,963,406.91

Methodology checkpoint
----------------------
ETL-184A
Post-HCV unresolved assistance canvas
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-184A - POST-HCV UNRESOLVED ASSISTANCE CANVAS'
\echo '===================================================================================================='
\echo 'DIAGNOSTIC PROFILE - NO PERSISTENT DATABASE WRITES'
\echo ''

BEGIN;


/*
====================================================================================================
1. MATERIALIZE CERTIFIED WA ASSISTANCE UNIVERSE
====================================================================================================

Copied from the certified Migration 184 ledger construction.

Do not reconstruct COVID / IIJA / extraordinary semantics here.  Those flags are already present
in analysis.v_certified_assistance_ledger.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m184a_ledger;

CREATE TEMP TABLE m184a_ledger AS
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


CREATE INDEX ON m184a_ledger (assistance_transaction_id);
CREATE INDEX ON m184a_ledger (cfda_number);
CREATE INDEX ON m184a_ledger (source_award_identifier);
CREATE INDEX ON m184a_ledger (action_date_fiscal_year);


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. CERTIFIED WA ASSISTANCE UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS gross_obligation_amount

FROM m184a_ledger;


/*
====================================================================================================
2. RESOLVE AWARD-LEVEL ACCOUNTING CLASSIFICATIONS
====================================================================================================

This reproduces Migration 184.

Award-level classification has precedence over program-level policy.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m184a_award_matches;

CREATE TEMP TABLE m184a_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM m184a_ledger l

JOIN reference.federal_inflow_award_classification a
  ON a.source_system =
     'USASPENDING_ASSISTANCE'
 AND a.source_program_code =
     l.cfda_number
 AND a.source_award_identifier =
     l.source_award_identifier
 AND (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
           a.valid_from_fiscal_year
 )
 AND (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
           a.valid_through_fiscal_year
 );


/*
====================================================================================================
3. RESOLVE PROGRAM-POLICY MAPPINGS
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m184a_program_matches;

CREATE TEMP TABLE m184a_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM m184a_ledger l

JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system =
     'USASPENDING_ASSISTANCE'
 AND m.source_program_code =
     l.cfda_number
 AND (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
           m.valid_from_fiscal_year
 )
 AND (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
           m.valid_through_fiscal_year
 );


/*
====================================================================================================
4. FAIL-CLOSED RESOLUTION UNIQUENESS
====================================================================================================
*/

DO $$
DECLARE
    v_award_duplicates   bigint;
    v_program_duplicates bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_award_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM m184a_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    SELECT COUNT(*)
    INTO v_program_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM m184a_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    IF v_award_duplicates <> 0
       OR v_program_duplicates <> 0
    THEN
        RAISE EXCEPTION
            'ETL-184A RESOLUTION UNIQUENESS FAILED: award_duplicates=% program_duplicates=%',
            v_award_duplicates,
            v_program_duplicates;
    END IF;

    RAISE NOTICE
        'ETL-184A RESOLUTION UNIQUENESS PASS';

END
$$;


/*
====================================================================================================
5. CONSTRUCT EFFECTIVE ACCOUNTING DISPOSITION
====================================================================================================

Precedence:
    AWARD
    PROGRAM
    UNCLASSIFIED_REVIEW
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m184a_resolved;

CREATE TEMP TABLE m184a_resolved AS
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

FROM m184a_ledger l

LEFT JOIN m184a_award_matches a
  ON a.assistance_transaction_id =
     l.assistance_transaction_id

LEFT JOIN m184a_program_matches p
  ON p.assistance_transaction_id =
     l.assistance_transaction_id;


/*
====================================================================================================
6. FULL POST-M184 ASSISTANCE BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FULL POST-M184 ASSISTANCE BRIDGE'
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

FROM m184a_resolved

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


/*
====================================================================================================
7. CERTIFY POST-M184 UNRESOLVED CONTROL
====================================================================================================
*/

DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_amount       numeric;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_transactions,
        v_programs,
        v_amount

    FROM m184a_resolved

    WHERE effective_accounting_disposition =
          'UNCLASSIFIED_REVIEW';


    IF v_transactions <> 818500 THEN
        RAISE EXCEPTION
            'ETL-184A FAIL: unresolved transaction control expected 818500, found %',
            v_transactions;
    END IF;


    IF v_programs <> 1274 THEN
        RAISE EXCEPTION
            'ETL-184A FAIL: unresolved program control expected 1274, found %',
            v_programs;
    END IF;


    IF ROUND(v_amount, 2) <> 57195963406.91 THEN
        RAISE EXCEPTION
            'ETL-184A FAIL: unresolved obligation control expected 57195963406.91, found %',
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-184A POST-M184 CONTROL PASS: tx=% programs=% unresolved=%',
        v_transactions,
        v_programs,
        ROUND(v_amount, 2);

END
$$;


/*
====================================================================================================
8. BUILD RANKED UNCLASSIFIED PROGRAM CANVAS
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m184a_ranked;

CREATE TEMP TABLE m184a_ranked AS

WITH program_summary AS (

    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,

        COUNT(*) AS transaction_count,

        COUNT(
            DISTINCT source_award_identifier
        ) AS award_count,

        COUNT(
            DISTINCT recipient_name
        ) AS recipient_count,

        SUM(
            federal_action_obligation
        )::numeric AS net_obligation,

        SUM(
            CASE
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric AS positive_obligation,

        SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric AS negative_obligation,

        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric AS covid_amount,

        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric AS iija_amount,

        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric AS extraordinary_amount,

        MIN(
            action_date_fiscal_year
        ) AS first_fiscal_year,

        MAX(
            action_date_fiscal_year
        ) AS last_fiscal_year

    FROM m184a_resolved

    WHERE effective_accounting_disposition =
          'UNCLASSIFIED_REVIEW'

    GROUP BY cfda_number
),

totals AS (

    SELECT
        SUM(net_obligation)::numeric
            AS unresolved_total

    FROM program_summary
),

ranked AS (

    SELECT
        p.*,

        100.0
        * p.net_obligation
        / NULLIF(t.unresolved_total, 0)
            AS percent_of_unresolved,

        SUM(
            p.net_obligation
        ) OVER (
            ORDER BY
                p.net_obligation DESC,
                p.cfda_number
            ROWS BETWEEN
                UNBOUNDED PRECEDING
                AND CURRENT ROW
        ) AS cumulative_obligation,

        100.0
        * SUM(
            p.net_obligation
        ) OVER (
            ORDER BY
                p.net_obligation DESC,
                p.cfda_number
            ROWS BETWEEN
                UNBOUNDED PRECEDING
                AND CURRENT ROW
        )
        / NULLIF(t.unresolved_total, 0)
            AS cumulative_percent

    FROM program_summary p
    CROSS JOIN totals t
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY
            net_obligation DESC,
            cfda_number
    ) AS obligation_rank,

    cfda_number,
    cfda_title,

    transaction_count,
    award_count,
    recipient_count,

    ROUND(
        net_obligation,
        2
    ) AS net_obligation,

    ROUND(
        positive_obligation,
        2
    ) AS positive_obligation,

    ROUND(
        negative_obligation,
        2
    ) AS negative_obligation,

    ROUND(
        covid_amount,
        2
    ) AS covid_amount,

    ROUND(
        iija_amount,
        2
    ) AS iija_amount,

    ROUND(
        extraordinary_amount,
        2
    ) AS extraordinary_amount,

    ROUND(
        percent_of_unresolved,
        4
    ) AS percent_of_unresolved,

    ROUND(
        cumulative_obligation,
        2
    ) AS cumulative_obligation,

    ROUND(
        cumulative_percent,
        4
    ) AS cumulative_percent,

    first_fiscal_year,
    last_fiscal_year

FROM ranked;


/*
====================================================================================================
9. TOP 100 REMAINING UNCLASSIFIED PROGRAMS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. TOP 100 UNCLASSIFIED_REVIEW ASSISTANCE LISTINGS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM m184a_ranked
ORDER BY obligation_rank
LIMIT 100;


/*
====================================================================================================
10. CONCENTRATION PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. UNRESOLVED CONCENTRATION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    SUM(
        CASE
            WHEN obligation_rank <= 10
            THEN net_obligation
            ELSE 0
        END
    )::numeric(20,2) AS top_10_amount,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN obligation_rank <= 10
                THEN net_obligation
                ELSE 0
            END
        )
        / NULLIF(
            SUM(net_obligation),
            0
        ),
        4
    ) AS top_10_percent,

    SUM(
        CASE
            WHEN obligation_rank <= 25
            THEN net_obligation
            ELSE 0
        END
    )::numeric(20,2) AS top_25_amount,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN obligation_rank <= 25
                THEN net_obligation
                ELSE 0
            END
        )
        / NULLIF(
            SUM(net_obligation),
            0
        ),
        4
    ) AS top_25_percent,

    SUM(
        CASE
            WHEN obligation_rank <= 50
            THEN net_obligation
            ELSE 0
        END
    )::numeric(20,2) AS top_50_amount,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN obligation_rank <= 50
                THEN net_obligation
                ELSE 0
            END
        )
        / NULLIF(
            SUM(net_obligation),
            0
        ),
        4
    ) AS top_50_percent,

    SUM(
        CASE
            WHEN obligation_rank <= 100
            THEN net_obligation
            ELSE 0
        END
    )::numeric(20,2) AS top_100_amount,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN obligation_rank <= 100
                THEN net_obligation
                ELSE 0
            END
        )
        / NULLIF(
            SUM(net_obligation),
            0
        ),
        4
    ) AS top_100_percent,

    SUM(
        net_obligation
    )::numeric(20,2) AS total_unresolved

FROM m184a_ranked;


/*
====================================================================================================
11. PROGRAM COUNTS BY NET OBLIGATION SIZE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. PROGRAM COUNTS BY NET OBLIGATION SIZE'
\echo '----------------------------------------------------------------------------------------------------'

WITH bands AS (

    SELECT
        CASE
            WHEN net_obligation >= 1000000000
                THEN 1
            WHEN net_obligation >= 500000000
                THEN 2
            WHEN net_obligation >= 100000000
                THEN 3
            WHEN net_obligation >= 50000000
                THEN 4
            WHEN net_obligation >= 10000000
                THEN 5
            WHEN net_obligation >= 1000000
                THEN 6
            WHEN net_obligation >= 0
                THEN 7
            ELSE 8
        END AS band_order,

        CASE
            WHEN net_obligation >= 1000000000
                THEN '>= $1B'
            WHEN net_obligation >= 500000000
                THEN '$500M - <$1B'
            WHEN net_obligation >= 100000000
                THEN '$100M - <$500M'
            WHEN net_obligation >= 50000000
                THEN '$50M - <$100M'
            WHEN net_obligation >= 10000000
                THEN '$10M - <$50M'
            WHEN net_obligation >= 1000000
                THEN '$1M - <$10M'
            WHEN net_obligation >= 0
                THEN '$0 - <$1M'
            ELSE '< $0 net'
        END AS obligation_band,

        net_obligation

    FROM m184a_ranked
)

SELECT
    obligation_band,
    COUNT(*) AS program_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation

FROM bands

GROUP BY
    band_order,
    obligation_band

ORDER BY band_order;


/*
====================================================================================================
12. UNCLASSIFIED POPULATION BY FISCAL YEAR
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. UNCLASSIFIED_REVIEW BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

    ROUND(
        SUM(
            federal_action_obligation
        )::numeric,
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

FROM m184a_resolved

WHERE effective_accounting_disposition =
      'UNCLASSIFIED_REVIEW'

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
13. NEGATIVE-NET PROGRAMS
====================================================================================================

Negative-net programs are shown separately because a descending net-obligation ranking places
them at the bottom even though they may reveal important deobligation or correction behavior.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. NEGATIVE-NET UNCLASSIFIED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM m184a_ranked

WHERE net_obligation < 0

ORDER BY
    net_obligation ASC,
    cfda_number;


/*
====================================================================================================
14. FINAL CANVAS CERTIFICATION
====================================================================================================
*/

DO $$
DECLARE
    v_ranked_programs bigint;
    v_ranked_total    numeric;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(
            SUM(net_obligation),
            0
        )

    INTO
        v_ranked_programs,
        v_ranked_total

    FROM m184a_ranked;


    IF v_ranked_programs <> 1274 THEN
        RAISE EXCEPTION
            'ETL-184A FAIL: ranked program count expected 1274, found %',
            v_ranked_programs;
    END IF;


    IF ROUND(v_ranked_total, 2) <> 57195963406.91 THEN
        RAISE EXCEPTION
            'ETL-184A FAIL: ranked unresolved total expected 57195963406.91, found %',
            ROUND(v_ranked_total, 2);
    END IF;


    RAISE NOTICE
        'ETL-184A FINAL CERTIFICATION PASS: programs=% unresolved=%',
        v_ranked_programs,
        ROUND(v_ranked_total, 2);

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-184A COMPLETE'
\echo '===================================================================================================='
\echo 'DIAGNOSTIC PROFILE ONLY'
\echo 'No persistent policy changes, accounting-source decisions, or county allocations.'
\echo ''

ROLLBACK;