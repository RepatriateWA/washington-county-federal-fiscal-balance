/*
================================================================================
ETL-174B-5W
POST-TRANSPORTATION ASSISTANCE BRIDGE
================================================================================

Purpose
-------
Independently reconstruct the Washington FY2020-FY2024 USAspending assistance
accounting bridge after ETL-182.

READ ONLY.
NO PERSISTENT DATABASE WRITES.

Resolution precedence
---------------------
1. Award-level classification
2. Program-policy mapping
3. Otherwise UNCLASSIFIED_REVIEW

Expected controls
-----------------
Gross assistance universe:
    transactions       942,243
    programs           1,351
    obligation amount  $348,524,407,674.34
    COVID              $46,859,546,247.83
    IIJA                $8,129,817,959.24
    extraordinary      $56,543,893,060.40

Pre-transportation ETL-174B-5U:
    INCLUDE_ADDITIVE       $30,158,111,888.47
    UNCLASSIFIED_REVIEW    $82,843,039,059.13

ETL-182 transportation addition:
    INCLUDE_ADDITIVE       $12,303,575,682.42

Expected post-ETL-182:
    INCLUDE_ADDITIVE       $42,461,687,570.89
    UNCLASSIFIED_REVIEW    $70,539,463,376.71

Other expected disposition controls:
    EXCLUDE_DUPLICATE      $234,974,673,851.81
    WITHHOLD_UNRESOLVED       $540,783,786.93
    REFERENCE_ONLY              $7,799,088.00

Expected accounting closure:
    $0.00

================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5W POST-TRANSPORTATION ASSISTANCE BRIDGE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. MATERIALIZE CERTIFIED WA ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5w_ledger;

CREATE TEMP TABLE etl174b_5w_ledger AS
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
    transaction_description,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier

FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


CREATE INDEX ON etl174b_5w_ledger (cfda_number);
CREATE INDEX ON etl174b_5w_ledger (source_award_identifier);
CREATE INDEX ON etl174b_5w_ledger (action_date_fiscal_year);


-- ================================================================================================
-- 2. GROSS UNIVERSE CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. GROSS ASSISTANCE UNIVERSE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5w_ledger;


DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_total        numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(SUM(CASE WHEN is_covid
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_iija
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_extraordinary
                          THEN federal_action_obligation ELSE 0 END), 0)
    INTO
        v_transactions,
        v_programs,
        v_total,
        v_covid,
        v_iija,
        v_extra
    FROM etl174b_5w_ledger;

    IF v_transactions <> 942243
       OR v_programs <> 1351
       OR ABS(v_total - 348524407674.34::numeric) > 0.01
       OR ABS(v_covid - 46859546247.83::numeric) > 0.01
       OR ABS(v_iija - 8129817959.24::numeric) > 0.01
       OR ABS(v_extra - 56543893060.40::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5W GROSS CONTROL FAILED: tx=% programs=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_total,
            v_covid,
            v_iija,
            v_extra;
    END IF;

    RAISE NOTICE
        'ETL-174B-5W GROSS CONTROL PASS: tx=% programs=% total=%',
        v_transactions,
        v_programs,
        v_total;
END
$$;


-- ================================================================================================
-- 3. RESOLVE AWARD-LEVEL CLASSIFICATIONS
--
-- If more than one valid award classification applies to the same transaction,
-- fail closed rather than arbitrarily selecting one.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5w_award_matches;

CREATE TEMP TABLE etl174b_5w_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition,
    a.inflow_family,
    a.inflow_subfamily,
    a.methodology_version
FROM etl174b_5w_ledger l
JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = l.cfda_number
 AND a.source_award_identifier = l.source_award_identifier
 AND (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= a.valid_from_fiscal_year
     )
 AND (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= a.valid_through_fiscal_year
     );


DO $$
DECLARE
    v_duplicate_transactions bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_duplicate_transactions
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5w_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) d;

    IF v_duplicate_transactions <> 0 THEN
        RAISE EXCEPTION
            'ETL-174B-5W AWARD RESOLUTION FAILED: % transactions have multiple applicable award classifications',
            v_duplicate_transactions;
    END IF;

    RAISE NOTICE
        'ETL-174B-5W AWARD RESOLUTION UNIQUENESS PASS';
END
$$;


-- ================================================================================================
-- 4. RESOLVE PROGRAM-POLICY MAPPINGS
--
-- Same fail-closed rule: one applicable mapping maximum per transaction.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5w_program_matches;

CREATE TEMP TABLE etl174b_5w_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition AS accounting_disposition,
    p.inflow_family,
    p.inflow_subfamily,
    m.methodology_version
FROM etl174b_5w_ledger l
JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = l.cfda_number
 AND (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >= m.valid_from_fiscal_year
     )
 AND (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <= m.valid_through_fiscal_year
     )
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id;


DO $$
DECLARE
    v_duplicate_transactions bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_duplicate_transactions
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5w_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) d;

    IF v_duplicate_transactions <> 0 THEN
        RAISE EXCEPTION
            'ETL-174B-5W PROGRAM RESOLUTION FAILED: % transactions have multiple applicable program mappings',
            v_duplicate_transactions;
    END IF;

    RAISE NOTICE
        'ETL-174B-5W PROGRAM RESOLUTION UNIQUENESS PASS';
END
$$;


-- ================================================================================================
-- 5. BUILD EFFECTIVE RESOLUTION
--
-- Award classification has precedence over program mapping.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5w_resolved;

CREATE TEMP TABLE etl174b_5w_resolved AS
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
        p.accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_accounting_disposition,

    COALESCE(
        a.inflow_family,
        p.inflow_family
    ) AS resolved_inflow_family,

    COALESCE(
        a.inflow_subfamily,
        p.inflow_subfamily
    ) AS resolved_inflow_subfamily,

    COALESCE(
        a.methodology_version,
        p.methodology_version
    ) AS resolution_methodology_version

FROM etl174b_5w_ledger l
LEFT JOIN etl174b_5w_award_matches a
  ON a.assistance_transaction_id = l.assistance_transaction_id
LEFT JOIN etl174b_5w_program_matches p
  ON p.assistance_transaction_id = l.assistance_transaction_id;


CREATE INDEX ON etl174b_5w_resolved (effective_accounting_disposition);
CREATE INDEX ON etl174b_5w_resolved (resolution_level);
CREATE INDEX ON etl174b_5w_resolved (cfda_number);


-- ================================================================================================
-- 6. RESOLUTION-LEVEL SUMMARY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. RESOLUTION LEVEL SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_level,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5w_resolved
GROUP BY resolution_level
ORDER BY resolution_level;


-- ================================================================================================
-- 7. EFFECTIVE ACCOUNTING-DISPOSITION BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. EFFECTIVE ACCOUNTING-DISPOSITION BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5w_resolved
GROUP BY effective_accounting_disposition
ORDER BY effective_accounting_disposition;


-- ================================================================================================
-- 8. EXPECTED POST-TRANSPORTATION ACCOUNTING CONTROLS
-- ================================================================================================

DO $$
DECLARE
    v_exclude     numeric;
    v_include     numeric;
    v_reference   numeric;
    v_unclassified numeric;
    v_withhold    numeric;
    v_gross       numeric;
    v_closure     numeric;
BEGIN
    SELECT
        COALESCE(SUM(federal_action_obligation)
                 FILTER (WHERE effective_accounting_disposition =
                               'EXCLUDE_DUPLICATE'), 0),

        COALESCE(SUM(federal_action_obligation)
                 FILTER (WHERE effective_accounting_disposition =
                               'INCLUDE_ADDITIVE'), 0),

        COALESCE(SUM(federal_action_obligation)
                 FILTER (WHERE effective_accounting_disposition =
                               'REFERENCE_ONLY'), 0),

        COALESCE(SUM(federal_action_obligation)
                 FILTER (WHERE effective_accounting_disposition =
                               'UNCLASSIFIED_REVIEW'), 0),

        COALESCE(SUM(federal_action_obligation)
                 FILTER (WHERE effective_accounting_disposition =
                               'WITHHOLD_UNRESOLVED'), 0),

        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_exclude,
        v_include,
        v_reference,
        v_unclassified,
        v_withhold,
        v_gross

    FROM etl174b_5w_resolved;

    v_closure :=
        v_gross
        - (
            v_exclude
          + v_include
          + v_reference
          + v_unclassified
          + v_withhold
        );

    IF ABS(v_exclude - 234974673851.81::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5W EXCLUDE CONTROL FAILED: expected 234974673851.81; found %',
            v_exclude;
    END IF;

    IF ABS(v_include - 42461687570.89::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5W INCLUDE CONTROL FAILED: expected 42461687570.89; found %',
            v_include;
    END IF;

    IF ABS(v_reference - 7799088.00::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5W REFERENCE CONTROL FAILED: expected 7799088.00; found %',
            v_reference;
    END IF;

    IF ABS(v_unclassified - 70539463376.71::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5W UNCLASSIFIED CONTROL FAILED: expected 70539463376.71; found %',
            v_unclassified;
    END IF;

    IF ABS(v_withhold - 540783786.93::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5W WITHHOLD CONTROL FAILED: expected 540783786.93; found %',
            v_withhold;
    END IF;

    IF ABS(v_closure) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5W CLOSURE FAILED: expected 0.00; found %',
            v_closure;
    END IF;

    RAISE NOTICE
        'ETL-174B-5W ACCOUNTING CONTROL PASS: exclude=% include=% reference=% withhold=% unclassified=% closure=%',
        v_exclude,
        v_include,
        v_reference,
        v_withhold,
        v_unclassified,
        v_closure;
END
$$;


-- ================================================================================================
-- 9. ANNUAL ACCOUNTING BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. ANNUAL ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS gross_assistance,

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
    ) AS unclassified_review,

    ROUND(
        (
            SUM(federal_action_obligation)
            -
            (
                COALESCE(
                    SUM(federal_action_obligation)
                    FILTER (
                        WHERE effective_accounting_disposition =
                              'EXCLUDE_DUPLICATE'
                    ),
                    0
                )
              + COALESCE(
                    SUM(federal_action_obligation)
                    FILTER (
                        WHERE effective_accounting_disposition =
                              'INCLUDE_ADDITIVE'
                    ),
                    0
                )
              + COALESCE(
                    SUM(federal_action_obligation)
                    FILTER (
                        WHERE effective_accounting_disposition =
                              'WITHHOLD_UNRESOLVED'
                    ),
                    0
                )
              + COALESCE(
                    SUM(federal_action_obligation)
                    FILTER (
                        WHERE effective_accounting_disposition =
                              'REFERENCE_ONLY'
                    ),
                    0
                )
              + COALESCE(
                    SUM(federal_action_obligation)
                    FILTER (
                        WHERE effective_accounting_disposition =
                              'UNCLASSIFIED_REVIEW'
                    ),
                    0
                )
            )
        )::numeric,
        2
    ) AS closure

FROM etl174b_5w_resolved
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 10. ADDITIVE FUNDING-PROVENANCE SUMMARY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. INCLUDE_ADDITIVE FUNDING PROVENANCE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS additive_total,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS additive_covid,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS additive_iija,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS additive_extraordinary

FROM etl174b_5w_resolved
WHERE effective_accounting_disposition = 'INCLUDE_ADDITIVE'
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 11. TRANSPORTATION FAMILY RECONSTRUCTION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TRANSPORTATION ASSISTANCE FAMILY RECONSTRUCTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_inflow_subfamily,
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5w_resolved
WHERE resolution_level = 'PROGRAM'
  AND effective_accounting_disposition = 'INCLUDE_ADDITIVE'
  AND resolved_inflow_family = 'TRANSPORTATION_ASSISTANCE'
GROUP BY
    resolved_inflow_subfamily,
    cfda_number
ORDER BY
    resolved_inflow_subfamily,
    cfda_number;


-- ================================================================================================
-- 12. REMAINING UNCLASSIFIED PROGRAM RANKING
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5w_residual_programs;

CREATE TEMP TABLE etl174b_5w_residual_programs AS
WITH program_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT source_award_identifier) AS award_count,
        COUNT(DISTINCT recipient_name) AS recipient_count,

        SUM(federal_action_obligation)::numeric
            AS obligation_amount,

        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric AS covid_amount,

        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric AS iija_amount,

        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric AS extraordinary_amount

    FROM etl174b_5w_resolved
    WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
    GROUP BY cfda_number
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            ORDER BY obligation_amount DESC, cfda_number
        ) AS materiality_rank,

        SUM(obligation_amount) OVER (
            ORDER BY obligation_amount DESC, cfda_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_amount,

        SUM(obligation_amount) OVER () AS residual_total

    FROM program_totals
)
SELECT *
FROM ranked;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TOP 50 REMAINING UNCLASSIFIED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    materiality_rank,
    cfda_number,
    cfda_title,
    transaction_count,
    award_count,
    recipient_count,
    ROUND(obligation_amount, 2) AS obligation_amount,
    ROUND(covid_amount, 2) AS covid_amount,
    ROUND(iija_amount, 2) AS iija_amount,
    ROUND(extraordinary_amount, 2) AS extraordinary_amount,
    ROUND(
        100.0 * obligation_amount /
        NULLIF(residual_total, 0),
        4
    ) AS residual_pct,
    ROUND(
        100.0 * cumulative_amount /
        NULLIF(residual_total, 0),
        4
    ) AS cumulative_pct
FROM etl174b_5w_residual_programs
ORDER BY materiality_rank
LIMIT 50;


-- ================================================================================================
-- 13. CORRECTED MATERIALITY THRESHOLD SUMMARY
--
-- This fixes the 5U reporting bug. MIN(materiality_rank) is filtered to rows
-- whose cumulative share actually reaches the threshold.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. CORRECTED RESIDUAL MATERIALITY THRESHOLDS'
\echo '----------------------------------------------------------------------------------------------------'

WITH thresholds(threshold_pct) AS (
    VALUES
        (25.0::numeric),
        (50.0::numeric),
        (75.0::numeric),
        (90.0::numeric),
        (95.0::numeric)
)
SELECT
    t.threshold_pct,

    MIN(r.materiality_rank)
        FILTER (
            WHERE
                100.0 * r.cumulative_amount /
                NULLIF(r.residual_total, 0)
                >= t.threshold_pct
        ) AS programs_required,

    MIN(r.cumulative_amount)
        FILTER (
            WHERE
                100.0 * r.cumulative_amount /
                NULLIF(r.residual_total, 0)
                >= t.threshold_pct
        ) AS cumulative_amount_at_threshold

FROM thresholds t
CROSS JOIN etl174b_5w_residual_programs r
GROUP BY t.threshold_pct
ORDER BY t.threshold_pct;


-- ================================================================================================
-- 14. REMAINING RESIDUAL BY FUNDING AGENCY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. REMAINING UNCLASSIFIED BY FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5w_resolved
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY COALESCE(funding_agency_name, '[NULL]')
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 15. TOP 25 REMAINING PROGRAMS BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. TOP 25 REMAINING PROGRAMS BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

WITH top_programs AS (
    SELECT cfda_number
    FROM etl174b_5w_residual_programs
    ORDER BY materiality_rank
    LIMIT 25
)
SELECT
    r.cfda_number,
    MAX(r.cfda_title) AS cfda_title,
    r.action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(SUM(r.federal_action_obligation)::numeric, 2)
        AS obligation_amount,
    ROUND(
        SUM(CASE WHEN r.is_covid
                 THEN r.federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN r.is_iija
                 THEN r.federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount
FROM etl174b_5w_resolved r
JOIN top_programs t
  ON t.cfda_number = r.cfda_number
WHERE r.effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY
    r.cfda_number,
    r.action_date_fiscal_year
ORDER BY
    (
        SELECT materiality_rank
        FROM etl174b_5w_residual_programs p
        WHERE p.cfda_number = r.cfda_number
    ),
    r.action_date_fiscal_year;


-- ================================================================================================
-- 16. RESIDUAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. REMAINING RESIDUAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5w_resolved
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW';


-- ================================================================================================
-- 17. FINAL CERTIFICATION
-- ================================================================================================

DO $$
DECLARE
    v_residual numeric;
BEGIN
    SELECT COALESCE(SUM(federal_action_obligation), 0)
    INTO v_residual
    FROM etl174b_5w_resolved
    WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW';

    IF ABS(v_residual - 70539463376.71::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5W FINAL RESIDUAL CONTROL FAILED: expected 70539463376.71; found %',
            v_residual;
    END IF;

    RAISE NOTICE
        'ETL-174B-5W PASS - post-transportation bridge independently reconstructed; remaining UNCLASSIFIED_REVIEW=%; NO PERSISTENT DB WRITES',
        v_residual;
END
$$;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5W COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'