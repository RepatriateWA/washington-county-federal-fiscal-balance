/*
====================================================================================================
ETL-197A
REFRESH UNRESOLVED ASSISTANCE RESIDUAL

Purpose:
    Reconstruct the current Washington FY2020-FY2024 USAspending assistance
    residual after ETL-197.

    Rank unresolved Assistance Listings by net federal action obligation.

This is a diagnostic only.

No persistent database writes.
No accounting classification.
No county-incidence inference.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-197A'
\echo 'REFRESH UNRESOLVED ASSISTANCE RESIDUAL'
\echo 'WASHINGTON FY2020-FY2024'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. BUILD CERTIFIED WASHINGTON ASSISTANCE POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197a_assistance;

CREATE TEMP TABLE m197a_assistance AS

SELECT
    l.*,

    pm.resolved_accounting_disposition,

    sp.federal_inflow_source_policy_id,
    sp.inflow_family,
    sp.inflow_subfamily,
    sp.ledger_treatment,
    sp.preferred_source,
    sp.allocation_source

FROM analysis.v_certified_assistance_ledger l

LEFT JOIN reference.federal_inflow_program_policy_mapping pm
  ON pm.source_system = 'USASPENDING_ASSISTANCE'
 AND pm.source_program_code = l.cfda_number
 AND pm.valid_from_fiscal_year <= l.action_date_fiscal_year
 AND (
        pm.valid_through_fiscal_year IS NULL
        OR pm.valid_through_fiscal_year >= l.action_date_fiscal_year
     )

LEFT JOIN reference.federal_inflow_source_policy sp
  ON sp.federal_inflow_source_policy_id =
     pm.federal_inflow_source_policy_id

WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;


ANALYZE m197a_assistance;


/*
====================================================================================================
2. WHOLE-POPULATION CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. WHOLE-POPULATION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS assistance_listing_count,

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

FROM m197a_assistance;


/*
====================================================================================================
3. ACCOUNTING-DISPOSITION BRIDGE

This tells us how much of the certified assistance universe is currently
resolved additive, excluded duplicate, withheld, reference-only, or still
unmapped.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. ACCOUNTING-DISPOSITION BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        resolved_accounting_disposition,
        'UNMAPPED'
    ) AS accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS assistance_listing_count,

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

FROM m197a_assistance

GROUP BY
    COALESCE(
        resolved_accounting_disposition,
        'UNMAPPED'
    )

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
4. BUILD UNRESOLVED / UNMAPPED PROGRAM RESIDUAL

For sprint purposes, the focal residual is any transaction that has no
program-level accounting disposition.

Programs explicitly WITHHOLD_UNRESOLVED are shown separately below rather
than silently merged into the unmapped population.
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m197a_unmapped_programs;

CREATE TEMP TABLE m197a_unmapped_programs AS

SELECT
    cfda_number,

    MIN(cfda_title)
        AS cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    COUNT(DISTINCT recipient_id)
        AS recipient_count,

    SUM(federal_action_obligation)
        AS net_obligation,

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
    ) AS extraordinary_amount,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year

FROM m197a_assistance

WHERE resolved_accounting_disposition IS NULL

GROUP BY cfda_number;


ANALYZE m197a_unmapped_programs;


/*
====================================================================================================
5. UNMAPPED RESIDUAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. UNMAPPED RESIDUAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS assistance_listing_count,

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

FROM m197a_unmapped_programs;


/*
====================================================================================================
6. TOP 30 CURRENT UNMAPPED PROGRAMS

This is the principal sprint decision table.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TOP 30 CURRENT UNMAPPED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROW_NUMBER() OVER
    (
        ORDER BY net_obligation DESC
    ) AS residual_rank,

    cfda_number
        AS assistance_listing,

    cfda_title
        AS program_title,

    transaction_count,

    award_count,

    recipient_count,

    ROUND(
        net_obligation::numeric,
        2
    ) AS net_obligation,

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

    first_fiscal_year,

    last_fiscal_year

FROM m197a_unmapped_programs

ORDER BY net_obligation DESC

LIMIT 30;


/*
====================================================================================================
7. TOP 30 BY ABSOLUTE DOLLAR MAGNITUDE

Normally this will closely resemble Section 6, but this catches large negative
or reversal-heavy programs that a descending positive ranking could hide.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TOP 30 UNMAPPED PROGRAMS BY ABSOLUTE DOLLAR MAGNITUDE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROW_NUMBER() OVER
    (
        ORDER BY ABS(net_obligation) DESC
    ) AS magnitude_rank,

    cfda_number
        AS assistance_listing,

    cfda_title
        AS program_title,

    transaction_count,

    award_count,

    recipient_count,

    ROUND(
        net_obligation::numeric,
        2
    ) AS net_obligation,

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
    ) AS extraordinary_amount

FROM m197a_unmapped_programs

ORDER BY ABS(net_obligation) DESC

LIMIT 30;


/*
====================================================================================================
8. UNMAPPED RESIDUAL CONCENTRATION

How much of the remaining unmapped dollar population is represented by the
largest programs?
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. UNMAPPED RESIDUAL CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH ranked AS
(
    SELECT
        *,

        ROW_NUMBER() OVER
        (
            ORDER BY net_obligation DESC
        ) AS residual_rank

    FROM m197a_unmapped_programs
),

total AS
(
    SELECT
        SUM(net_obligation)
            AS total_unmapped

    FROM ranked
)

SELECT
    COUNT(*) FILTER
    (
        WHERE residual_rank <= 5
    ) AS top_5_programs,

    ROUND(SUM(
        CASE
            WHEN residual_rank <= 5
            THEN net_obligation
            ELSE 0
        END
    )::numeric, 2) AS top_5_amount,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN residual_rank <= 5
                THEN net_obligation
                ELSE 0
            END
        )
        / NULLIF(MAX(total_unmapped), 0),
        2
    ) AS top_5_percent,

    ROUND(SUM(
        CASE
            WHEN residual_rank <= 10
            THEN net_obligation
            ELSE 0
        END
    )::numeric, 2) AS top_10_amount,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN residual_rank <= 10
                THEN net_obligation
                ELSE 0
            END
        )
        / NULLIF(MAX(total_unmapped), 0),
        2
    ) AS top_10_percent,

    ROUND(SUM(
        CASE
            WHEN residual_rank <= 20
            THEN net_obligation
            ELSE 0
        END
    )::numeric, 2) AS top_20_amount,

    ROUND(
        100.0
        * SUM(
            CASE
                WHEN residual_rank <= 20
                THEN net_obligation
                ELSE 0
            END
        )
        / NULLIF(MAX(total_unmapped), 0),
        2
    ) AS top_20_percent,

    ROUND(
        MAX(total_unmapped)::numeric,
        2
    ) AS total_unmapped_amount

FROM ranked

CROSS JOIN total;


/*
====================================================================================================
9. UNMAPPED COVID / IIJA / EXTRAORDINARY CONCENTRATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. UNMAPPED PROVENANCE CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) FILTER
    (
        WHERE covid_amount <> 0
    ) AS programs_with_covid,

    ROUND(
        SUM(covid_amount)::numeric,
        2
    ) AS covid_amount,

    COUNT(*) FILTER
    (
        WHERE iija_amount <> 0
    ) AS programs_with_iija,

    ROUND(
        SUM(iija_amount)::numeric,
        2
    ) AS iija_amount,

    COUNT(*) FILTER
    (
        WHERE extraordinary_amount <> 0
    ) AS programs_with_extraordinary,

    ROUND(
        SUM(extraordinary_amount)::numeric,
        2
    ) AS extraordinary_amount

FROM m197a_unmapped_programs;


/*
====================================================================================================
10. TOP UNMAPPED IIJA PROGRAMS

This preserves visibility into the separate IIJA reporting dimension without
creating a second accounting path.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. TOP UNMAPPED IIJA PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number
        AS assistance_listing,

    cfda_title
        AS program_title,

    transaction_count,

    ROUND(
        net_obligation::numeric,
        2
    ) AS total_net_obligation,

    ROUND(
        iija_amount::numeric,
        2
    ) AS iija_amount,

    ROUND(
        extraordinary_amount::numeric,
        2
    ) AS extraordinary_amount

FROM m197a_unmapped_programs

WHERE iija_amount <> 0

ORDER BY ABS(iija_amount) DESC

LIMIT 30;


/*
====================================================================================================
11. TOP UNMAPPED COVID PROGRAMS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. TOP UNMAPPED COVID PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number
        AS assistance_listing,

    cfda_title
        AS program_title,

    transaction_count,

    ROUND(
        net_obligation::numeric,
        2
    ) AS total_net_obligation,

    ROUND(
        covid_amount::numeric,
        2
    ) AS covid_amount,

    ROUND(
        extraordinary_amount::numeric,
        2
    ) AS extraordinary_amount

FROM m197a_unmapped_programs

WHERE covid_amount <> 0

ORDER BY ABS(covid_amount) DESC

LIMIT 30;


/*
====================================================================================================
12. EXPLICITLY WITHHELD PROGRAMS

Keep programs already mapped to WITHHOLD_UNRESOLVED visible, but separate
from programs that simply have not yet been classified.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXPLICITLY WITHHELD PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number
        AS assistance_listing,

    MIN(cfda_title)
        AS program_title,

    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

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

FROM m197a_assistance

WHERE resolved_accounting_disposition =
      'WITHHOLD_UNRESOLVED'

GROUP BY cfda_number

ORDER BY ABS(SUM(federal_action_obligation)) DESC;


/*
====================================================================================================
13. FINAL RECONCILIATION

The disposition buckets must reconstruct the complete certified assistance
population exactly.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. FINAL RECONCILIATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH disposition_bridge AS
(
    SELECT
        COALESCE(
            resolved_accounting_disposition,
            'UNMAPPED'
        ) AS accounting_disposition,

        COUNT(*) AS transaction_count,

        SUM(federal_action_obligation)
            AS net_obligation

    FROM m197a_assistance

    GROUP BY
        COALESCE(
            resolved_accounting_disposition,
            'UNMAPPED'
        )
)

SELECT
    SUM(transaction_count)
        AS reconstructed_transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS reconstructed_net_obligation

FROM disposition_bridge;


SELECT
    COUNT(*) AS source_transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS source_net_obligation

FROM m197a_assistance;


/*
====================================================================================================
14. NO-WRITE CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-197A COMPLETE'
\echo ''
\echo 'Current unresolved assistance residual refreshed.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;