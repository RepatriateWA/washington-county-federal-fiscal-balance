/*
================================================================================
ETL-174B-5P
Residual Assistance Materiality Profile
================================================================================

Purpose
-------
Profile the remaining Washington FY2020-FY2024 USAspending assistance
UNCLASSIFIED_REVIEW population after ETL-179 and ETL-174B-5O.

This is a READ-ONLY analytical script.

Resolution hierarchy
--------------------
1. Award-specific accounting classification
2. Explicit program -> source-policy mapping
3. UNCLASSIFIED_REVIEW

5O frozen residual control
--------------------------
Transactions              863,190
Programs                     1,289
Amount             107,284,286,183.21
COVID               46,546,748,315.92
IIJA                 8,129,817,959.24
Extraordinary       56,231,095,128.49

Objectives
----------
1. Reproduce the exact 5O residual.
2. Rank remaining programs by absolute dollar materiality.
3. Calculate cumulative share of unresolved dollars.
4. Measure how many programs account for 50%, 75%, 80%, 90%, 95%, and 99%.
5. Group programs into broad analytical families for triage only.
6. Preserve COVID, IIJA, and extraordinary dimensions independently.
7. Identify the most efficient next reconciliation targets.

IMPORTANT
---------
Analytical family assignment in this script is TRIAGE ONLY.

It is NOT:
* an accounting disposition,
* evidence of overlap,
* evidence of additivity,
* a source-policy mapping,
* or authorization for database persistence.

No DB writes are authorized.
================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5P RESIDUAL ASSISTANCE MATERIALITY PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. BUILD FY2020-FY2024 WASHINGTON ASSISTANCE BASE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5p_base;

CREATE TEMP TABLE etl174b_5p_base AS
SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year,
    l.cfda_number,
    l.cfda_title,
    l.award_id_fain,
    l.recipient_name,
    l.funding_agency_name,
    l.federal_action_obligation,
    l.defc_codes,
    l.funding_families,
    l.is_covid,
    l.is_iija,
    l.is_extraordinary
FROM analysis.v_certified_assistance_ledger l
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;


-- ================================================================================================
-- 2. AWARD-SPECIFIC RESOLUTION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5p_award_resolution;

CREATE TEMP TABLE etl174b_5p_award_resolution AS
SELECT
    b.*,
    ac.accounting_disposition AS award_disposition,
    ac.methodology_version AS award_methodology_version
FROM etl174b_5p_base b
LEFT JOIN LATERAL (
    SELECT
        a.accounting_disposition,
        a.methodology_version
    FROM reference.federal_inflow_award_classification a
    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = b.cfda_number
      AND a.source_award_identifier = b.award_id_fain
      AND (
            a.valid_from_fiscal_year IS NULL
            OR b.action_date_fiscal_year >= a.valid_from_fiscal_year
          )
      AND (
            a.valid_through_fiscal_year IS NULL
            OR b.action_date_fiscal_year <= a.valid_through_fiscal_year
          )
    ORDER BY
        a.updated_at DESC NULLS LAST,
        a.created_at DESC NULLS LAST,
        a.federal_inflow_award_classification_id DESC
    LIMIT 1
) ac ON TRUE;


-- ================================================================================================
-- 3. EXPLICIT PROGRAM-POLICY RESOLUTION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5p_program_resolution;

CREATE TEMP TABLE etl174b_5p_program_resolution AS
SELECT
    a.*,
    pm.resolved_accounting_disposition AS program_disposition,
    pm.methodology_version AS program_methodology_version,
    pm.federal_inflow_source_policy_id
FROM etl174b_5p_award_resolution a
LEFT JOIN LATERAL (
    SELECT
        m.resolved_accounting_disposition,
        m.methodology_version,
        m.federal_inflow_source_policy_id
    FROM reference.federal_inflow_program_policy_mapping m
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = a.cfda_number
      AND (
            m.valid_from_fiscal_year IS NULL
            OR a.action_date_fiscal_year >= m.valid_from_fiscal_year
          )
      AND (
            m.valid_through_fiscal_year IS NULL
            OR a.action_date_fiscal_year <= m.valid_through_fiscal_year
          )
    ORDER BY
        m.updated_at DESC NULLS LAST,
        m.created_at DESC NULLS LAST,
        m.federal_inflow_program_policy_mapping_id DESC
    LIMIT 1
) pm ON TRUE;


-- ================================================================================================
-- 4. FINAL RESOLUTION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5p_resolved;

CREATE TEMP TABLE etl174b_5p_resolved AS
SELECT
    p.*,

    CASE
        WHEN p.award_disposition IS NOT NULL
            THEN 'AWARD'
        WHEN p.program_disposition IS NOT NULL
            THEN 'PROGRAM'
        ELSE 'UNCLASSIFIED'
    END AS resolution_level,

    COALESCE(
        p.award_disposition,
        p.program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS resolved_accounting_disposition

FROM etl174b_5p_program_resolution p;


-- ================================================================================================
-- 5. EXTRACT 5O RESIDUAL
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5p_residual;

CREATE TEMP TABLE etl174b_5p_residual AS
SELECT *
FROM etl174b_5p_resolved
WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW';


-- ================================================================================================
-- 6. HARD 5O RESIDUAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. ETL-174B-5O RESIDUAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS unresolved_amount,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount
FROM etl174b_5p_residual;


DO $$
DECLARE
    v_transactions bigint;
    v_programs bigint;
    v_total numeric;
    v_covid numeric;
    v_iija numeric;
    v_extraordinary numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(
                CASE WHEN is_covid
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        ),
        COALESCE(
            SUM(
                CASE WHEN is_iija
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        ),
        COALESCE(
            SUM(
                CASE WHEN is_extraordinary
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            0
        )
    INTO
        v_transactions,
        v_programs,
        v_total,
        v_covid,
        v_iija,
        v_extraordinary
    FROM etl174b_5p_residual;

    IF v_transactions <> 863190 THEN
        RAISE EXCEPTION
            '5P CONTROL FAILED: expected 863190 transactions, found %',
            v_transactions;
    END IF;

    IF v_programs <> 1289 THEN
        RAISE EXCEPTION
            '5P CONTROL FAILED: expected 1289 programs, found %',
            v_programs;
    END IF;

    IF ABS(v_total - 107284286183.21::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5P CONTROL FAILED: expected residual %, found %',
            107284286183.21,
            v_total;
    END IF;

    IF ABS(v_covid - 46546748315.92::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5P COVID CONTROL FAILED: expected %, found %',
            46546748315.92,
            v_covid;
    END IF;

    IF ABS(v_iija - 8129817959.24::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5P IIJA CONTROL FAILED: expected %, found %',
            8129817959.24,
            v_iija;
    END IF;

    IF ABS(v_extraordinary - 56231095128.49::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5P EXTRAORDINARY CONTROL FAILED: expected %, found %',
            56231095128.49,
            v_extraordinary;
    END IF;

    RAISE NOTICE
        '5P 5O-BASELINE CONTROL PASS: transactions=% programs=% residual=% COVID=% IIJA=% extraordinary=%',
        v_transactions,
        v_programs,
        v_total,
        v_covid,
        v_iija,
        v_extraordinary;
END
$$;


-- ================================================================================================
-- 7. PROGRAM MATERIALITY TABLE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5p_programs;

CREATE TEMP TABLE etl174b_5p_programs AS
WITH program_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        MAX(funding_agency_name) AS funding_agency_name,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT award_id_fain) AS award_count,
        SUM(federal_action_obligation) AS obligation_amount,

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
        ) AS extraordinary_amount

    FROM etl174b_5p_residual
    GROUP BY cfda_number
),
ranked AS (
    SELECT
        p.*,

        ROW_NUMBER() OVER (
            ORDER BY obligation_amount DESC NULLS LAST, cfda_number
        ) AS materiality_rank,

        SUM(obligation_amount) OVER (
            ORDER BY obligation_amount DESC NULLS LAST, cfda_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_amount,

        SUM(obligation_amount) OVER () AS residual_control

    FROM program_totals p
)
SELECT
    *,
    100.0 * obligation_amount
        / NULLIF(residual_control, 0) AS pct_of_residual,

    100.0 * cumulative_amount
        / NULLIF(residual_control, 0) AS cumulative_pct_of_residual

FROM ranked;


-- ================================================================================================
-- 8. TOP 100 PROGRAMS WITH CUMULATIVE MATERIALITY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. TOP 100 UNRESOLVED PROGRAMS - CUMULATIVE MATERIALITY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    materiality_rank,
    cfda_number,
    cfda_title,
    funding_agency_name,
    transaction_count,
    award_count,
    ROUND(obligation_amount, 2) AS obligation_amount,
    ROUND(pct_of_residual, 4) AS pct_of_residual,
    ROUND(cumulative_amount, 2) AS cumulative_amount,
    ROUND(cumulative_pct_of_residual, 4) AS cumulative_pct,
    ROUND(covid_amount, 2) AS covid_amount,
    ROUND(iija_amount, 2) AS iija_amount,
    ROUND(extraordinary_amount, 2) AS extraordinary_amount
FROM etl174b_5p_programs
ORDER BY materiality_rank
LIMIT 100;


-- ================================================================================================
-- 9. CONCENTRATION THRESHOLDS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. PROGRAM COUNTS REQUIRED TO REACH MATERIALITY THRESHOLDS'
\echo '----------------------------------------------------------------------------------------------------'

WITH thresholds AS (
    SELECT *
    FROM (
        VALUES
            (50.0::numeric),
            (75.0::numeric),
            (80.0::numeric),
            (90.0::numeric),
            (95.0::numeric),
            (99.0::numeric)
    ) t(threshold_pct)
)
SELECT
    t.threshold_pct,
    MIN(p.materiality_rank) AS programs_required,
    ROUND(
        MIN(p.cumulative_amount)
            FILTER (
                WHERE p.cumulative_pct_of_residual >= t.threshold_pct
            ),
        2
    ) AS cumulative_amount_at_threshold
FROM thresholds t
LEFT JOIN etl174b_5p_programs p
  ON p.cumulative_pct_of_residual >= t.threshold_pct
GROUP BY t.threshold_pct
ORDER BY t.threshold_pct;


-- ================================================================================================
-- 10. FIXED TOP-N CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FIXED TOP-N PROGRAM CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH cutoffs AS (
    SELECT *
    FROM (
        VALUES
            (1),
            (5),
            (10),
            (20),
            (25),
            (50),
            (100),
            (250),
            (500),
            (1289)
    ) c(top_n)
)
SELECT
    c.top_n,
    COUNT(p.cfda_number) AS programs_present,
    ROUND(COALESCE(SUM(p.obligation_amount), 0), 2) AS obligation_amount,
    ROUND(
        100.0
        * COALESCE(SUM(p.obligation_amount), 0)
        / 107284286183.21::numeric,
        4
    ) AS pct_of_residual
FROM cutoffs c
LEFT JOIN etl174b_5p_programs p
  ON p.materiality_rank <= c.top_n
GROUP BY c.top_n
ORDER BY c.top_n;


-- ================================================================================================
-- 11. BROAD ANALYTICAL FAMILY ASSIGNMENT
--
-- IMPORTANT:
-- This is a triage taxonomy only.
-- It does not imply accounting disposition.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5p_family;

CREATE TEMP TABLE etl174b_5p_family AS
SELECT
    p.*,

    CASE
        -- --------------------------------------------------------------------
        -- Treasury / fiscal stabilization
        -- --------------------------------------------------------------------
        WHEN cfda_number IN (
            '21.019',
            '21.023',
            '21.027'
        )
        THEN 'STATE_LOCAL_FISCAL_STABILIZATION'

        -- --------------------------------------------------------------------
        -- Nutrition / food assistance
        -- --------------------------------------------------------------------
        WHEN cfda_number IN (
            '10.551',
            '10.555',
            '10.557',
            '10.561'
        )
        OR UPPER(COALESCE(cfda_title, '')) LIKE '%NUTRITION%'
        OR UPPER(COALESCE(cfda_title, '')) LIKE '%FOOD ASSISTANCE%'
        OR UPPER(COALESCE(cfda_title, '')) LIKE '%SCHOOL LUNCH%'
        THEN 'NUTRITION_FOOD_ASSISTANCE'

        -- --------------------------------------------------------------------
        -- Transportation infrastructure
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '20.%'
        THEN 'TRANSPORTATION_INFRASTRUCTURE'

        -- --------------------------------------------------------------------
        -- Education
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '84.%'
        THEN 'EDUCATION'

        -- --------------------------------------------------------------------
        -- Housing
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '14.%'
        THEN 'HOUSING_COMMUNITY_DEVELOPMENT'

        -- --------------------------------------------------------------------
        -- Disaster / emergency
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '97.%'
        THEN 'DISASTER_EMERGENCY'

        -- --------------------------------------------------------------------
        -- HHS health research
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '93.%'
         AND (
              UPPER(COALESCE(cfda_title, '')) LIKE '%RESEARCH%'
              OR UPPER(COALESCE(cfda_title, '')) LIKE '%DISEASE%'
              OR UPPER(COALESCE(cfda_title, '')) LIKE '%EPIDEMIOLOGY%'
             )
        THEN 'HEALTH_RESEARCH_PUBLIC_HEALTH'

        -- --------------------------------------------------------------------
        -- HHS human services
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '93.%'
        THEN 'HHS_HUMAN_SERVICES_OTHER'

        -- --------------------------------------------------------------------
        -- Unemployment / labor income support
        -- --------------------------------------------------------------------
        WHEN cfda_number = '17.225'
        THEN 'UNEMPLOYMENT_INSURANCE'

        WHEN cfda_number LIKE '17.%'
        THEN 'LABOR_WORKFORCE_OTHER'

        -- --------------------------------------------------------------------
        -- Railroad social insurance
        -- --------------------------------------------------------------------
        WHEN cfda_number = '57.001'
        THEN 'RAILROAD_SOCIAL_INSURANCE'

        -- --------------------------------------------------------------------
        -- PBGC
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '86.%'
        THEN 'PENSION_INSURANCE'

        -- --------------------------------------------------------------------
        -- SBA
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '59.%'
        THEN 'SMALL_BUSINESS_ASSISTANCE'

        -- --------------------------------------------------------------------
        -- Commerce / broadband
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '11.%'
        THEN 'COMMERCE_BROADBAND_ECONOMIC_DEVELOPMENT'

        -- --------------------------------------------------------------------
        -- Interior / tribal / natural resources
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '15.%'
        THEN 'INTERIOR_TRIBAL_NATURAL_RESOURCES'

        -- --------------------------------------------------------------------
        -- Energy
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '81.%'
        THEN 'ENERGY'

        -- --------------------------------------------------------------------
        -- FCC
        -- --------------------------------------------------------------------
        WHEN cfda_number LIKE '32.%'
        THEN 'COMMUNICATIONS'

        -- --------------------------------------------------------------------
        -- Everything else
        -- --------------------------------------------------------------------
        ELSE 'OTHER_REVIEW'

    END AS analytical_family

FROM etl174b_5p_programs p;


-- ================================================================================================
-- 12. ANALYTICAL FAMILY MATERIALITY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. ANALYTICAL FAMILY MATERIALITY - TRIAGE ONLY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    analytical_family,
    COUNT(*) AS program_count,
    SUM(transaction_count) AS transaction_count,
    ROUND(SUM(obligation_amount), 2) AS obligation_amount,
    ROUND(
        100.0 * SUM(obligation_amount)
        / 107284286183.21::numeric,
        4
    ) AS pct_of_residual,
    ROUND(SUM(covid_amount), 2) AS covid_amount,
    ROUND(SUM(iija_amount), 2) AS iija_amount,
    ROUND(SUM(extraordinary_amount), 2) AS extraordinary_amount
FROM etl174b_5p_family
GROUP BY analytical_family
ORDER BY SUM(obligation_amount) DESC NULLS LAST;


-- ================================================================================================
-- 13. TOP PROGRAMS WITHIN EACH ANALYTICAL FAMILY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TOP 10 PROGRAMS WITHIN EACH ANALYTICAL FAMILY'
\echo '----------------------------------------------------------------------------------------------------'

WITH ranked_family AS (
    SELECT
        f.*,
        ROW_NUMBER() OVER (
            PARTITION BY analytical_family
            ORDER BY obligation_amount DESC NULLS LAST, cfda_number
        ) AS family_rank
    FROM etl174b_5p_family f
)
SELECT
    analytical_family,
    family_rank,
    cfda_number,
    cfda_title,
    funding_agency_name,
    ROUND(obligation_amount, 2) AS obligation_amount,
    ROUND(pct_of_residual, 4) AS pct_of_total_residual,
    ROUND(covid_amount, 2) AS covid_amount,
    ROUND(iija_amount, 2) AS iija_amount,
    ROUND(extraordinary_amount, 2) AS extraordinary_amount
FROM ranked_family
WHERE family_rank <= 10
ORDER BY
    analytical_family,
    family_rank;


-- ================================================================================================
-- 14. COVID CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TOP 30 UNRESOLVED PROGRAMS BY COVID AMOUNT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    cfda_title,
    funding_agency_name,
    ROUND(obligation_amount, 2) AS total_obligation,
    ROUND(covid_amount, 2) AS covid_amount,
    ROUND(
        100.0 * covid_amount
        / NULLIF(obligation_amount, 0),
        4
    ) AS pct_program_amount_covid
FROM etl174b_5p_programs
WHERE covid_amount <> 0
ORDER BY covid_amount DESC NULLS LAST
LIMIT 30;


-- ================================================================================================
-- 15. IIJA CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TOP 30 UNRESOLVED PROGRAMS BY IIJA AMOUNT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    cfda_title,
    funding_agency_name,
    ROUND(obligation_amount, 2) AS total_obligation,
    ROUND(iija_amount, 2) AS iija_amount,
    ROUND(
        100.0 * iija_amount
        / NULLIF(obligation_amount, 0),
        4
    ) AS pct_program_amount_iija
FROM etl174b_5p_programs
WHERE iija_amount <> 0
ORDER BY iija_amount DESC NULLS LAST
LIMIT 30;


-- ================================================================================================
-- 16. EXTRAORDINARY FUNDING CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP 30 UNRESOLVED PROGRAMS BY EXTRAORDINARY AMOUNT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    cfda_title,
    funding_agency_name,
    ROUND(obligation_amount, 2) AS total_obligation,
    ROUND(extraordinary_amount, 2) AS extraordinary_amount,
    ROUND(
        100.0 * extraordinary_amount
        / NULLIF(obligation_amount, 0),
        4
    ) AS pct_program_amount_extraordinary
FROM etl174b_5p_programs
WHERE extraordinary_amount <> 0
ORDER BY extraordinary_amount DESC NULLS LAST
LIMIT 30;


-- ================================================================================================
-- 17. ORDINARY VS COVID VS OTHER EXTRAORDINARY
--
-- These dimensions can overlap. Therefore this is a diagnostic profile, not
-- an additive three-part bridge.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. FUNDING-DIMENSION PROFILE - NONADDITIVE DIAGNOSTIC'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(SUM(federal_action_obligation), 2) AS total_residual,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount,

    ROUND(
        SUM(
            CASE
                WHEN NOT is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS non_extraordinary_amount

FROM etl174b_5p_residual;


-- ================================================================================================
-- 18. TOP-25 TRIAGE QUEUE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. TOP-25 MATERIALITY TRIAGE QUEUE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    materiality_rank,
    analytical_family,
    cfda_number,
    cfda_title,
    funding_agency_name,
    ROUND(obligation_amount, 2) AS obligation_amount,
    ROUND(pct_of_residual, 4) AS pct_of_residual,
    ROUND(cumulative_pct_of_residual, 4) AS cumulative_pct,
    ROUND(covid_amount, 2) AS covid_amount,
    ROUND(iija_amount, 2) AS iija_amount,
    ROUND(extraordinary_amount, 2) AS extraordinary_amount
FROM etl174b_5p_family
WHERE materiality_rank <= 25
ORDER BY materiality_rank;


-- ================================================================================================
-- 19. TOP-25 CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. TOP-25 CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS program_count,
    ROUND(SUM(obligation_amount), 2) AS top_25_amount,
    ROUND(
        100.0 * SUM(obligation_amount)
        / 107284286183.21::numeric,
        4
    ) AS pct_of_residual,
    ROUND(SUM(covid_amount), 2) AS covid_amount,
    ROUND(SUM(iija_amount), 2) AS iija_amount,
    ROUND(SUM(extraordinary_amount), 2) AS extraordinary_amount
FROM etl174b_5p_programs
WHERE materiality_rank <= 25;


-- ================================================================================================
-- 20. COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5P PROFILE COMPLETE - RESIDUAL MATERIALITY TRIAGE - NO DB WRITES';
END
$$;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5P COMPLETE'
\echo '===================================================================================================='
\echo 'NO DATABASE WRITES'