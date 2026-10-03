/*
================================================================================
ETL-174B-5U
POST-SNAP ASSISTANCE ACCOUNTING BRIDGE
================================================================================

Purpose
-------
Reconstruct the Washington FY2020-FY2024 USAspending assistance accounting
bridge after Migration 181 persisted SNAP 10.551 as INCLUDE_ADDITIVE.

READ ONLY.
NO PERSISTENT DATABASE WRITES.

Expected movement from frozen ETL-174B-5R:
    INCLUDE_ADDITIVE
        18,278,125,746.75
      + 11,879,986,141.72 SNAP
      = 30,158,111,888.47

    UNCLASSIFIED_REVIEW
        94,723,025,200.85
      - 11,879,986,141.72 SNAP
      = 82,843,039,059.13

All other dispositions must remain unchanged.

Gross assistance control:
    348,524,407,674.34

Scope:
    Washington
    FY2020-FY2024
    Certified USAspending assistance ledger

No database writes are authorized by this script.
================================================================================
*/


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5U POST-SNAP ASSISTANCE ACCOUNTING BRIDGE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. BUILD CERTIFIED WA FY2020-FY2024 POPULATION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5u_base;

CREATE TEMP TABLE etl174b_5u_base AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


-- ================================================================================================
-- 2. RESOLVE AWARD-SPECIFIC CLASSIFICATIONS
--
-- Award classification has precedence over program classification.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5u_award_resolution;

CREATE TEMP TABLE etl174b_5u_award_resolution AS
SELECT DISTINCT ON (b.assistance_transaction_id)
    b.assistance_transaction_id,
    a.accounting_disposition,
    a.methodology_version,
    a.classification_basis
FROM etl174b_5u_base b
JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = b.cfda_number
 AND a.source_award_identifier =
        COALESCE(NULLIF(b.award_id_fain, ''), NULLIF(b.award_id_uri, ''))
 AND (
        a.valid_from_fiscal_year IS NULL
        OR b.action_date_fiscal_year >= a.valid_from_fiscal_year
     )
 AND (
        a.valid_through_fiscal_year IS NULL
        OR b.action_date_fiscal_year <= a.valid_through_fiscal_year
     )
ORDER BY
    b.assistance_transaction_id,
    a.updated_at DESC,
    a.federal_inflow_award_classification_id DESC;


-- ================================================================================================
-- 3. RESOLVE PROGRAM-POLICY MAPPINGS
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5u_program_resolution;

CREATE TEMP TABLE etl174b_5u_program_resolution AS
SELECT DISTINCT ON (b.assistance_transaction_id)
    b.assistance_transaction_id,
    m.resolved_accounting_disposition AS accounting_disposition,
    m.methodology_version,
    m.mapping_basis
FROM etl174b_5u_base b
JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = b.cfda_number
 AND (
        m.valid_from_fiscal_year IS NULL
        OR b.action_date_fiscal_year >= m.valid_from_fiscal_year
     )
 AND (
        m.valid_through_fiscal_year IS NULL
        OR b.action_date_fiscal_year <= m.valid_through_fiscal_year
     )
ORDER BY
    b.assistance_transaction_id,
    m.updated_at DESC,
    m.federal_inflow_program_policy_mapping_id DESC;


-- ================================================================================================
-- 4. BUILD EFFECTIVE TRANSACTION ACCOUNTING BRIDGE
--
-- Precedence:
--     AWARD
--     PROGRAM
--     UNCLASSIFIED
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5u_bridge;

CREATE TEMP TABLE etl174b_5u_bridge AS
SELECT
    b.*,

    CASE
        WHEN ar.assistance_transaction_id IS NOT NULL THEN 'AWARD'
        WHEN pr.assistance_transaction_id IS NOT NULL THEN 'PROGRAM'
        ELSE 'UNCLASSIFIED'
    END AS resolution_level,

    CASE
        WHEN ar.assistance_transaction_id IS NOT NULL
            THEN ar.accounting_disposition
        WHEN pr.assistance_transaction_id IS NOT NULL
            THEN pr.accounting_disposition
        ELSE 'UNCLASSIFIED_REVIEW'
    END AS effective_accounting_disposition,

    COALESCE(
        ar.methodology_version,
        pr.methodology_version
    ) AS effective_methodology_version

FROM etl174b_5u_base b
LEFT JOIN etl174b_5u_award_resolution ar
  ON ar.assistance_transaction_id = b.assistance_transaction_id
LEFT JOIN etl174b_5u_program_resolution pr
  ON pr.assistance_transaction_id = b.assistance_transaction_id;


-- ================================================================================================
-- 5. GROSS UNIVERSE CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. GROSS ASSISTANCE UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS gross_obligations,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5u_bridge;


