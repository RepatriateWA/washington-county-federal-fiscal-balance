/*
====================================================================================================
ETL-185A
POST-FEMA UNRESOLVED ASSISTANCE CANVAS
====================================================================================================

Purpose
-------
Reconstruct the effective WCFFBP USAspending assistance accounting disposition
after Migration 185 and rank the remaining UNCLASSIFIED_REVIEW population.

Established precedence:

    AWARD CLASSIFICATION
        >
    PROGRAM POLICY MAPPING
        >
    UNCLASSIFIED_REVIEW

This script is diagnostic only.

It performs:
    - no persistent database writes
    - no accounting classification
    - no external-source reconciliation
    - no county-incidence inference

Certified post-M185 unresolved control:

    transactions       815,260
    programs             1,273
    net obligations     $54,439,794,160.88

Methodological objective
------------------------
Identify the next material unresolved assistance programs for application of
the WCFFBP overlap-risk triage rule:

    No identified overlap pathway
        -> basic semantic/accounting validation
        -> classify
        -> migrate
        -> move on

    Identified/plausible overlap pathway
        -> reconcile before inclusion

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-185A - POST-FEMA UNRESOLVED ASSISTANCE CANVAS'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. CERTIFIED ASSISTANCE LEDGER
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. BUILD CERTIFIED WA FY2020-FY2024 ASSISTANCE LEDGER'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185a_ledger;

CREATE TEMP TABLE m185a_ledger AS
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
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


CREATE INDEX ON m185a_ledger
    (assistance_transaction_id);

CREATE INDEX ON m185a_ledger
    (cfda_number);

CREATE INDEX ON m185a_ledger
    (source_award_identifier);

CREATE INDEX ON m185a_ledger
    (action_date_fiscal_year);


SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS gross_obligation

FROM m185a_ledger;


/*
====================================================================================================
2. AWARD-LEVEL RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. RESOLVE AWARD-LEVEL CLASSIFICATIONS'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185a_award_matches;

CREATE TEMP TABLE m185a_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM m185a_ledger l

JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = l.cfda_number
 AND a.source_award_identifier = l.source_award_identifier

WHERE
    (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= a.valid_from_fiscal_year
    )
AND
    (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= a.valid_through_fiscal_year
    );


SELECT
    COUNT(*) AS award_match_rows,
    COUNT(DISTINCT assistance_transaction_id)
        AS matched_transactions

FROM m185a_award_matches;


/*
====================================================================================================
3. PROGRAM-LEVEL RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. RESOLVE PROGRAM-LEVEL POLICY MAPPINGS'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185a_program_matches;

CREATE TEMP TABLE m185a_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM m185a_ledger l

JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = l.cfda_number

WHERE
    (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= m.valid_from_fiscal_year
    )
AND
    (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= m.valid_through_fiscal_year
    );


SELECT
    COUNT(*) AS program_match_rows,
    COUNT(DISTINCT assistance_transaction_id)
        AS matched_transactions

FROM m185a_program_matches;


/*
====================================================================================================
4. FAIL-CLOSED RESOLUTION UNIQUENESS
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
        SELECT assistance_transaction_id
        FROM m185a_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;


    SELECT COUNT(*)
    INTO v_duplicate_program_matches
    FROM
    (
        SELECT assistance_transaction_id
        FROM m185a_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;


    IF v_duplicate_award_matches <> 0 THEN
        RAISE EXCEPTION
            'ETL-185A duplicate award resolution detected for % transactions',
            v_duplicate_award_matches;
    END IF;


    IF v_duplicate_program_matches <> 0 THEN
        RAISE EXCEPTION
            'ETL-185A duplicate program resolution detected for % transactions',
            v_duplicate_program_matches;
    END IF;


    RAISE NOTICE
        'ETL-185A RESOLUTION UNIQUENESS PASS';

END
$$;


/*
====================================================================================================
5. EFFECTIVE ACCOUNTING RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. BUILD EFFECTIVE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185a_resolved;

CREATE TEMP TABLE m185a_resolved AS
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

FROM m185a_ledger l

LEFT JOIN m185a_award_matches a
  ON a.assistance_transaction_id =
     l.assistance_transaction_id

LEFT JOIN m185a_program_matches p
  ON p.assistance_transaction_id =
     l.assistance_transaction_id;


/*
====================================================================================================
6. CURRENT ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. CURRENT POST-M185 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM m185a_resolved

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


/*
====================================================================================================
7. HARD POST-M185 CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. HARD POST-M185 UNRESOLVED CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

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

    FROM m185a_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW';


    IF v_transactions <> 815260 THEN
        RAISE EXCEPTION
            'ETL-185A unresolved transaction control failed: expected 815260, found %',
            v_transactions;
    END IF;


    IF v_programs <> 1273 THEN
        RAISE EXCEPTION
            'ETL-185A unresolved program control failed: expected 1273, found %',
            v_programs;
    END IF;


    IF ROUND(v_amount, 2) <> 54439794160.88 THEN
        RAISE EXCEPTION
            'ETL-185A unresolved amount control failed: expected 54439794160.88, found %',
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-185A POST-M185 CONTROL PASS: transactions=% programs=% amount=%',
        v_transactions,
        v_programs,
        ROUND(v_amount, 2);

END
$$;


/*
====================================================================================================
8. BUILD UNRESOLVED PROGRAM CANVAS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. BUILD UNRESOLVED PROGRAM CANVAS'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m185a_unresolved_programs;

CREATE TEMP TABLE m185a_unresolved_programs AS
WITH program_rollup AS
(
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

        COUNT(
            DISTINCT funding_agency_name
        ) AS funding_agency_count,

        MIN(action_date_fiscal_year)
            AS first_fiscal_year,

        MAX(action_date_fiscal_year)
            AS last_fiscal_year,

        SUM(federal_action_obligation)
            AS net_obligation,

        SUM(
            CASE
                WHEN federal_action_obligation > 0
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS positive_obligation,

        SUM(
            CASE
                WHEN federal_action_obligation < 0
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS negative_obligation,

        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS covid_amount,

        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS iija_amount,

        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS extraordinary_amount

    FROM m185a_resolved

    WHERE effective_accounting_disposition =
        'UNCLASSIFIED_REVIEW'

    GROUP BY cfda_number
),

ranked AS
(
    SELECT
        *,

        SUM(net_obligation)
            OVER () AS unresolved_total,

        ROW_NUMBER() OVER
        (
            ORDER BY
                net_obligation DESC,
                cfda_number
        ) AS obligation_rank

    FROM program_rollup
)

SELECT
    obligation_rank,
    cfda_number,
    cfda_title,

    transaction_count,
    award_count,
    recipient_count,
    funding_agency_count,

    first_fiscal_year,
    last_fiscal_year,

    ROUND(
        net_obligation::numeric,
        2
    ) AS net_obligation,

    ROUND(
        positive_obligation::numeric,
        2
    ) AS positive_obligation,

    ROUND(
        negative_obligation::numeric,
        2
    ) AS negative_obligation,

    ROUND(
        covid_amount::numeric,
        2
    ) AS covid_amount,

    ROUND(
        iija_amount::numeric,
        2
    ) AS iija_amount,

    ROUND(
        extraordinary_amount::numeric,
        2
    ) AS extraordinary_amount,

    ROUND(
        (
            100.0
            * net_obligation
            / NULLIF(unresolved_total, 0)
        )::numeric,
        4
    ) AS pct_unresolved

FROM ranked;


/*
====================================================================================================
9. TOP 50 UNRESOLVED PROGRAMS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP 50 UNRESOLVED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

WITH top_programs AS
(
    SELECT
        *,

        SUM(net_obligation)
            OVER
            (
                ORDER BY obligation_rank
                ROWS BETWEEN UNBOUNDED PRECEDING
                AND CURRENT ROW
            ) AS cumulative_obligation

    FROM m185a_unresolved_programs
)

SELECT
    obligation_rank AS rank,
    cfda_number,
    cfda_title,

    transaction_count,
    award_count,
    recipient_count,

    net_obligation,

    covid_amount,
    iija_amount,
    extraordinary_amount,

    pct_unresolved,

    ROUND(
        (
            100.0
            * cumulative_obligation
            / 54439794160.88
        )::numeric,
        4
    ) AS cumulative_pct

FROM top_programs

WHERE obligation_rank <= 50

ORDER BY obligation_rank;


/*
====================================================================================================
10. CONCENTRATION PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. RESIDUAL CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(
        SUM(
            CASE
                WHEN obligation_rank <= 10
                THEN net_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS top10_amount,

    ROUND(
        (
            100.0
            * SUM(
                CASE
                    WHEN obligation_rank <= 10
                    THEN net_obligation
                    ELSE 0
                END
            )
            / 54439794160.88
        )::numeric,
        4
    ) AS top10_pct,

    ROUND(
        SUM(
            CASE
                WHEN obligation_rank <= 25
                THEN net_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS top25_amount,

    ROUND(
        (
            100.0
            * SUM(
                CASE
                    WHEN obligation_rank <= 25
                    THEN net_obligation
                    ELSE 0
                END
            )
            / 54439794160.88
        )::numeric,
        4
    ) AS top25_pct,

    ROUND(
        SUM(
            CASE
                WHEN obligation_rank <= 50
                THEN net_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS top50_amount,

    ROUND(
        (
            100.0
            * SUM(
                CASE
                    WHEN obligation_rank <= 50
                    THEN net_obligation
                    ELSE 0
                END
            )
            / 54439794160.88
        )::numeric,
        4
    ) AS top50_pct,

    ROUND(
        SUM(
            CASE
                WHEN obligation_rank <= 100
                THEN net_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS top100_amount,

    ROUND(
        (
            100.0
            * SUM(
                CASE
                    WHEN obligation_rank <= 100
                    THEN net_obligation
                    ELSE 0
                END
            )
            / 54439794160.88
        )::numeric,
        4
    ) AS top100_pct

FROM m185a_unresolved_programs;


/*
====================================================================================================
11. SIZE-BAND PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. UNRESOLVED PROGRAM SIZE BANDS'
\echo '----------------------------------------------------------------------------------------------------'

WITH bands AS
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

            ELSE '08 < $0'
        END AS size_band,

        net_obligation

    FROM m185a_unresolved_programs
)

SELECT
    size_band,
    COUNT(*) AS program_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation

FROM bands

GROUP BY size_band

ORDER BY size_band;


/*
====================================================================================================
12. FISCAL-YEAR PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. UNRESOLVED BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS program_count,

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

FROM m185a_resolved

WHERE effective_accounting_disposition =
    'UNCLASSIFIED_REVIEW'

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
13. NEXT-CANDIDATE SUMMARY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. NEXT 10 CANDIDATES FOR OVERLAP-RISK TRIAGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    obligation_rank AS rank,
    cfda_number,
    cfda_title,
    transaction_count,
    award_count,
    recipient_count,
    funding_agency_count,
    first_fiscal_year,
    last_fiscal_year,
    net_obligation,
    covid_amount,
    iija_amount,
    extraordinary_amount,
    pct_unresolved

FROM m185a_unresolved_programs

WHERE obligation_rank <= 10

ORDER BY obligation_rank;


/*
====================================================================================================
14. COMPLETION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-185A COMPLETE'
\echo '===================================================================================================='
\echo 'Diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No external-source reconciliation.'
\echo 'No county-incidence inference.'
\echo ''

ROLLBACK;