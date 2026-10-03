\echo ''
\echo '===================================================================================================='
\echo 'ETL-200A'
\echo 'REFRESH WA ASSISTANCE ACCOUNTING RESIDUAL'
\echo 'POST ETL-200'
\echo '===================================================================================================='
\echo ''

\set ON_ERROR_STOP on

BEGIN;


/*
====================================================================================================
PURPOSE

Refresh the statewide FY2020-FY2024 USAspending assistance accounting canvas
after ETL-200.

This diagnostic answers:

    1. What is the certified WA assistance universe?
    2. How much is currently mapped INCLUDE / EXCLUDE / WITHHOLD / REFERENCE?
    3. What remains unmapped?
    4. Which unmapped Assistance Listings are now the largest?

Important
---------
Program-level mappings are used here.

Award-level classifications are reported separately so programs such as
AL 57.001 Railroad Retirement Board benefits are not mistaken for genuinely
unresolved merely because their accounting treatment was implemented at the
award level.

No persistent writes.
====================================================================================================
*/


/*
====================================================================================================
1. BUILD CERTIFIED WA FY2020-FY2024 POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m200a_all;

CREATE TEMP TABLE m200a_all AS
SELECT
    l.*,

    COALESCE(
        NULLIF(l.award_id_fain, ''),
        NULLIF(l.award_id_uri, '')
    ) AS diagnostic_award_identifier

FROM analysis.v_certified_assistance_ledger AS l

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;

ANALYZE m200a_all;


/*
====================================================================================================
2. WHOLE CERTIFIED UNIVERSE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. WHOLE CERTIFIED WA ASSISTANCE UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS assistance_listing_count,

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

FROM m200a_all;


/*
====================================================================================================
3. PROGRAM-LEVEL ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. PROGRAM-LEVEL ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_mapping AS
(
    SELECT
        source_program_code,
        resolved_accounting_disposition

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND valid_from_fiscal_year <= 2024
      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          )
),

classified AS
(
    SELECT
        a.*,

        COALESCE(
            p.resolved_accounting_disposition,
            'UNMAPPED'
        ) AS accounting_disposition

    FROM m200a_all AS a

    LEFT JOIN program_mapping AS p
      ON p.source_program_code =
         a.cfda_number
)

SELECT
    accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT cfda_number
    ) AS assistance_listing_count,

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

FROM classified

GROUP BY accounting_disposition

ORDER BY
    ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
4. PROGRAM-MAPPED INCLUDE_ADDITIVE CONTROL

This is NOT yet the complete additive assistance ledger because award-level
classifications may resolve additional programs such as AL 57.001.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. PROGRAM-MAPPED INCLUDE_ADDITIVE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT a.cfda_number
    ) AS assistance_listing_count,

    ROUND(
        SUM(a.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN a.is_covid
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN a.is_iija
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN a.is_extraordinary
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m200a_all AS a

JOIN reference.federal_inflow_program_policy_mapping AS p
  ON p.source_system =
     'USASPENDING_ASSISTANCE'

 AND p.source_program_code =
     a.cfda_number

 AND p.resolved_accounting_disposition =
     'INCLUDE_ADDITIVE';


/*
====================================================================================================
5. AWARD-LEVEL CLASSIFICATION SUMMARY

Important for identifying apparent program-level residuals already resolved
through award-level accounting.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. AWARD-LEVEL CLASSIFICATION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,

    accounting_disposition,

    COUNT(*) AS classified_award_count,

    MIN(inflow_family)
        AS example_inflow_family,

    MIN(inflow_subfamily)
        AS example_inflow_subfamily,

    MIN(methodology_version)
        AS first_methodology_version,

    MAX(methodology_version)
        AS last_methodology_version

FROM reference.federal_inflow_award_classification

WHERE source_system =
      'USASPENDING_ASSISTANCE'

  AND valid_from_fiscal_year <= 2024

  AND (
        valid_through_fiscal_year IS NULL
        OR valid_through_fiscal_year >= 2020
      )

GROUP BY
    source_program_code,
    accounting_disposition

ORDER BY
    source_program_code,
    accounting_disposition;


/*
====================================================================================================
6. TOP 40 PROGRAM-LEVEL UNMAPPED ASSISTANCE LISTINGS

This is the principal sprint queue.

The award-level flag tells us when a nominal program residual has already
received award-level treatment.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TOP 40 PROGRAM-LEVEL UNMAPPED ASSISTANCE LISTINGS'
\echo '----------------------------------------------------------------------------------------------------'

WITH mapped_program AS
(
    SELECT DISTINCT
        source_program_code

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND valid_from_fiscal_year <= 2024

      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          )
),

award_classified_program AS
(
    SELECT
        source_program_code,

        COUNT(*) AS award_classification_count

    FROM reference.federal_inflow_award_classification

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND valid_from_fiscal_year <= 2024

      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          )

    GROUP BY source_program_code
),

residual AS
(
    SELECT
        a.cfda_number,

        MIN(a.cfda_title)
            AS cfda_title,

        COUNT(*)
            AS transaction_count,

        COUNT(
            DISTINCT a.diagnostic_award_identifier
        ) AS award_count,

        COUNT(
            DISTINCT a.recipient_id
        ) AS recipient_count,

        ROUND(
            SUM(a.federal_action_obligation)::numeric,
            2
        ) AS net_obligation,

        ROUND(SUM(
            CASE
                WHEN a.is_covid
                    THEN a.federal_action_obligation
                ELSE 0
            END
        )::numeric, 2) AS covid_amount,

        ROUND(SUM(
            CASE
                WHEN a.is_iija
                    THEN a.federal_action_obligation
                ELSE 0
            END
        )::numeric, 2) AS iija_amount,

        ROUND(SUM(
            CASE
                WHEN a.is_extraordinary
                    THEN a.federal_action_obligation
                ELSE 0
            END
        )::numeric, 2) AS extraordinary_amount

    FROM m200a_all AS a

    LEFT JOIN mapped_program AS m
      ON m.source_program_code =
         a.cfda_number

    WHERE m.source_program_code IS NULL

    GROUP BY a.cfda_number
)

SELECT
    r.cfda_number,

    r.cfda_title,

    r.transaction_count,
    r.award_count,
    r.recipient_count,

    r.net_obligation,
    r.covid_amount,
    r.iija_amount,
    r.extraordinary_amount,

    COALESCE(
        ac.award_classification_count,
        0
    ) AS award_classification_count,

    CASE
        WHEN COALESCE(
            ac.award_classification_count,
            0
        ) > 0
            THEN 'YES'
        ELSE 'NO'
    END AS has_award_level_classification

FROM residual AS r

LEFT JOIN award_classified_program AS ac
  ON ac.source_program_code =
     r.cfda_number

ORDER BY
    ABS(r.net_obligation) DESC

LIMIT 40;


/*
====================================================================================================
7. TOP 40 GENUINELY UNRESOLVED PROGRAMS

Exclude nominal residual programs that already have at least one award-level
classification. This gives us a cleaner sprint queue.

This does NOT assert that award-level classification necessarily resolves
every transaction in such a program. It simply removes those programs from
this quick ranking so they can be handled by their established architecture.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TOP 40 RESIDUAL PROGRAMS WITHOUT AWARD-LEVEL CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH mapped_program AS
(
    SELECT DISTINCT
        source_program_code

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND valid_from_fiscal_year <= 2024

      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          )
),

award_classified_program AS
(
    SELECT DISTINCT
        source_program_code

    FROM reference.federal_inflow_award_classification

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND valid_from_fiscal_year <= 2024

      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          )
)

SELECT
    a.cfda_number,

    MIN(a.cfda_title)
        AS cfda_title,

    COUNT(*)
        AS transaction_count,

    COUNT(
        DISTINCT a.diagnostic_award_identifier
    ) AS award_count,

    COUNT(
        DISTINCT a.recipient_id
    ) AS recipient_count,

    ROUND(
        SUM(a.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN a.is_covid
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN a.is_iija
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN a.is_extraordinary
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m200a_all AS a

LEFT JOIN mapped_program AS m
  ON m.source_program_code =
     a.cfda_number

LEFT JOIN award_classified_program AS ac
  ON ac.source_program_code =
     a.cfda_number

WHERE m.source_program_code IS NULL
  AND ac.source_program_code IS NULL

GROUP BY a.cfda_number

ORDER BY
    ABS(SUM(a.federal_action_obligation)) DESC

LIMIT 40;


/*
====================================================================================================
8. RESIDUAL TOTAL WITHOUT PROGRAM OR AWARD-LEVEL CLASSIFICATION

This is a sprint-oriented diagnostic, not the final whole-ledger accounting
bridge.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. RESIDUAL TOTAL WITHOUT PROGRAM OR AWARD-LEVEL CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH mapped_program AS
(
    SELECT DISTINCT
        source_program_code

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND valid_from_fiscal_year <= 2024

      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          )
),

award_classified_program AS
(
    SELECT DISTINCT
        source_program_code

    FROM reference.federal_inflow_award_classification

    WHERE source_system =
          'USASPENDING_ASSISTANCE'

      AND valid_from_fiscal_year <= 2024

      AND (
            valid_through_fiscal_year IS NULL
            OR valid_through_fiscal_year >= 2020
          )
)

SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT a.cfda_number
    ) AS assistance_listing_count,

    ROUND(
        SUM(a.federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE
            WHEN a.is_covid
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE
            WHEN a.is_iija
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE
            WHEN a.is_extraordinary
                THEN a.federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS extraordinary_amount

FROM m200a_all AS a

LEFT JOIN mapped_program AS m
  ON m.source_program_code =
     a.cfda_number

LEFT JOIN award_classified_program AS ac
  ON ac.source_program_code =
     a.cfda_number

WHERE m.source_program_code IS NULL
  AND ac.source_program_code IS NULL;


/*
====================================================================================================
9. TARGET CHECK: AL 10.561

Do not classify it here. Merely establish whether it remains in the residual
and reproduce its basic control.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TARGET CHECK - AL 10.561'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    MIN(cfda_title)
        AS cfda_title,

    COUNT(*)
        AS transaction_count,

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

FROM m200a_all

WHERE cfda_number = '10.561'

GROUP BY cfda_number;


/*
====================================================================================================
10. TARGET EXISTING POLICY CHECK: AL 10.561
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. EXISTING POLICY / CLASSIFICATION CHECK - AL 10.561'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '10.561'
ORDER BY federal_inflow_program_classification_id;


SELECT *
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '10.561'
ORDER BY federal_inflow_program_policy_mapping_id;


SELECT *
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '10.561'
ORDER BY federal_inflow_award_classification_id;


/*
====================================================================================================
11. FINAL CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-200A COMPLETE'
\echo ''
\echo 'Read-only residual refresh.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;