DO $$
DECLARE
    v_count bigint;
    v_total numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO
        v_count,
        v_total
    FROM etl174b_5u_bridge;

    IF v_count <> 942243 THEN
        RAISE EXCEPTION
            '5U GROSS CONTROL FAILED: expected 942243 transactions; found %',
            v_count;
    END IF;

    IF ABS(v_total - 348524407674.34::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5U GROSS CONTROL FAILED: expected 348524407674.34; found %',
            v_total;
    END IF;

    RAISE NOTICE
        '5U GROSS CONTROL PASS: transactions=% total=%',
        v_count,
        v_total;
END
$$;


-- ================================================================================================
-- 6. RESOLUTION LEVEL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. RESOLUTION LEVEL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_level,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5u_bridge
GROUP BY resolution_level
ORDER BY resolution_level;


-- ================================================================================================
-- 7. EFFECTIVE ACCOUNTING DISPOSITION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. EFFECTIVE ACCOUNTING DISPOSITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5u_bridge
GROUP BY effective_accounting_disposition
ORDER BY effective_accounting_disposition;


-- ================================================================================================
-- 8. HARD POST-SNAP ACCOUNTING CONTROL
-- ================================================================================================

DO $$
DECLARE
    v_exclude     numeric;
    v_include     numeric;
    v_reference   numeric;
    v_unclassified numeric;
    v_withhold    numeric;
    v_closure     numeric;
BEGIN
    SELECT
        COALESCE(SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'EXCLUDE_DUPLICATE'
            ), 0),

        COALESCE(SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'INCLUDE_ADDITIVE'
            ), 0),

        COALESCE(SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'REFERENCE_ONLY'
            ), 0),

        COALESCE(SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
            ), 0),

        COALESCE(SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'WITHHOLD_UNRESOLVED'
            ), 0)

    INTO
        v_exclude,
        v_include,
        v_reference,
        v_unclassified,
        v_withhold
    FROM etl174b_5u_bridge;

    IF ABS(v_exclude - 234974673851.81::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5U CONTROL FAILED: EXCLUDE expected 234974673851.81; found %',
            v_exclude;
    END IF;

    IF ABS(v_include - 30158111888.47::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5U CONTROL FAILED: INCLUDE expected 30158111888.47; found %',
            v_include;
    END IF;

    IF ABS(v_reference - 7799088.00::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5U CONTROL FAILED: REFERENCE expected 7799088.00; found %',
            v_reference;
    END IF;

    IF ABS(v_unclassified - 82843039059.13::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5U CONTROL FAILED: UNCLASSIFIED expected 82843039059.13; found %',
            v_unclassified;
    END IF;

    IF ABS(v_withhold - 540783786.93::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5U CONTROL FAILED: WITHHOLD expected 540783786.93; found %',
            v_withhold;
    END IF;

    v_closure :=
          v_exclude
        + v_include
        + v_reference
        + v_unclassified
        + v_withhold
        - 348524407674.34::numeric;

    IF ABS(v_closure) > 0.01 THEN
        RAISE EXCEPTION
            '5U BRIDGE CLOSURE FAILED: difference=%',
            v_closure;
    END IF;

    RAISE NOTICE
        '5U POST-SNAP CONTROL PASS: EXCLUDE=% INCLUDE=% REFERENCE=% UNCLASSIFIED=% WITHHOLD=% CLOSURE=%',
        v_exclude,
        v_include,
        v_reference,
        v_unclassified,
        v_withhold,
        v_closure;
END
$$;


-- ================================================================================================
-- 9. SNAP CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. SNAP 10.551 CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,
    effective_methodology_version,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount
FROM etl174b_5u_bridge
WHERE cfda_number = '10.551'
GROUP BY
    effective_accounting_disposition,
    effective_methodology_version;


-- ================================================================================================
-- 10. ANNUAL ACCOUNTING BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. ANNUAL ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS gross_assistance,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'EXCLUDE_DUPLICATE'
            )::numeric,
        2
    ) AS exclude_duplicate,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'INCLUDE_ADDITIVE'
            )::numeric,
        2
    ) AS include_additive,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'WITHHOLD_UNRESOLVED'
            )::numeric,
        2
    ) AS withhold_unresolved,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'REFERENCE_ONLY'
            )::numeric,
        2
    ) AS reference_only,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
            )::numeric,
        2
    ) AS unclassified_review

FROM etl174b_5u_bridge
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 11. ADDITIVE COVID / NON-COVID PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. INCLUDE_ADDITIVE FUNDING PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'INCLUDE_ADDITIVE'
            )::numeric,
        2
    ) AS additive_total,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'INCLUDE_ADDITIVE'
                  AND is_covid
            )::numeric,
        2
    ) AS additive_covid,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'INCLUDE_ADDITIVE'
                  AND NOT is_covid
            )::numeric,
        2
    ) AS additive_non_covid,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition = 'INCLUDE_ADDITIVE'
                  AND is_iija
            )::numeric,
        2
    ) AS additive_iija

FROM etl174b_5u_bridge
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 12. REMAINING UNCLASSIFIED RESIDUAL BY PROGRAM
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. REMAINING UNCLASSIFIED PROGRAMS - MATERIALITY RANKING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount,

    ROUND(
        100.0
        * SUM(federal_action_obligation)
        / 82843039059.13::numeric,
        4
    ) AS pct_of_remaining_residual

FROM etl174b_5u_bridge
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC
LIMIT 50;


