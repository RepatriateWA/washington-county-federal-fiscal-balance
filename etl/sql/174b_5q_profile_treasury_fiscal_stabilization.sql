/*
================================================================================
ETL-174B-5Q
Treasury State / Local Fiscal Stabilization Assistance Profile
================================================================================

Purpose
-------
Build a read-only evidence profile for three high-materiality Treasury
assistance programs remaining in ETL-174B-5P UNCLASSIFIED_REVIEW:

    21.019  Coronavirus Relief Fund
    21.023  Emergency Rental Assistance Program
    21.027  Coronavirus State and Local Fiscal Recovery Funds

Questions
---------
1. Reproduce the ETL-174B-5P control exactly.
2. Establish annual obligation timing.
3. Identify recipients and recipient concentration.
4. Identify awards and award concentration.
5. Inspect transaction descriptions and funding provenance.
6. Determine whether negative/deobligation activity is material.
7. Search existing WCFFBP policy/mapping architecture for possible overlap.
8. Search existing certified assistance for closely related Treasury programs.

IMPORTANT
---------
This script does NOT decide whether these programs are additive.

No accounting classification is persisted.
No DB writes are authorized.
================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5Q TREASURY STATE / LOCAL FISCAL STABILIZATION PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. BUILD TARGET UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5q_target;

CREATE TEMP TABLE etl174b_5q_target AS
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
  AND l.cfda_number IN (
      '21.019',
      '21.023',
      '21.027'
  );


-- ================================================================================================
-- 2. HARD 5P CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. ETL-174B-5P TREASURY FAMILY CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount
FROM etl174b_5q_target;


DO $$
DECLARE
    v_programs bigint;
    v_total numeric;
BEGIN
    SELECT
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO
        v_programs,
        v_total
    FROM etl174b_5q_target;

    IF v_programs <> 3 THEN
        RAISE EXCEPTION
            '5Q CONTROL FAILED: expected 3 programs, found %',
            v_programs;
    END IF;

    IF ABS(v_total - 12561260982.36::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5Q CONTROL FAILED: expected %, found %',
            12561260982.36,
            v_total;
    END IF;

    RAISE NOTICE
        '5Q 5P-CONTROL PASS: programs=3 total=%',
        v_total;
END
$$;


-- ================================================================================================
-- 3. PROGRAM CONTROLS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. PROGRAM CONTROLS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount
FROM etl174b_5q_target
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 4. ANNUAL PROGRAM PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. ANNUAL PROGRAM PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_amount
FROM etl174b_5q_target
GROUP BY
    action_date_fiscal_year,
    cfda_number
ORDER BY
    action_date_fiscal_year,
    cfda_number;


-- ================================================================================================
-- 5. FUNDING PROVENANCE COMBINATIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FUNDING PROVENANCE COMBINATIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount
FROM etl174b_5q_target
GROUP BY
    cfda_number,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 6. POSITIVE / NEGATIVE / ZERO TRANSACTIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. TRANSACTION SIGN PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    COUNT(*) FILTER (
        WHERE federal_action_obligation > 0
    ) AS positive_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (
                    WHERE federal_action_obligation > 0
                ),
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
                FILTER (
                    WHERE federal_action_obligation < 0
                ),
            0
        ),
        2
    ) AS negative_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions,

    ROUND(SUM(federal_action_obligation), 2) AS net_obligations

FROM etl174b_5q_target
GROUP BY cfda_number
ORDER BY cfda_number;


-- ================================================================================================
-- 7. RECIPIENT CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. TOP RECIPIENTS BY PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH recipient_totals AS (
    SELECT
        cfda_number,
        recipient_name,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
        SUM(federal_action_obligation) AS obligation_amount
    FROM etl174b_5q_target
    GROUP BY
        cfda_number,
        recipient_name
),
ranked AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY obligation_amount DESC NULLS LAST, recipient_name
        ) AS recipient_rank,

        SUM(obligation_amount) OVER (
            PARTITION BY cfda_number
        ) AS program_total

    FROM recipient_totals r
)
SELECT
    cfda_number,
    recipient_rank,
    recipient_name,
    transaction_count,
    award_count,
    ROUND(obligation_amount, 2) AS obligation_amount,
    ROUND(
        100.0 * obligation_amount
        / NULLIF(program_total, 0),
        4
    ) AS pct_of_program
FROM ranked
WHERE recipient_rank <= 25
ORDER BY
    cfda_number,
    recipient_rank;


-- ================================================================================================
-- 8. AWARD CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. TOP AWARDS BY PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH award_totals AS (
    SELECT
        cfda_number,
        award_id_fain,
        award_id_uri,
        recipient_name,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS obligation_amount,

        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS covid_amount

    FROM etl174b_5q_target
    GROUP BY
        cfda_number,
        award_id_fain,
        award_id_uri,
        recipient_name
),
ranked AS (
    SELECT
        a.*,
        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY obligation_amount DESC NULLS LAST,
                     COALESCE(award_id_fain, award_id_uri)
        ) AS award_rank,

        SUM(obligation_amount) OVER (
            PARTITION BY cfda_number
        ) AS program_total

    FROM award_totals a
)
SELECT
    cfda_number,
    award_rank,
    award_id_fain,
    award_id_uri,
    recipient_name,
    transaction_count,
    ROUND(obligation_amount, 2) AS obligation_amount,
    ROUND(covid_amount, 2) AS covid_amount,
    ROUND(
        100.0 * obligation_amount
        / NULLIF(program_total, 0),
        4
    ) AS pct_of_program
FROM ranked
WHERE award_rank <= 50
ORDER BY
    cfda_number,
    award_rank;


-- ================================================================================================
-- 9. TRANSACTION DESCRIPTION PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TRANSACTION DESCRIPTION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    COALESCE(NULLIF(BTRIM(transaction_description), ''), '[BLANK]') AS transaction_description,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount
FROM etl174b_5q_target
GROUP BY
    cfda_number,
    COALESCE(NULLIF(BTRIM(transaction_description), ''), '[BLANK]')
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 10. LARGEST INDIVIDUAL TRANSACTIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP 75 INDIVIDUAL TRANSACTIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    award_id_fain,
    award_id_uri,
    recipient_name,
    federal_action_obligation,
    defc_codes,
    is_covid,
    is_extraordinary,
    transaction_description
FROM etl174b_5q_target
ORDER BY
    ABS(federal_action_obligation) DESC,
    cfda_number
LIMIT 75;


-- ================================================================================================
-- 11. EXISTING PROGRAM CLASSIFICATIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. EXISTING PROGRAM CLASSIFICATIONS'
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
  AND source_program_code IN (
      '21.019',
      '21.023',
      '21.027'
  )
ORDER BY
    source_program_code,
    methodology_version;


-- ================================================================================================
-- 12. EXISTING PROGRAM-POLICY MAPPINGS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. EXISTING PROGRAM-POLICY MAPPINGS'
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
  AND m.source_program_code IN (
      '21.019',
      '21.023',
      '21.027'
  )
ORDER BY
    m.source_program_code,
    m.methodology_version;


-- ================================================================================================
-- 13. EXISTING AWARD-SPECIFIC CLASSIFICATIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING AWARD-SPECIFIC CLASSIFICATIONS'
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
  AND source_program_code IN (
      '21.019',
      '21.023',
      '21.027'
  )
ORDER BY
    source_program_code,
    source_award_identifier,
    methodology_version;


-- ================================================================================================
-- 14. SEARCH SOURCE POLICIES FOR POSSIBLE TREASURY / COVID / RENTAL / FISCAL OVERLAP
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. POSSIBLY RELEVANT EXISTING SOURCE POLICIES'
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
       UPPER(COALESCE(inflow_family, '')) LIKE '%TREASUR%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%COVID%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%RENT%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%FISCAL%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%TREASUR%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%COVID%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%RENT%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%FISCAL%'
    OR UPPER(COALESCE(accounting_measure, '')) LIKE '%TREASUR%'
    OR UPPER(COALESCE(accounting_measure, '')) LIKE '%COVID%'
    OR UPPER(COALESCE(accounting_measure, '')) LIKE '%RENT%'
    OR UPPER(COALESCE(accounting_measure, '')) LIKE '%FISCAL%'
    OR UPPER(COALESCE(preferred_source, '')) LIKE '%TREASUR%'
ORDER BY federal_inflow_source_policy_id;


-- ================================================================================================
-- 15. OTHER TREASURY ASSISTANCE PROGRAMS IN THE CERTIFIED LEDGER
--
-- This is contextual only. It helps distinguish the three target programs
-- from other Treasury assistance present in Washington.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. OTHER TREASURY ASSISTANCE PROGRAMS IN FY2020-FY2024'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_amount,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
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
        funding_agency_name = 'Department of the Treasury'
        OR cfda_number LIKE '21.%'
      )
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC NULLS LAST;


-- ================================================================================================
-- 16. TARGET SHARE OF 5O RESIDUAL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. MATERIALITY RELATIVE TO 5O RESIDUAL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(SUM(federal_action_obligation), 2) AS target_amount,

    ROUND(
        100.0 * SUM(federal_action_obligation)
        / 107284286183.21::numeric,
        4
    ) AS pct_of_5o_unclassified_residual,

    ROUND(
        107284286183.21::numeric
        - SUM(federal_action_obligation),
        2
    ) AS hypothetical_residual_if_fully_resolved

FROM etl174b_5q_target;


-- ================================================================================================
-- 17. COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5Q PROFILE COMPLETE - TREASURY FISCAL STABILIZATION - NO DB WRITES';
END
$$;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5Q COMPLETE'
\echo '===================================================================================================='
\echo 'NO DATABASE WRITES'