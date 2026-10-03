/*
================================================================================
ETL-174B-5R
Post-Treasury Assistance Accounting Bridge
================================================================================

Purpose
-------
Reconstruct the Washington FY2020-FY2024 USAspending assistance accounting
bridge after Migration 180 persisted the Treasury fiscal-stabilization policy
for:

    21.019  Coronavirus Relief Fund
    21.023  Emergency Rental Assistance Program
    21.027  Coronavirus State and Local Fiscal Recovery Funds

This is the successor diagnostic to frozen ETL-174B-5O.

Resolution hierarchy
--------------------
1. Award-specific accounting classification
2. Explicit program -> source-policy mapping
3. UNCLASSIFIED_REVIEW

Important
---------
This script is READ ONLY with respect to persistent database objects.

Temporary tables are used only for analysis.

No accounting policy is created or changed.
No persistent database writes are authorized.

Expected gross universe
-----------------------
Transactions       : 942,243
Gross obligations  : 348,524,407,674.34
COVID              : 46,859,546,247.83
IIJA               : 8,129,817,959.24
Extraordinary      : 56,543,893,060.40

Frozen ETL-174B-5O baseline
---------------------------
EXCLUDE_DUPLICATE       234,974,673,851.81
INCLUDE_ADDITIVE          5,716,864,764.39
REFERENCE_ONLY                7,799,088.00
UNCLASSIFIED_REVIEW     107,284,286,183.21
WITHHOLD_UNRESOLVED         540,783,786.93

Migration 180 expected movement
-------------------------------
UNCLASSIFIED_REVIEW -> INCLUDE_ADDITIVE

Amount: 12,561,260,982.36

Expected ETL-174B-5R
--------------------
EXCLUDE_DUPLICATE       234,974,673,851.81
INCLUDE_ADDITIVE         18,278,125,746.75
REFERENCE_ONLY                7,799,088.00
UNCLASSIFIED_REVIEW      94,723,025,200.85
WITHHOLD_UNRESOLVED         540,783,786.93

Methodology
-----------
ETL-174B-5R is a reconstruction / validation step only.
================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5R POST-TREASURY ASSISTANCE ACCOUNTING BRIDGE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. BUILD GROSS WA ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5r_gross;

CREATE TEMP TABLE etl174b_5r_gross AS
SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year,
    l.cfda_number,
    l.cfda_title,
    l.award_id_fain,
    l.award_id_uri,
    l.recipient_name,
    l.funding_agency_name,
    l.federal_action_obligation,
    l.defc_codes,
    l.funding_families,
    l.is_covid,
    l.is_iija,
    l.is_extraordinary,
    l.transaction_description
FROM analysis.v_certified_assistance_ledger l
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024;


-- ================================================================================================
-- 2. HARD GROSS CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. GROSS ASSISTANCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS gross_obligations,
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
FROM etl174b_5r_gross;


DO $$
DECLARE
    v_transactions bigint;
    v_total        numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(SUM(CASE WHEN is_covid THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_iija THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_extraordinary THEN federal_action_obligation ELSE 0 END), 0)
    INTO
        v_transactions,
        v_total,
        v_covid,
        v_iija,
        v_extra
    FROM etl174b_5r_gross;

    IF v_transactions <> 942243 THEN
        RAISE EXCEPTION
            '5R GROSS CONTROL FAILED: expected 942243 transactions; found %',
            v_transactions;
    END IF;

    IF ABS(v_total - 348524407674.34::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R GROSS CONTROL FAILED: expected 348524407674.34; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 46859546247.83::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R COVID CONTROL FAILED: expected 46859546247.83; found %',
            v_covid;
    END IF;

    IF ABS(v_iija - 8129817959.24::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R IIJA CONTROL FAILED: expected 8129817959.24; found %',
            v_iija;
    END IF;

    IF ABS(v_extra - 56543893060.40::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R EXTRAORDINARY CONTROL FAILED: expected 56543893060.40; found %',
            v_extra;
    END IF;

    RAISE NOTICE
        '5R GROSS CONTROL PASS: transactions=% total=% COVID=% IIJA=% extraordinary=%',
        v_transactions,
        v_total,
        v_covid,
        v_iija,
        v_extra;
END
$$;


-- ================================================================================================
-- 3. BUILD AWARD-SPECIFIC CANDIDATES
--
-- An award identifier may be represented by FAIN or URI. Match the same
-- normalized identifier convention used in the existing award classification
-- architecture.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5r_award_candidates;

CREATE TEMP TABLE etl174b_5r_award_candidates AS
SELECT
    g.assistance_transaction_id,
    a.accounting_disposition,
    a.methodology_version,
    ROW_NUMBER() OVER (
        PARTITION BY g.assistance_transaction_id
        ORDER BY
            COALESCE(a.valid_from_fiscal_year, -2147483648) DESC,
            a.federal_inflow_award_classification_id DESC
    ) AS candidate_rank
FROM etl174b_5r_gross g
JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = g.cfda_number
 AND a.source_award_identifier =
     COALESCE(g.award_id_fain, g.award_id_uri)
 AND (
        a.valid_from_fiscal_year IS NULL
        OR g.action_date_fiscal_year >= a.valid_from_fiscal_year
     )
 AND (
        a.valid_through_fiscal_year IS NULL
        OR g.action_date_fiscal_year <= a.valid_through_fiscal_year
     );


-- ================================================================================================
-- 4. BUILD PROGRAM-POLICY CANDIDATES
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5r_program_candidates;

CREATE TEMP TABLE etl174b_5r_program_candidates AS
SELECT
    g.assistance_transaction_id,
    m.resolved_accounting_disposition,
    m.methodology_version,
    ROW_NUMBER() OVER (
        PARTITION BY g.assistance_transaction_id
        ORDER BY
            COALESCE(m.valid_from_fiscal_year, -2147483648) DESC,
            m.federal_inflow_program_policy_mapping_id DESC
    ) AS candidate_rank
FROM etl174b_5r_gross g
JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = g.cfda_number
 AND (
        m.valid_from_fiscal_year IS NULL
        OR g.action_date_fiscal_year >= m.valid_from_fiscal_year
     )
 AND (
        m.valid_through_fiscal_year IS NULL
        OR g.action_date_fiscal_year <= m.valid_through_fiscal_year
     );


-- ================================================================================================
-- 5. RESOLVE EVERY TRANSACTION EXACTLY ONCE
--
-- Hierarchy:
--     award-specific
--     program mapping
--     UNCLASSIFIED_REVIEW
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5r_resolved;

CREATE TEMP TABLE etl174b_5r_resolved AS
SELECT
    g.*,

    CASE
        WHEN a.assistance_transaction_id IS NOT NULL
            THEN a.accounting_disposition

        WHEN p.assistance_transaction_id IS NOT NULL
            THEN p.resolved_accounting_disposition

        ELSE 'UNCLASSIFIED_REVIEW'
    END AS final_accounting_disposition,

    CASE
        WHEN a.assistance_transaction_id IS NOT NULL
            THEN 'AWARD'

        WHEN p.assistance_transaction_id IS NOT NULL
            THEN 'PROGRAM'

        ELSE 'UNCLASSIFIED'
    END AS resolution_level,

    CASE
        WHEN a.assistance_transaction_id IS NOT NULL
            THEN a.methodology_version

        WHEN p.assistance_transaction_id IS NOT NULL
            THEN p.methodology_version

        ELSE NULL
    END AS resolution_methodology_version

FROM etl174b_5r_gross g

LEFT JOIN etl174b_5r_award_candidates a
  ON a.assistance_transaction_id = g.assistance_transaction_id
 AND a.candidate_rank = 1

LEFT JOIN etl174b_5r_program_candidates p
  ON p.assistance_transaction_id = g.assistance_transaction_id
 AND p.candidate_rank = 1;


-- ================================================================================================
-- 6. CARDINALITY CHECK
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. RESOLUTION CARDINALITY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS resolved_rows,
    COUNT(DISTINCT assistance_transaction_id) AS distinct_transactions
FROM etl174b_5r_resolved;


DO $$
DECLARE
    v_rows     bigint;
    v_distinct bigint;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id)
    INTO
        v_rows,
        v_distinct
    FROM etl174b_5r_resolved;

    IF v_rows <> 942243
       OR v_distinct <> 942243 THEN

        RAISE EXCEPTION
            '5R CARDINALITY FAILED: rows=% distinct=% expected=942243',
            v_rows,
            v_distinct;
    END IF;

    RAISE NOTICE
        '5R CARDINALITY PASS: 942243 transactions resolved exactly once';
END
$$;


-- ================================================================================================
-- 7. RESOLUTION LEVEL PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. RESOLUTION LEVEL PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_level,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
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
FROM etl174b_5r_resolved
GROUP BY resolution_level
ORDER BY resolution_level;


-- ================================================================================================
-- 8. FINAL ACCOUNTING DISPOSITION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FINAL ACCOUNTING DISPOSITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    final_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
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
FROM etl174b_5r_resolved
GROUP BY final_accounting_disposition
ORDER BY final_accounting_disposition;


-- ================================================================================================
-- 9. HARD POST-TREASURY DISPOSITION CONTROLS
-- ================================================================================================

DO $$
DECLARE
    v_exclude      numeric;
    v_include      numeric;
    v_reference    numeric;
    v_unclassified numeric;
    v_withhold     numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE final_accounting_disposition = 'EXCLUDE_DUPLICATE'
                ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE final_accounting_disposition = 'INCLUDE_ADDITIVE'
                ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE final_accounting_disposition = 'REFERENCE_ONLY'
                ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE final_accounting_disposition = 'UNCLASSIFIED_REVIEW'
                ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE final_accounting_disposition = 'WITHHOLD_UNRESOLVED'
                ),
            0
        )

    INTO
        v_exclude,
        v_include,
        v_reference,
        v_unclassified,
        v_withhold

    FROM etl174b_5r_resolved;


    IF ABS(v_exclude - 234974673851.81::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R EXCLUDE CONTROL FAILED: expected 234974673851.81; found %',
            v_exclude;
    END IF;

    IF ABS(v_include - 18278125746.75::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R INCLUDE CONTROL FAILED: expected 18278125746.75; found %',
            v_include;
    END IF;

    IF ABS(v_reference - 7799088.00::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R REFERENCE CONTROL FAILED: expected 7799088.00; found %',
            v_reference;
    END IF;

    IF ABS(v_unclassified - 94723025200.85::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R UNCLASSIFIED CONTROL FAILED: expected 94723025200.85; found %',
            v_unclassified;
    END IF;

    IF ABS(v_withhold - 540783786.93::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R WITHHOLD CONTROL FAILED: expected 540783786.93; found %',
            v_withhold;
    END IF;

    RAISE NOTICE
        '5R POST-TREASURY DISPOSITION CONTROL PASS';
END
$$;


-- ================================================================================================
-- 10. EXACT BRIDGE CLOSURE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. EXACT BRIDGE CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS resolved_total,

    348524407674.34::numeric AS expected_gross_total,

    ROUND(
        SUM(federal_action_obligation)
        - 348524407674.34::numeric,
        2
    ) AS closure_difference

FROM etl174b_5r_resolved;


DO $$
DECLARE
    v_total numeric;
BEGIN
    SELECT
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_total
    FROM etl174b_5r_resolved;

    IF ABS(v_total - 348524407674.34::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R BRIDGE CLOSURE FAILED: expected 348524407674.34; found %',
            v_total;
    END IF;

    RAISE NOTICE
        '5R EXACT BRIDGE CLOSURE PASS: %',
        v_total;
END
$$;


-- ================================================================================================
-- 11. MIGRATION 180 TREASURY CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. MIGRATION 180 TREASURY CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    final_accounting_disposition,
    resolution_level,
    resolution_methodology_version,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5r_resolved
WHERE cfda_number IN (
    '21.019',
    '21.023',
    '21.027'
)
GROUP BY
    cfda_number,
    final_accounting_disposition,
    resolution_level,
    resolution_methodology_version
ORDER BY cfda_number;


DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_total        numeric;
    v_covid        numeric;
    v_wrong        bigint;
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
        COUNT(*) FILTER (
            WHERE final_accounting_disposition <> 'INCLUDE_ADDITIVE'
               OR resolution_level <> 'PROGRAM'
               OR resolution_methodology_version <> 'ANALYSIS-174B-5Q-v1'
        )
    INTO
        v_transactions,
        v_programs,
        v_total,
        v_covid,
        v_wrong
    FROM etl174b_5r_resolved
    WHERE cfda_number IN (
        '21.019',
        '21.023',
        '21.027'
    );

    IF v_transactions <> 660 THEN
        RAISE EXCEPTION
            '5R TREASURY CONTROL FAILED: expected 660 transactions; found %',
            v_transactions;
    END IF;

    IF v_programs <> 3 THEN
        RAISE EXCEPTION
            '5R TREASURY CONTROL FAILED: expected 3 programs; found %',
            v_programs;
    END IF;

    IF ABS(v_total - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R TREASURY CONTROL FAILED: expected 12561260982.36; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R TREASURY COVID CONTROL FAILED: expected 12561260982.36; found %',
            v_covid;
    END IF;

    IF v_wrong <> 0 THEN
        RAISE EXCEPTION
            '5R TREASURY RESOLUTION FAILED: % transactions have unexpected disposition/resolution/methodology',
            v_wrong;
    END IF;

    RAISE NOTICE
        '5R TREASURY CONTROL PASS: 660 transactions; 3 programs; additive=12561260982.36; COVID preserved';
END
$$;


-- ================================================================================================
-- 12. 5O -> 5R MOVEMENT
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. ETL-174B-5O -> ETL-174B-5R MOVEMENT'
\echo '----------------------------------------------------------------------------------------------------'

WITH baseline AS (
    SELECT *
    FROM (
        VALUES
            ('EXCLUDE_DUPLICATE'::text,   234974673851.81::numeric),
            ('INCLUDE_ADDITIVE'::text,      5716864764.39::numeric),
            ('REFERENCE_ONLY'::text,            7799088.00::numeric),
            ('UNCLASSIFIED_REVIEW'::text, 107284286183.21::numeric),
            ('WITHHOLD_UNRESOLVED'::text,    540783786.93::numeric)
    ) AS b (
        final_accounting_disposition,
        baseline_amount
    )
),
current_bridge AS (
    SELECT
        final_accounting_disposition,
        SUM(federal_action_obligation) AS current_amount
    FROM etl174b_5r_resolved
    GROUP BY final_accounting_disposition
)
SELECT
    b.final_accounting_disposition,
    ROUND(b.baseline_amount, 2) AS etl174b_5o_amount,
    ROUND(COALESCE(c.current_amount, 0), 2) AS etl174b_5r_amount,
    ROUND(
        COALESCE(c.current_amount, 0)
        - b.baseline_amount,
        2
    ) AS movement
FROM baseline b
LEFT JOIN current_bridge c
  ON c.final_accounting_disposition =
     b.final_accounting_disposition
ORDER BY b.final_accounting_disposition;


-- ================================================================================================
-- 13. HARD MOVEMENT CHECK
-- ================================================================================================

DO $$
DECLARE
    v_include_delta      numeric;
    v_unclassified_delta numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE final_accounting_disposition = 'INCLUDE_ADDITIVE'
                ),
            0
        ) - 5716864764.39::numeric,

        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE final_accounting_disposition = 'UNCLASSIFIED_REVIEW'
                ),
            0
        ) - 107284286183.21::numeric

    INTO
        v_include_delta,
        v_unclassified_delta

    FROM etl174b_5r_resolved;


    IF ABS(v_include_delta - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5R MOVEMENT FAILED: INCLUDE delta expected +12561260982.36; found %',
            v_include_delta;
    END IF;

    IF ABS(v_unclassified_delta - (-12561260982.36::numeric)) > 0.01 THEN
        RAISE EXCEPTION
            '5R MOVEMENT FAILED: UNCLASSIFIED delta expected -12561260982.36; found %',
            v_unclassified_delta;
    END IF;

    IF ABS(v_include_delta + v_unclassified_delta) > 0.01 THEN
        RAISE EXCEPTION
            '5R MOVEMENT FAILED: movement is not zero-sum; include delta=% unclassified delta=%',
            v_include_delta,
            v_unclassified_delta;
    END IF;

    RAISE NOTICE
        '5R MOVEMENT PASS: exactly 12561260982.36 moved UNCLASSIFIED_REVIEW -> INCLUDE_ADDITIVE';
END
$$;


-- ================================================================================================
-- 14. ANNUAL TREASURY ADDITIVE PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TREASURY ADDITIVE PROFILE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS additive_amount,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_amount
FROM etl174b_5r_resolved
WHERE cfda_number IN (
    '21.019',
    '21.023',
    '21.027'
)
  AND final_accounting_disposition = 'INCLUDE_ADDITIVE'
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 15. UPDATED UNCLASSIFIED RESIDUAL BY AGENCY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. UPDATED UNCLASSIFIED RESIDUAL BY FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
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
    ) AS iija_amount
FROM etl174b_5r_resolved
WHERE final_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY COALESCE(funding_agency_name, '[NULL]')
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 16. UPDATED TOP 50 UNCLASSIFIED PROGRAMS
--
-- Use Assistance Listing number/title as the principal program identity.
-- funding_agency_name is contextual only because ETL-174B-5P identified
-- questionable agency metadata for some programs.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. UPDATED TOP 50 UNCLASSIFIED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        COUNT(*) AS transaction_count,
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
    FROM etl174b_5r_resolved
    WHERE final_accounting_disposition = 'UNCLASSIFIED_REVIEW'
    GROUP BY cfda_number
),
ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            ORDER BY obligation_amount DESC NULLS LAST, cfda_number
        ) AS materiality_rank,

        SUM(obligation_amount) OVER () AS residual_total,

        SUM(obligation_amount) OVER (
            ORDER BY obligation_amount DESC NULLS LAST, cfda_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_amount
    FROM program_totals p
)
SELECT
    materiality_rank,
    cfda_number,
    cfda_title,
    transaction_count,
    ROUND(obligation_amount, 2) AS obligation_amount,
    ROUND(covid_amount, 2) AS covid_amount,
    ROUND(iija_amount, 2) AS iija_amount,
    ROUND(extraordinary_amount, 2) AS extraordinary_amount,
    ROUND(
        100.0 * obligation_amount
        / NULLIF(residual_total, 0),
        4
    ) AS pct_of_residual,
    ROUND(
        100.0 * cumulative_amount
        / NULLIF(residual_total, 0),
        4
    ) AS cumulative_pct_of_residual
FROM ranked
WHERE materiality_rank <= 50
ORDER BY materiality_rank;


-- ================================================================================================
-- 17. UPDATED UNCLASSIFIED FUNDING-DIMENSION PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. UPDATED UNCLASSIFIED FUNDING-DIMENSION PROFILE'
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
            CASE WHEN NOT is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS non_covid_amount,

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

FROM etl174b_5r_resolved
WHERE final_accounting_disposition = 'UNCLASSIFIED_REVIEW';


-- ================================================================================================
-- 18. FINAL NO-WRITE COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5R RECONSTRUCTION COMPLETE - POST-TREASURY ASSISTANCE BRIDGE - NO PERSISTENT DB WRITES';
END
$$;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5R COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'