-- ================================================================================================
-- 13. REMAINING RESIDUAL BY FUNDING AGENCY
--
-- Agency is contextual only. It is NOT the classification identity.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. REMAINING UNCLASSIFIED RESIDUAL BY FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    funding_agency_name,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM etl174b_5u_bridge
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY funding_agency_name
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 14. MATERIALITY CURVE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. REMAINING PROGRAM MATERIALITY CURVE'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        SUM(federal_action_obligation) AS obligation_amount
    FROM etl174b_5u_bridge
    WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
    GROUP BY cfda_number
),
ranked AS (
    SELECT
        cfda_number,
        cfda_title,
        obligation_amount,
        ROW_NUMBER() OVER (
            ORDER BY obligation_amount DESC
        ) AS materiality_rank,
        SUM(obligation_amount) OVER (
            ORDER BY obligation_amount DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_amount
    FROM program_totals
)
SELECT
    materiality_rank,
    cfda_number,
    cfda_title,
    ROUND(obligation_amount::numeric, 2) AS obligation_amount,
    ROUND(cumulative_amount::numeric, 2) AS cumulative_amount,
    ROUND(
        100.0 * cumulative_amount / 82843039059.13::numeric,
        4
    ) AS cumulative_pct_of_residual
FROM ranked
WHERE materiality_rank <= 50
ORDER BY materiality_rank;


-- ================================================================================================
-- 15. THRESHOLD SUMMARY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. PROGRAMS REQUIRED TO REACH MATERIALITY THRESHOLDS'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        SUM(federal_action_obligation) AS obligation_amount
    FROM etl174b_5u_bridge
    WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
    GROUP BY cfda_number
),
ranked AS (
    SELECT
        cfda_number,
        obligation_amount,
        ROW_NUMBER() OVER (
            ORDER BY obligation_amount DESC
        ) AS materiality_rank,
        SUM(obligation_amount) OVER (
            ORDER BY obligation_amount DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_amount
    FROM program_totals
),
thresholds(threshold_pct) AS (
    VALUES
        (25.0::numeric),
        (50.0::numeric),
        (75.0::numeric),
        (80.0::numeric),
        (90.0::numeric),
        (95.0::numeric)
)
SELECT
    t.threshold_pct,
    MIN(r.materiality_rank) AS programs_required,
    ROUND(
        MIN(r.cumulative_amount)
            FILTER (
                WHERE 100.0 * r.cumulative_amount
                      / 82843039059.13::numeric
                      >= t.threshold_pct
            )::numeric,
        2
    ) AS cumulative_amount
FROM thresholds t
CROSS JOIN ranked r
GROUP BY t.threshold_pct
ORDER BY t.threshold_pct;


-- ================================================================================================
-- 16. TOP 25 SHARE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. TOP-25 REMAINING PROGRAM SHARE'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        SUM(federal_action_obligation) AS obligation_amount
    FROM etl174b_5u_bridge
    WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
    GROUP BY cfda_number
),
ranked AS (
    SELECT
        cfda_number,
        obligation_amount,
        ROW_NUMBER() OVER (
            ORDER BY obligation_amount DESC
        ) AS materiality_rank
    FROM program_totals
)
SELECT
    ROUND(
        SUM(obligation_amount)
            FILTER (WHERE materiality_rank <= 25)::numeric,
        2
    ) AS top_25_amount,

    ROUND(
        100.0
        * SUM(obligation_amount)
            FILTER (WHERE materiality_rank <= 25)
        / 82843039059.13::numeric,
        4
    ) AS top_25_pct_of_residual,

    COUNT(*) AS remaining_program_count
FROM ranked;


-- ================================================================================================
-- 17. BRIDGE CLOSURE DISPLAY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. ACCOUNTING BRIDGE CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS gross_assistance,

    ROUND(
        SUM(
            CASE
                WHEN effective_accounting_disposition = 'EXCLUDE_DUPLICATE'
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS exclude_duplicate,

    ROUND(
        SUM(
            CASE
                WHEN effective_accounting_disposition = 'INCLUDE_ADDITIVE'
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS include_additive,

    ROUND(
        SUM(
            CASE
                WHEN effective_accounting_disposition = 'WITHHOLD_UNRESOLVED'
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS withhold_unresolved,

    ROUND(
        SUM(
            CASE
                WHEN effective_accounting_disposition = 'REFERENCE_ONLY'
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS reference_only,

    ROUND(
        SUM(
            CASE
                WHEN effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS unclassified_review,

    ROUND(
        (
            SUM(federal_action_obligation)
            -
            SUM(
                CASE
                    WHEN effective_accounting_disposition IN (
                        'EXCLUDE_DUPLICATE',
                        'INCLUDE_ADDITIVE',
                        'WITHHOLD_UNRESOLVED',
                        'REFERENCE_ONLY',
                        'UNCLASSIFIED_REVIEW'
                    )
                    THEN federal_action_obligation
                    ELSE 0
                END
            )
        )::numeric,
        2
    ) AS closure_difference

FROM etl174b_5u_bridge;


-- ================================================================================================
-- 18. COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5U COMPLETE - POST-SNAP ASSISTANCE BRIDGE RECONSTRUCTED - NO PERSISTENT DB WRITES';
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5U COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'