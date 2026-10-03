\echo ''
\echo '===================================================================================================='
\echo 'WCFFBP DRAFT 1A'
\echo 'PROVISIONAL STATEWIDE ASSISTANCE ACCOUNTING BRIDGE'
\echo 'WASHINGTON FY2020-FY2024'
\echo '===================================================================================================='
\echo ''

\set ON_ERROR_STOP on

BEGIN;


/*
====================================================================================================
PURPOSE

Construct a provisional statewide USAspending assistance accounting bridge
for WCFFBP Draft 1.

THIS IS NOT A PERSISTENT ACCOUNTING MIGRATION.

No reference-table writes.
No permanent classification decisions.
No county-incidence inference.

DECISION PRECEDENCE
-------------------

1. Award-level accounting classification, where present.
2. Program-level accounting mapping, where present.
3. Remaining unresolved transactions explicitly tagged:
       is_covid
       is_iija
       is_extraordinary
   are provisionally included for Draft 1.
4. All remaining transactions remain unresolved.

IMPORTANT
---------

COVID, IIJA, and extraordinary are provenance dimensions.

They are NOT separate additive accounting paths.

A transaction carrying multiple tags enters the accounting bridge exactly once.

Existing EXCLUDE_DUPLICATE / WITHHOLD_UNRESOLVED / REFERENCE_ONLY decisions
always take precedence over provisional tag inclusion.

This diagnostic therefore does NOT reopen previously resolved overlap policy.
====================================================================================================
*/


/*
====================================================================================================
1. CERTIFIED WA ASSISTANCE UNIVERSE
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.d1a_base;

CREATE TEMP TABLE d1a_base AS
SELECT
    ROW_NUMBER() OVER (
        ORDER BY
            action_date,
            cfda_number,
            COALESCE(award_id_fain, ''),
            COALESCE(award_id_uri, ''),
            recipient_id,
            federal_action_obligation
    ) AS draft_row_id,

    l.*,

    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ) AS diagnostic_award_identifier

FROM analysis.v_certified_assistance_ledger AS l

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;

ANALYZE d1a_base;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. CERTIFIED ASSISTANCE UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS assistance_listing_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

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

FROM d1a_base;


/*
====================================================================================================
2. RESOLVE PROGRAM-LEVEL MAPPING

There should be at most one applicable program mapping per source program
for this Draft-1 period.

If more than one exists, fail rather than multiply transaction rows.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.d1a_program_mapping;

CREATE TEMP TABLE d1a_program_mapping AS
SELECT
    source_program_code,

    MIN(resolved_accounting_disposition)
        AS resolved_accounting_disposition,

    COUNT(*)
        AS mapping_count

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND valid_from_fiscal_year <= 2024
  AND (
        valid_through_fiscal_year IS NULL
        OR valid_through_fiscal_year >= 2020
      )

GROUP BY source_program_code;


DO $$
DECLARE
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_bad
    FROM d1a_program_mapping
    WHERE mapping_count <> 1;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'DRAFT-1A FAIL: % program codes have multiple applicable program mappings.',
            v_bad;
    END IF;

    RAISE NOTICE
        'DRAFT-1A PASS: program mappings are one-to-one for the analysis period.';

END
$$;


/*
====================================================================================================
3. RESOLVE AWARD-LEVEL CLASSIFICATION

Award-level decisions take precedence over program-level decisions.

The diagnostic award identifier is the same normalization used in the
recent assistance diagnostics.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.d1a_award_mapping;

CREATE TEMP TABLE d1a_award_mapping AS
SELECT
    source_program_code,
    source_award_identifier,

    MIN(accounting_disposition)
        AS accounting_disposition,

    COUNT(*)
        AS classification_count

FROM reference.federal_inflow_award_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND valid_from_fiscal_year <= 2024
  AND (
        valid_through_fiscal_year IS NULL
        OR valid_through_fiscal_year >= 2020
      )

GROUP BY
    source_program_code,
    source_award_identifier;


DO $$
DECLARE
    v_conflict bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_conflict

    FROM d1a_award_mapping

    WHERE classification_count <> 1;

    IF v_conflict <> 0 THEN
        RAISE EXCEPTION
            'DRAFT-1A FAIL: % award/program keys have multiple applicable award classifications.',
            v_conflict;
    END IF;

    RAISE NOTICE
        'DRAFT-1A PASS: award classifications are one-to-one for the analysis period.';

END
$$;


/*
====================================================================================================
4. ASSIGN ONE AND ONLY ONE DRAFT-1 ACCOUNTING BUCKET

Precedence:
    AWARD
    PROGRAM
    PROVISIONAL TAG
    UNRESOLVED

The tag bucket itself is mutually exclusive:
    IIJA first
    COVID second
    EXTRAORDINARY third

This priority is only for presentation.

All three tags remain independently preserved in the row.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.d1a_bridge;

CREATE TEMP TABLE d1a_bridge AS
SELECT
    b.*,

    a.accounting_disposition
        AS award_disposition,

    p.resolved_accounting_disposition
        AS program_disposition,

    CASE

        /*
        --------------------------------------------------------------------------------------------
        Award-level decisions have highest precedence.
        --------------------------------------------------------------------------------------------
        */

        WHEN a.accounting_disposition = 'INCLUDE_ADDITIVE'
            THEN 'INCLUDE_ADDITIVE_EXISTING_AWARD'

        WHEN a.accounting_disposition = 'EXCLUDE_DUPLICATE'
            THEN 'EXCLUDE_DUPLICATE_EXISTING_AWARD'

        WHEN a.accounting_disposition = 'WITHHOLD_UNRESOLVED'
            THEN 'WITHHOLD_UNRESOLVED_EXISTING_AWARD'

        WHEN a.accounting_disposition = 'REFERENCE_ONLY'
            THEN 'REFERENCE_ONLY_EXISTING_AWARD'


        /*
        --------------------------------------------------------------------------------------------
        Program-level decisions next.
        --------------------------------------------------------------------------------------------
        */

        WHEN p.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
            THEN 'INCLUDE_ADDITIVE_EXISTING_PROGRAM'

        WHEN p.resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
            THEN 'EXCLUDE_DUPLICATE_EXISTING_PROGRAM'

        WHEN p.resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED'
            THEN 'WITHHOLD_UNRESOLVED_EXISTING_PROGRAM'

        WHEN p.resolved_accounting_disposition = 'REFERENCE_ONLY'
            THEN 'REFERENCE_ONLY_EXISTING_PROGRAM'


        /*
        --------------------------------------------------------------------------------------------
        Provisional Draft-1 treatment.

        These rows have NO existing award/program accounting decision.
        --------------------------------------------------------------------------------------------
        */

        WHEN b.is_iija
            THEN 'INCLUDE_PROVISIONAL_IIJA'

        WHEN b.is_covid
            THEN 'INCLUDE_PROVISIONAL_COVID'

        WHEN b.is_extraordinary
            THEN 'INCLUDE_PROVISIONAL_EXTRAORDINARY'


        /*
        --------------------------------------------------------------------------------------------
        Everything else remains unresolved.
        --------------------------------------------------------------------------------------------
        */

        ELSE 'UNRESOLVED_ORDINARY'

    END AS draft_accounting_bucket

