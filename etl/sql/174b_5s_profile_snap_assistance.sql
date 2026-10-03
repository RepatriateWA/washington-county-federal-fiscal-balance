/*
================================================================================
ETL-174B-5S
SNAP Assistance Accounting Profile
================================================================================

Purpose
-------
Build a read-only evidence profile for Assistance Listing:

    10.551  Supplemental Nutrition Assistance Program (SNAP)

ETL-174B-5R established 10.551 as the largest remaining
UNCLASSIFIED_REVIEW program.

Questions
---------
1. Reproduce the frozen 5R SNAP control exactly.
2. Establish annual obligation timing.
3. Separate ordinary and COVID-tagged funding.
4. Profile DEFC / funding-family provenance.
5. Identify recipients and award structure.
6. Examine transaction descriptions for benefit, administrative,
   emergency-allotment, P-EBT, or other semantic distinctions.
7. Measure positive obligations and deobligations.
8. Search existing WCFFBP program classifications and accounting policies.
9. Profile related USDA nutrition programs for overlap context.
10. Determine whether award-level or transaction-level refinement may be
    required before an accounting disposition can be persisted.

IMPORTANT
---------
This script does NOT classify 10.551 as additive or duplicative.

No persistent database writes are authorized.
================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5S SNAP ASSISTANCE ACCOUNTING PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. BUILD TARGET POPULATION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5s_snap;

CREATE TEMP TABLE etl174b_5s_snap AS
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
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.cfda_number = '10.551';


-- ================================================================================================
-- 2. HARD 5R CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. ETL-174B-5R SNAP CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
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
FROM etl174b_5s_snap;


DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_total        numeric;
    v_covid        numeric;
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
        )
    INTO
        v_transactions,
        v_programs,
        v_total,
        v_covid
    FROM etl174b_5s_snap;

    IF v_transactions <> 59 THEN
        RAISE EXCEPTION
            '5S CONTROL FAILED: expected 59 transactions; found %',
            v_transactions;
    END IF;

    IF v_programs <> 1 THEN
        RAISE EXCEPTION
            '5S CONTROL FAILED: expected 1 program; found %',
            v_programs;
    END IF;

    IF ABS(v_total - 11879986141.72::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5S CONTROL FAILED: expected 11879986141.72; found %',
            v_total;
    END IF;

    IF ABS(v_covid - 9549726843.52::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5S COVID CONTROL FAILED: expected 9549726843.52; found %',
            v_covid;
    END IF;

    RAISE NOTICE
        '5S 5R-CONTROL PASS: transactions=% total=% COVID=%',
        v_transactions,
        v_total,
        v_covid;
END
$$;


-- ================================================================================================
-- 3. ANNUAL PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. SNAP ANNUAL PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,

    ROUND(SUM(federal_action_obligation), 2) AS net_obligations,

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
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount

FROM etl174b_5s_snap
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 4. FUNDING PROVENANCE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. SNAP FUNDING PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount
FROM etl174b_5s_snap
GROUP BY
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 5. TRANSACTION SIGN PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. SNAP TRANSACTION SIGN PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) FILTER (
        WHERE federal_action_obligation > 0
    ) AS positive_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (WHERE federal_action_obligation > 0),
            0
        ),
        2
    ) AS positive_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (WHERE federal_action_obligation < 0),
            0
        ),
        2
    ) AS negative_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions,

    ROUND(SUM(federal_action_obligation), 2) AS net_obligations

FROM etl174b_5s_snap;


-- ================================================================================================
-- 6. ANNUAL SIGN PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. SNAP ANNUAL POSITIVE / NEGATIVE PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) FILTER (
        WHERE federal_action_obligation > 0
    ) AS positive_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (WHERE federal_action_obligation > 0),
            0
        ),
        2
    ) AS positive_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (WHERE federal_action_obligation < 0),
            0
        ),
        2
    ) AS negative_obligations,

    ROUND(SUM(federal_action_obligation), 2) AS net_obligations

FROM etl174b_5s_snap
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 7. RECIPIENT PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. SNAP RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(recipient_name, '[NULL]') AS recipient_name,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
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
        100.0 * SUM(federal_action_obligation)
        / NULLIF(
            SUM(SUM(federal_action_obligation)) OVER (),
            0
        ),
        4
    ) AS pct_of_snap
FROM etl174b_5s_snap
GROUP BY COALESCE(recipient_name, '[NULL]')
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 8. AWARD PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. SNAP AWARD PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    award_id_fain,
    award_id_uri,
    COALESCE(recipient_name, '[NULL]') AS recipient_name,
    MIN(action_date_fiscal_year) AS first_fiscal_year,
    MAX(action_date_fiscal_year) AS last_fiscal_year,
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
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE WHEN NOT is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS non_covid_amount
FROM etl174b_5s_snap
GROUP BY
    award_id_fain,
    award_id_uri,
    COALESCE(recipient_name, '[NULL]')
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 9. AWARD x YEAR PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. SNAP AWARD x FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    award_id_fain,
    award_id_uri,
    COALESCE(recipient_name, '[NULL]') AS recipient_name,
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
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE WHEN NOT is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS non_covid_amount
FROM etl174b_5s_snap
GROUP BY
    action_date_fiscal_year,
    award_id_fain,
    award_id_uri,
    COALESCE(recipient_name, '[NULL]')
ORDER BY
    action_date_fiscal_year,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 10. DESCRIPTION PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. SNAP TRANSACTION DESCRIPTION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(
        NULLIF(BTRIM(transaction_description), ''),
        '[BLANK]'
    ) AS transaction_description,
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
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE WHEN NOT is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS non_covid_amount
FROM etl174b_5s_snap
GROUP BY
    COALESCE(
        NULLIF(BTRIM(transaction_description), ''),
        '[BLANK]'
    )
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 11. SEMANTIC KEYWORD PROFILE
--
-- This is intentionally diagnostic. Keyword categories do NOT constitute
-- accounting classifications.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. SNAP DESCRIPTION KEYWORD PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

WITH classified AS (
    SELECT
        s.*,
        CASE
            WHEN UPPER(COALESCE(transaction_description, '')) LIKE '%P-EBT%'
              OR UPPER(COALESCE(transaction_description, '')) LIKE '%PEBT%'
              OR UPPER(COALESCE(transaction_description, '')) LIKE '%PANDEMIC EBT%'
              OR UPPER(COALESCE(transaction_description, '')) LIKE '%PANDEMIC ELECTRONIC BENEFIT%'
                THEN 'P_EBT_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) LIKE '%EMERGENCY ALLOT%'
                THEN 'EMERGENCY_ALLOTMENT_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) LIKE '%BENEFIT%'
                THEN 'BENEFIT_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) LIKE '%ADMIN%'
                THEN 'ADMINISTRATION_TEXT'

            ELSE 'OTHER_OR_UNSPECIFIED_TEXT'
        END AS semantic_bucket
    FROM etl174b_5s_snap s
)
SELECT
    semantic_bucket,
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
FROM classified
GROUP BY semantic_bucket
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 12. COMPLETE TRANSACTION INVENTORY
--
-- Only 59 rows are expected, so print the complete transaction population.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. COMPLETE SNAP TRANSACTION INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    assistance_transaction_id,
    award_id_fain,
    award_id_uri,
    recipient_name,
    federal_action_obligation,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,
    transaction_description
FROM etl174b_5s_snap
ORDER BY
    action_date_fiscal_year,
    COALESCE(award_id_fain, award_id_uri),
    assistance_transaction_id;


-- ================================================================================================
-- 13. EXISTING PROGRAM CLASSIFICATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING 10.551 PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '10.551'
ORDER BY methodology_version;


-- ================================================================================================
-- 14. EXISTING PROGRAM-POLICY MAPPING
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXISTING 10.551 PROGRAM-POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version AS mapping_methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.methodology_version AS policy_methodology_version
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '10.551'
ORDER BY m.methodology_version;


-- ================================================================================================
-- 15. EXISTING AWARD-SPECIFIC CLASSIFICATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EXISTING 10.551 AWARD-SPECIFIC CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '10.551'
ORDER BY
    source_award_identifier,
    methodology_version;


-- ================================================================================================
-- 16. POSSIBLY RELATED EXISTING SOURCE POLICIES
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. POSSIBLY RELATED EXISTING SOURCE POLICIES'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE
       UPPER(COALESCE(inflow_family, '')) LIKE '%SNAP%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%NUTRITION%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%FOOD%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%SNAP%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%NUTRITION%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%FOOD%'
    OR UPPER(COALESCE(accounting_measure, '')) LIKE '%SNAP%'
    OR UPPER(COALESCE(accounting_measure, '')) LIKE '%NUTRITION%'
    OR UPPER(COALESCE(preferred_source, '')) LIKE '%USDA%'
ORDER BY federal_inflow_source_policy_id;


-- ================================================================================================
-- 17. RELATED USDA NUTRITION PROGRAMS
--
-- Context only. This is NOT an accounting grouping.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. RELATED USDA NUTRITION ASSISTANCE PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
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
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND (
        cfda_number IN (
            '10.551',
            '10.555',
            '10.557',
            '10.561'
        )
        OR UPPER(COALESCE(cfda_title, '')) LIKE '%NUTRITION%'
        OR UPPER(COALESCE(cfda_title, '')) LIKE '%FOOD ASSISTANCE%'
        OR UPPER(COALESCE(cfda_title, '')) LIKE '%SCHOOL LUNCH%'
        OR UPPER(COALESCE(cfda_title, '')) LIKE '%SNAP%'
      )
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC NULLS LAST;


-- ================================================================================================
-- 18. MATERIALITY AGAINST CURRENT 5R RESIDUAL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. SNAP MATERIALITY RELATIVE TO 5R RESIDUAL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(SUM(federal_action_obligation), 2) AS snap_amount,

    94723025200.85::numeric AS current_5r_residual,

    ROUND(
        100.0 * SUM(federal_action_obligation)
        / 94723025200.85::numeric,
        4
    ) AS pct_of_5r_residual,

    ROUND(
        94723025200.85::numeric
        - SUM(federal_action_obligation),
        2
    ) AS hypothetical_residual_if_fully_resolved

FROM etl174b_5s_snap;


-- ================================================================================================
-- 19. COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5S PROFILE COMPLETE - SNAP 10.551 ACCOUNTING REVIEW - NO PERSISTENT DB WRITES';
END
$$;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5S COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'