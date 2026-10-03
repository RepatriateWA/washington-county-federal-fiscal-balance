/*
====================================================================================================
ETL-186A
POST-NIAID UNRESOLVED ASSISTANCE CANVAS
====================================================================================================

Purpose
-------
Reconstruct the certified Washington USAspending assistance accounting bridge
after Migration 186 and profile the remaining UNCLASSIFIED_REVIEW population.

This is a diagnostic canvas only.

It does NOT:
    - classify another program
    - change accounting policy
    - infer county incidence
    - perform external reconciliation
    - write persistent database data

Established resolution precedence
---------------------------------
    AWARD CLASSIFICATION
        >
    PROGRAM POLICY MAPPING
        >
    UNCLASSIFIED_REVIEW

Post-M186 hard controls
-----------------------
Full assistance universe:
    transactions       942,243
    programs             1,351
    gross/net bridge    $348,524,407,674.34

Expected UNCLASSIFIED_REVIEW:
    transactions       811,899
    programs             1,272
    amount              $52,054,638,715.09

Expected INCLUDE_ADDITIVE:
    transactions        55,929
    programs                19
    amount              $60,946,512,232.51

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-186A - POST-NIAID UNRESOLVED ASSISTANCE CANVAS'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. BUILD CERTIFIED ASSISTANCE UNIVERSE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. BUILD CERTIFIED WA ASSISTANCE UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186a_ledger;

CREATE TEMP TABLE m186a_ledger AS
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

    is_covid,
    is_iija,
    is_extraordinary

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM m186a_ledger;


/*
====================================================================================================
2. BUILD AWARD-LEVEL MATCHES
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. BUILD AWARD-LEVEL POLICY MATCHES'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186a_award_matches;

CREATE TEMP TABLE m186a_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM m186a_ledger l

JOIN reference.federal_inflow_award_classification a
  ON a.source_system =
        'USASPENDING_ASSISTANCE'

 AND a.source_program_code =
        l.cfda_number

 AND a.source_award_identifier =
        l.source_award_identifier

WHERE
    (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
            a.valid_from_fiscal_year
    )

AND
    (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
            a.valid_through_fiscal_year
    );


SELECT
    COUNT(*) AS award_match_rows

FROM m186a_award_matches;


/*
====================================================================================================
3. BUILD PROGRAM-LEVEL MATCHES
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. BUILD PROGRAM-LEVEL POLICY MATCHES'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186a_program_matches;

CREATE TEMP TABLE m186a_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM m186a_ledger l

JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system =
        'USASPENDING_ASSISTANCE'

 AND m.source_program_code =
        l.cfda_number

WHERE
    (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
            m.valid_from_fiscal_year
    )

AND
    (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
            m.valid_through_fiscal_year
    );


SELECT
    COUNT(*) AS program_match_rows

FROM m186a_program_matches;


/*
====================================================================================================
4. RESOLUTION UNIQUENESS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. RESOLUTION UNIQUENESS CHECK'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_duplicate_award_matches   bigint;
    v_duplicate_program_matches bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_duplicate_award_matches

    FROM
    (
        SELECT
            assistance_transaction_id

        FROM m186a_award_matches

        GROUP BY assistance_transaction_id

        HAVING COUNT(*) > 1
    ) x;


    SELECT COUNT(*)
    INTO v_duplicate_program_matches

    FROM
    (
        SELECT
            assistance_transaction_id

        FROM m186a_program_matches

        GROUP BY assistance_transaction_id

        HAVING COUNT(*) > 1
    ) x;


    IF v_duplicate_award_matches <> 0 THEN
        RAISE EXCEPTION
            'ETL-186A duplicate award resolution detected for % transactions',
            v_duplicate_award_matches;
    END IF;


    IF v_duplicate_program_matches <> 0 THEN
        RAISE EXCEPTION
            'ETL-186A duplicate program resolution detected for % transactions',
            v_duplicate_program_matches;
    END IF;


    RAISE NOTICE
        'ETL-186A RESOLUTION UNIQUENESS PASS';

END
$$;


/*
====================================================================================================
5. BUILD EFFECTIVE ACCOUNTING RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. BUILD EFFECTIVE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m186a_resolved;

CREATE TEMP TABLE m186a_resolved AS
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

FROM m186a_ledger l

LEFT JOIN m186a_award_matches a
  ON a.assistance_transaction_id =
        l.assistance_transaction_id

LEFT JOIN m186a_program_matches p
  ON p.assistance_transaction_id =
        l.assistance_transaction_id;


/*
====================================================================================================
6. POST-M186 ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. POST-M186 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM m186a_resolved

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


/*
====================================================================================================
7. HARD POST-M186 CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. HARD POST-M186 CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_total_transactions      bigint;
    v_total_programs          bigint;
    v_total_amount            numeric;

    v_unresolved_transactions bigint;
    v_unresolved_programs     bigint;
    v_unresolved_amount       numeric;

    v_additive_transactions   bigint;
    v_additive_programs       bigint;
    v_additive_amount         numeric;
BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT cfda_number
        ),

        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_total_transactions,
        v_total_programs,
        v_total_amount

    FROM m186a_resolved;


    IF v_total_transactions <> 942243 THEN
        RAISE EXCEPTION
            'ETL-186A total transaction control failed: expected 942243, found %',
            v_total_transactions;
    END IF;


    IF v_total_programs <> 1351 THEN
        RAISE EXCEPTION
            'ETL-186A total program control failed: expected 1351, found %',
            v_total_programs;
    END IF;


    IF ROUND(v_total_amount, 2) <> 348524407674.34 THEN
        RAISE EXCEPTION
            'ETL-186A total amount control failed: expected 348524407674.34, found %',
            ROUND(v_total_amount, 2);
    END IF;


    SELECT
        COUNT(*),

        COUNT(
            DISTINCT cfda_number
        ),

        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_unresolved_transactions,
        v_unresolved_programs,
        v_unresolved_amount

    FROM m186a_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW';


    IF v_unresolved_transactions <> 811899 THEN
        RAISE EXCEPTION
            'ETL-186A unresolved transaction control failed: expected 811899, found %',
            v_unresolved_transactions;
    END IF;


    IF v_unresolved_programs <> 1272 THEN
        RAISE EXCEPTION
            'ETL-186A unresolved program control failed: expected 1272, found %',
            v_unresolved_programs;
    END IF;


    IF ROUND(v_unresolved_amount, 2) <> 52054638715.09 THEN
        RAISE EXCEPTION
            'ETL-186A unresolved amount control failed: expected 52054638715.09, found %',
            ROUND(v_unresolved_amount, 2);
    END IF;


    SELECT
        COUNT(*),

        COUNT(
            DISTINCT cfda_number
        ),

        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_additive_transactions,
        v_additive_programs,
        v_additive_amount

    FROM m186a_resolved

    WHERE effective_accounting_disposition =
        'INCLUDE_ADDITIVE';


    IF v_additive_transactions <> 55929 THEN
        RAISE EXCEPTION
            'ETL-186A additive transaction control failed: expected 55929, found %',
            v_additive_transactions;
    END IF;


    IF v_additive_programs <> 19 THEN
        RAISE EXCEPTION
            'ETL-186A additive program control failed: expected 19, found %',
            v_additive_programs;
    END IF;


    IF ROUND(v_additive_amount, 2) <> 60946512232.51 THEN
        RAISE EXCEPTION
            'ETL-186A additive amount control failed: expected 60946512232.51, found %',
            ROUND(v_additive_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-186A HARD POST-M186 CONTROL PASS';

END
$$;


/*
====================================================================================================
8. TOP 50 REMAINING UNRESOLVED PROGRAMS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TOP 50 REMAINING UNRESOLVED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

WITH unresolved_total AS
(
    SELECT
        SUM(
            federal_action_obligation
        ) AS unresolved_amount

    FROM m186a_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW'
)

SELECT
    r.cfda_number,
    r.cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT r.source_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT r.recipient_name
    ) AS recipient_count,

    ROUND(
        SUM(r.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(
        SUM(
            CASE
                WHEN r.is_covid
                    THEN r.federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE
                WHEN r.is_iija
                    THEN r.federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE
                WHEN r.is_extraordinary
                    THEN r.federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount,

    ROUND(
        (
            100.0
            * SUM(r.federal_action_obligation)
            / NULLIF(u.unresolved_amount, 0)
        )::numeric,
        4
    ) AS pct_of_unresolved

FROM m186a_resolved r

CROSS JOIN unresolved_total u

WHERE r.effective_accounting_disposition =
    'UNCLASSIFIED_REVIEW'

GROUP BY
    r.cfda_number,
    r.cfda_title,
    u.unresolved_amount

ORDER BY
    SUM(r.federal_action_obligation) DESC

LIMIT 50;


/*
====================================================================================================
9. RESIDUAL CONCENTRATION

How much of the remaining unresolved dollar population is represented by
the largest programs?
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. REMAINING UNRESOLVED CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS
(
    SELECT
        cfda_number,

        SUM(
            federal_action_obligation
        ) AS net_obligation

    FROM m186a_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW'

    GROUP BY cfda_number
),

ranked AS
(
    SELECT
        cfda_number,
        net_obligation,

        ROW_NUMBER() OVER
        (
            ORDER BY net_obligation DESC
        ) AS program_rank

    FROM program_totals
),

total AS
(
    SELECT
        SUM(net_obligation)
            AS unresolved_amount

    FROM program_totals
)

SELECT
    cutoff AS top_n_programs,

    ROUND(
        SUM(
            CASE
                WHEN r.program_rank <= cutoff
                    THEN r.net_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS top_n_amount,

    ROUND(
        (
            100.0
            * SUM(
                CASE
                    WHEN r.program_rank <= cutoff
                        THEN r.net_obligation
                    ELSE 0
                END
            )
            / NULLIF(t.unresolved_amount, 0)
        )::numeric,
        4
    ) AS pct_of_unresolved

FROM ranked r

CROSS JOIN total t

CROSS JOIN
(
    VALUES
        (10),
        (25),
        (50),
        (100)
) AS cutoffs(cutoff)

GROUP BY
    cutoff,
    t.unresolved_amount

ORDER BY cutoff;


/*
====================================================================================================
10. PROGRAM SIZE BANDS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. REMAINING UNRESOLVED PROGRAM SIZE BANDS'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS
(
    SELECT
        cfda_number,

        SUM(
            federal_action_obligation
        ) AS net_obligation

    FROM m186a_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW'

    GROUP BY cfda_number
),

banded AS
(
    SELECT
        CASE
            WHEN net_obligation >= 1000000000
                THEN '01 >= $1B'

            WHEN net_obligation >= 500000000
                THEN '02 $500M - < $1B'

            WHEN net_obligation >= 100000000
                THEN '03 $100M - < $500M'

            WHEN net_obligation >= 50000000
                THEN '04 $50M - < $100M'

            WHEN net_obligation >= 10000000
                THEN '05 $10M - < $50M'

            WHEN net_obligation >= 1000000
                THEN '06 $1M - < $10M'

            WHEN net_obligation >= 0
                THEN '07 $0 - < $1M'

            ELSE '08 NEGATIVE NET'
        END AS size_band,

        net_obligation

    FROM program_totals
)

SELECT
    size_band,

    COUNT(*) AS program_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation

FROM banded

GROUP BY size_band

ORDER BY size_band;


/*
====================================================================================================
11. FISCAL-YEAR PROFILE OF REMAINING UNRESOLVED POPULATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. REMAINING UNRESOLVED BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

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

FROM m186a_resolved

WHERE effective_accounting_disposition =
    'UNCLASSIFIED_REVIEW'

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
12. TOP 10 REMAINING PROGRAMS - COMPACT NEXT-TARGET VIEW
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. TOP 10 REMAINING PROGRAMS - NEXT-TARGET VIEW'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    cfda_title,

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

FROM m186a_resolved

WHERE effective_accounting_disposition =
    'UNCLASSIFIED_REVIEW'

GROUP BY
    cfda_number,
    cfda_title

ORDER BY
    SUM(federal_action_obligation) DESC

LIMIT 10;


/*
====================================================================================================
13. COMPLETION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-186A COMPLETE'
\echo 'Diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No external-source reconciliation.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;