FROM d1a_base AS b

LEFT JOIN d1a_award_mapping AS a
  ON a.source_program_code =
     b.cfda_number

 AND a.source_award_identifier =
     b.diagnostic_award_identifier

LEFT JOIN d1a_program_mapping AS p
  ON p.source_program_code =
     b.cfda_number;

ANALYZE d1a_bridge;


/*
====================================================================================================
5. ROW-CARDINALITY FIREWALL

No mapping operation may duplicate certified transaction rows.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. ROW-CARDINALITY FIREWALL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    (SELECT COUNT(*) FROM d1a_base)
        AS certified_rows,

    (SELECT COUNT(*) FROM d1a_bridge)
        AS bridge_rows;


DO $$
DECLARE
    v_base   bigint;
    v_bridge bigint;
BEGIN

    SELECT COUNT(*) INTO v_base
    FROM d1a_base;

    SELECT COUNT(*) INTO v_bridge
    FROM d1a_bridge;

    IF v_base <> v_bridge THEN
        RAISE EXCEPTION
            'DRAFT-1A FAIL: row cardinality changed from % to %.',
            v_base,
            v_bridge;
    END IF;

    RAISE NOTICE
        'DRAFT-1A PASS: every certified transaction appears exactly once in the bridge.';

END
$$;


/*
====================================================================================================
6. COMPLETE DRAFT ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. COMPLETE DRAFT-1 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    draft_accounting_bucket,

    COUNT(*)
        AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS assistance_listing_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS covid_tagged_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS iija_tagged_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS extraordinary_tagged_amount

FROM d1a_bridge

GROUP BY draft_accounting_bucket

ORDER BY
    CASE draft_accounting_bucket

        WHEN 'INCLUDE_ADDITIVE_EXISTING_AWARD'
            THEN 1

        WHEN 'INCLUDE_ADDITIVE_EXISTING_PROGRAM'
            THEN 2

        WHEN 'INCLUDE_PROVISIONAL_IIJA'
            THEN 3

        WHEN 'INCLUDE_PROVISIONAL_COVID'
            THEN 4

        WHEN 'INCLUDE_PROVISIONAL_EXTRAORDINARY'
            THEN 5

        WHEN 'EXCLUDE_DUPLICATE_EXISTING_AWARD'
            THEN 6

        WHEN 'EXCLUDE_DUPLICATE_EXISTING_PROGRAM'
            THEN 7

        WHEN 'WITHHOLD_UNRESOLVED_EXISTING_AWARD'
            THEN 8

        WHEN 'WITHHOLD_UNRESOLVED_EXISTING_PROGRAM'
            THEN 9

        WHEN 'REFERENCE_ONLY_EXISTING_AWARD'
            THEN 10

        WHEN 'REFERENCE_ONLY_EXISTING_PROGRAM'
            THEN 11

        WHEN 'UNRESOLVED_ORDINARY'
            THEN 12

        ELSE 99
    END;


/*
====================================================================================================
7. PROVISIONAL ADDITIVE TOTAL

Existing INCLUDE_ADDITIVE
+
provisional IIJA
+
provisional COVID
+
provisional extraordinary

Each transaction occurs exactly once.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. DRAFT-1 PROVISIONAL ADDITIVE ASSISTANCE TOTAL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*)
        AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS assistance_listing_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS draft_1_additive_assistance,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS covid_tagged_within_additive,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS iija_tagged_within_additive,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS extraordinary_tagged_within_additive

FROM d1a_bridge

WHERE draft_accounting_bucket IN
(
    'INCLUDE_ADDITIVE_EXISTING_AWARD',
    'INCLUDE_ADDITIVE_EXISTING_PROGRAM',
    'INCLUDE_PROVISIONAL_IIJA',
    'INCLUDE_PROVISIONAL_COVID',
    'INCLUDE_PROVISIONAL_EXTRAORDINARY'
);


/*
====================================================================================================
8. DRAFT-1 BALANCE CHECK

Every dollar in the certified universe must fall into exactly one bridge bucket.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. WHOLE-UNIVERSE BALANCE CHECK'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS reconstructed_universe,

    ROUND(
        (
            SELECT SUM(federal_action_obligation)
            FROM d1a_base
        )::numeric,
        2
    ) AS certified_universe,

    ROUND(
        (
            SUM(federal_action_obligation)
            -
            (
                SELECT SUM(federal_action_obligation)
                FROM d1a_base
            )
        )::numeric,
        2
    ) AS difference

FROM d1a_bridge;


DO $$
DECLARE
    v_base   numeric;
    v_bridge numeric;
BEGIN

    SELECT ROUND(SUM(federal_action_obligation)::numeric, 2)
    INTO v_base
    FROM d1a_base;

    SELECT ROUND(SUM(federal_action_obligation)::numeric, 2)
    INTO v_bridge
    FROM d1a_bridge;

    IF v_base <> v_bridge THEN
        RAISE EXCEPTION
            'DRAFT-1A FAIL: certified universe % does not equal reconstructed universe %.',
            v_base,
            v_bridge;
    END IF;

    RAISE NOTICE
        'DRAFT-1A PASS: whole certified assistance universe balances exactly.';

END
$$;


/*
====================================================================================================
9. PROVISIONAL TAGGED ADDITIONS BY FISCAL YEAR
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. PROVISIONAL TAGGED ADDITIONS BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year,

    draft_accounting_bucket,

    COUNT(*)
        AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM d1a_bridge

WHERE draft_accounting_bucket IN
(
    'INCLUDE_PROVISIONAL_IIJA',
    'INCLUDE_PROVISIONAL_COVID',
    'INCLUDE_PROVISIONAL_EXTRAORDINARY'
)

GROUP BY
    action_date_fiscal_year,
    draft_accounting_bucket

ORDER BY
    action_date_fiscal_year,
    draft_accounting_bucket;


/*
====================================================================================================
10. PROVISIONAL TAGGED ADDITIONS BY PROGRAM

This is the review table we need before accepting the Draft-1 provisional total.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. PROVISIONAL TAGGED ADDITIONS BY PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    MIN(cfda_title)
        AS cfda_title,

    draft_accounting_bucket,

    COUNT(*)
        AS transaction_count,

    COUNT(DISTINCT diagnostic_award_identifier)
        AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

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

FROM d1a_bridge

WHERE draft_accounting_bucket IN
(
    'INCLUDE_PROVISIONAL_IIJA',
    'INCLUDE_PROVISIONAL_COVID',
    'INCLUDE_PROVISIONAL_EXTRAORDINARY'
)

GROUP BY
    cfda_number,
    draft_accounting_bucket

ORDER BY
    ABS(SUM(federal_action_obligation)) DESC

LIMIT 100;


/*
====================================================================================================
11. UNRESOLVED ORDINARY ASSISTANCE BY FISCAL YEAR
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. UNRESOLVED ORDINARY ASSISTANCE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year,

    COUNT(*)
        AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS assistance_listing_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS unresolved_ordinary_amount

FROM d1a_bridge

WHERE draft_accounting_bucket =
      'UNRESOLVED_ORDINARY'

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
12. TOP 50 UNRESOLVED ORDINARY PROGRAMS

These are explicitly NOT included in Draft 1 unless separately resolved later.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. TOP 50 UNRESOLVED ORDINARY PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    MIN(cfda_title)
        AS cfda_title,

    COUNT(*)
        AS transaction_count,

    COUNT(DISTINCT diagnostic_award_identifier)
        AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS unresolved_amount

FROM d1a_bridge

WHERE draft_accounting_bucket =
      'UNRESOLVED_ORDINARY'

GROUP BY cfda_number

ORDER BY
    ABS(SUM(federal_action_obligation)) DESC

LIMIT 50;


/*
====================================================================================================
13. DRAFT-1 ADDITIVE ASSISTANCE BY FISCAL YEAR

This is the table needed for statewide fiscal-balance assembly.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. DRAFT-1 ADDITIVE ASSISTANCE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year
        AS fiscal_year,

    ROUND(SUM(
        CASE
            WHEN draft_accounting_bucket IN
            (
                'INCLUDE_ADDITIVE_EXISTING_AWARD',
                'INCLUDE_ADDITIVE_EXISTING_PROGRAM'
            )
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2)
        AS established_additive,

    ROUND(SUM(
        CASE
            WHEN draft_accounting_bucket IN
            (
                'INCLUDE_PROVISIONAL_IIJA',
                'INCLUDE_PROVISIONAL_COVID',
                'INCLUDE_PROVISIONAL_EXTRAORDINARY'
            )
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2)
        AS provisional_tagged_additive,

    ROUND(SUM(
        CASE
            WHEN draft_accounting_bucket IN
            (
                'INCLUDE_ADDITIVE_EXISTING_AWARD',
                'INCLUDE_ADDITIVE_EXISTING_PROGRAM',
                'INCLUDE_PROVISIONAL_IIJA',
                'INCLUDE_PROVISIONAL_COVID',
                'INCLUDE_PROVISIONAL_EXTRAORDINARY'
            )
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2)
        AS draft_1_additive_assistance,

    ROUND(SUM(
        CASE
            WHEN draft_accounting_bucket =
                 'UNRESOLVED_ORDINARY'
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2)
        AS unresolved_ordinary

FROM d1a_bridge

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/*
====================================================================================================
14. PROVISIONAL ASSUMPTION SUMMARY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. DRAFT-1 PROVISIONAL ASSUMPTION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*)
        AS provisional_transaction_count,

    COUNT(DISTINCT cfda_number)
        AS provisional_program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS provisional_additive_amount,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS covid_tagged,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS iija_tagged,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation
             ELSE 0 END
    )::numeric, 2) AS extraordinary_tagged

FROM d1a_bridge

WHERE draft_accounting_bucket IN
(
    'INCLUDE_PROVISIONAL_IIJA',
    'INCLUDE_PROVISIONAL_COVID',
    'INCLUDE_PROVISIONAL_EXTRAORDINARY'
);


/*
====================================================================================================
15. FINAL CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'WCFFBP DRAFT 1A COMPLETE'
\echo ''
\echo 'READ-ONLY ANALYTICAL DRAFT'
\echo ''
\echo 'No persistent database writes.'
\echo 'No permanent accounting classification.'
\echo 'No county-incidence inference.'
\echo ''
\echo 'Existing accounting decisions take precedence.'
\echo 'Previously unresolved COVID / IIJA / extraordinary transactions are provisional only.'
\echo 'Each certified transaction appears exactly once in the accounting bridge.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;