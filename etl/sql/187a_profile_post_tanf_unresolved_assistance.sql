/*
====================================================================================================
ETL-187A
POST-TANF UNRESOLVED ASSISTANCE REFRESH
====================================================================================================

Purpose:
    Refresh the WCFFBP unresolved USAspending assistance canvas after
    successful ETL-187 TANF policy migration.

Scope:
    Washington
    FFY2020-FFY2024
    Certified assistance ledger

This is a diagnostic only.

Objectives:
    1. Reconstruct effective accounting resolution using:
           award-level classification
               >
           program-level mapping
               >
           UNCLASSIFIED_REVIEW

    2. Hard-control the post-ETL-187 accounting bridge.

    3. Rank the top 25 remaining UNCLASSIFIED_REVIEW programs.

    4. Report concentration of the remaining unresolved population.

No persistent writes.
No accounting classification.
No county-incidence inference.

Expected post-ETL-187 bridge:

    EXCLUDE_DUPLICATE
        70,782 transactions
        44 programs
        $234,974,673,851.81

    INCLUDE_ADDITIVE
        56,214 transactions
        20 programs
        $63,148,717,534.63

    REFERENCE_ONLY
        2,443 transactions
        4 programs
        $7,799,088.00

    UNCLASSIFIED_REVIEW
        811,614 transactions
        1,271 programs
        $49,852,433,412.97

    WITHHOLD_UNRESOLVED
        1,190 transactions
        13 programs
        $540,783,786.93

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-187A - POST-TANF UNRESOLVED ASSISTANCE REFRESH'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. RECONSTRUCT EFFECTIVE RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. RECONSTRUCT EFFECTIVE ASSISTANCE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m187a_effective_resolution;

CREATE TEMP TABLE m187a_effective_resolution AS

WITH ledger AS
(
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

        is_covid,
        is_iija,
        is_extraordinary

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

award_resolution AS
(
    SELECT
        l.assistance_transaction_id,

        a.accounting_disposition
            AS resolved_accounting_disposition,

        ROW_NUMBER() OVER
        (
            PARTITION BY l.assistance_transaction_id

            ORDER BY
                a.federal_inflow_award_classification_id DESC
        ) AS rn

    FROM ledger l

    JOIN reference.federal_inflow_award_classification a
        ON a.source_system = 'USASPENDING_ASSISTANCE'
       AND a.source_award_identifier = l.source_award_identifier
       AND a.valid_from_fiscal_year <= 2024
       AND
       (
           a.valid_through_fiscal_year IS NULL
           OR a.valid_through_fiscal_year >= 2020
       )
),

program_resolution AS
(
    SELECT
        l.assistance_transaction_id,

        m.resolved_accounting_disposition,

        ROW_NUMBER() OVER
        (
            PARTITION BY l.assistance_transaction_id

            ORDER BY
                m.federal_inflow_program_policy_mapping_id DESC
        ) AS rn

    FROM ledger l

    JOIN reference.federal_inflow_program_policy_mapping m
        ON m.source_system = 'USASPENDING_ASSISTANCE'
       AND m.source_program_code = l.cfda_number
       AND m.valid_from_fiscal_year <= 2024
       AND
       (
           m.valid_through_fiscal_year IS NULL
           OR m.valid_through_fiscal_year >= 2020
       )
)

SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year,
    l.federal_action_obligation,

    l.cfda_number,
    l.cfda_title,

    l.is_covid,
    l.is_iija,
    l.is_extraordinary,

    CASE
        WHEN ar.assistance_transaction_id IS NOT NULL
            THEN 'AWARD'

        WHEN pr.assistance_transaction_id IS NOT NULL
            THEN 'PROGRAM'

        ELSE 'NONE'
    END AS resolution_level,

    COALESCE(
        ar.resolved_accounting_disposition,
        pr.resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS resolved_accounting_disposition

FROM ledger l

LEFT JOIN award_resolution ar
    ON ar.assistance_transaction_id
       = l.assistance_transaction_id
   AND ar.rn = 1

LEFT JOIN program_resolution pr
    ON pr.assistance_transaction_id
       = l.assistance_transaction_id
   AND pr.rn = 1;


/*
====================================================================================================
2. LEDGER UNIQUENESS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. LEDGER UNIQUENESS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS resolved_transaction_count,

    COUNT(
        DISTINCT assistance_transaction_id
    ) AS distinct_transaction_count

FROM m187a_effective_resolution;


DO $$
DECLARE
    v_rows     bigint;
    v_distinct bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(
            DISTINCT assistance_transaction_id
        )

    INTO
        v_rows,
        v_distinct

    FROM m187a_effective_resolution;


    IF v_rows <> 942243 THEN
        RAISE EXCEPTION
            'ETL-187A ledger control failed: expected 942243 rows, found %',
            v_rows;
    END IF;


    IF v_rows <> v_distinct THEN
        RAISE EXCEPTION
            'ETL-187A uniqueness failed: rows %, distinct transactions %',
            v_rows,
            v_distinct;
    END IF;


    RAISE NOTICE
        'ETL-187A LEDGER UNIQUENESS PASS';

END
$$;


/*
====================================================================================================
3. CURRENT ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. CURRENT POST-TANF ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m187a_effective_resolution

GROUP BY resolved_accounting_disposition

ORDER BY resolved_accounting_disposition;


/*
====================================================================================================
4. HARD POST-TANF BRIDGE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. HARD POST-TANF BRIDGE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_tx       bigint;
    v_programs bigint;
    v_amount   numeric;
BEGIN

    /*
    EXCLUDE_DUPLICATE
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m187a_effective_resolution

    WHERE resolved_accounting_disposition
          = 'EXCLUDE_DUPLICATE';


    IF v_tx <> 70782
       OR v_programs <> 44
       OR ROUND(v_amount, 2) <> 234974673851.81 THEN

        RAISE EXCEPTION
            'ETL-187A EXCLUDE_DUPLICATE bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    INCLUDE_ADDITIVE
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m187a_effective_resolution

    WHERE resolved_accounting_disposition
          = 'INCLUDE_ADDITIVE';


    IF v_tx <> 56214
       OR v_programs <> 20
       OR ROUND(v_amount, 2) <> 63148717534.63 THEN

        RAISE EXCEPTION
            'ETL-187A INCLUDE_ADDITIVE bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    REFERENCE_ONLY
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m187a_effective_resolution

    WHERE resolved_accounting_disposition
          = 'REFERENCE_ONLY';


    IF v_tx <> 2443
       OR v_programs <> 4
       OR ROUND(v_amount, 2) <> 7799088.00 THEN

        RAISE EXCEPTION
            'ETL-187A REFERENCE_ONLY bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    UNCLASSIFIED_REVIEW
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m187a_effective_resolution

    WHERE resolved_accounting_disposition
          = 'UNCLASSIFIED_REVIEW';


    IF v_tx <> 811614
       OR v_programs <> 1271
       OR ROUND(v_amount, 2) <> 49852433412.97 THEN

        RAISE EXCEPTION
            'ETL-187A UNCLASSIFIED bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    WITHHOLD_UNRESOLVED
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m187a_effective_resolution

    WHERE resolved_accounting_disposition
          = 'WITHHOLD_UNRESOLVED';


    IF v_tx <> 1190
       OR v_programs <> 13
       OR ROUND(v_amount, 2) <> 540783786.93 THEN

        RAISE EXCEPTION
            'ETL-187A WITHHOLD_UNRESOLVED bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-187A POST-TANF BRIDGE CONTROL PASS';

END
$$;


/*
====================================================================================================
5. BUILD UNRESOLVED PROGRAM SUMMARY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. BUILD UNRESOLVED PROGRAM SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m187a_unresolved_program;

CREATE TEMP TABLE m187a_unresolved_program AS

SELECT
    cfda_number,

    MAX(cfda_title)
        AS cfda_title,

    COUNT(*)
        AS transaction_count,

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

FROM m187a_effective_resolution

WHERE resolved_accounting_disposition
      = 'UNCLASSIFIED_REVIEW'

GROUP BY cfda_number;


/*
====================================================================================================
6. TOP 25 REMAINING UNRESOLVED PROGRAMS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TOP 25 REMAINING UNRESOLVED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROW_NUMBER() OVER
    (
        ORDER BY net_obligation DESC
    ) AS unresolved_rank,

    cfda_number,
    cfda_title,

    transaction_count,
    net_obligation,
    covid_amount,
    iija_amount,
    extraordinary_amount,

    ROUND(
        (
            100.0
            * net_obligation
            / 49852433412.97
        )::numeric,
        4
    ) AS pct_of_unresolved

FROM m187a_unresolved_program

ORDER BY net_obligation DESC

LIMIT 25;


/*
====================================================================================================
7. REMAINING UNRESOLVED CONCENTRATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. REMAINING UNRESOLVED CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH ranked AS
(
    SELECT
        net_obligation,

        ROW_NUMBER() OVER
        (
            ORDER BY net_obligation DESC
        ) AS rn

    FROM m187a_unresolved_program
),

cuts AS
(
    SELECT
        10 AS top_n

    UNION ALL

    SELECT
        25

    UNION ALL

    SELECT
        50

    UNION ALL

    SELECT
        100
)

SELECT
    c.top_n,

    ROUND(
        SUM(
            CASE
                WHEN r.rn <= c.top_n
                    THEN r.net_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS top_n_net_obligation,

    ROUND(
        (
            100.0
            * SUM(
                CASE
                    WHEN r.rn <= c.top_n
                        THEN r.net_obligation
                    ELSE 0
                END
            )
            / 49852433412.97
        )::numeric,
        4
    ) AS pct_of_unresolved

FROM cuts c

CROSS JOIN ranked r

GROUP BY c.top_n

ORDER BY c.top_n;


/*
====================================================================================================
8. COMPLETION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-187A COMPLETE'
\echo 'Post-TANF unresolved assistance refresh.'
\echo 'Diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;