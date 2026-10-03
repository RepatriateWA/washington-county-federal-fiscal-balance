/*
================================================================================
ETL-174B-5X
PROFILE EDUCATION ASSISTANCE FAMILY
================================================================================

Purpose
-------
Profile the unresolved Department of Education portion of the certified
Washington FY2020-FY2024 USAspending assistance universe after ETL-174B-5W.

Primary focal programs
----------------------
84.425  Education Stabilization Fund
84.063  Federal Pell Grant Program
84.010  Title I Grants to Local Educational Agencies
84.027  Special Education Grants to States

Objectives
----------
1. Reproduce the certified ETL-174B-5W residual.
2. Profile the complete unresolved Department of Education population.
3. Profile the four focal programs by:
      - fiscal year
      - program
      - sign
      - recipient
      - award
      - funding provenance
      - descriptions
4. Inspect existing classifications and policy mappings.
5. Establish exact controls for a later accounting-policy decision.

READ ONLY.
NO PERSISTENT DATABASE WRITES.

Certified ETL-174B-5W controls
------------------------------
Remaining UNCLASSIFIED_REVIEW:
    transactions       852,648
    programs             1,279
    awards             671,888
    obligation amount  $70,539,463,376.71
    COVID              $20,538,493,522.27
    IIJA                 $3,797,323,322.93
    extraordinary      $25,809,436,041.04

Department of Education unresolved:
    transactions        39,636
    programs                72
    awards               4,654
    obligation amount  $11,419,755,831.98
    COVID               $4,450,501,531.87
    IIJA                         $0.00
    extraordinary       $4,506,911,955.87

Four focal programs expected:
84.425  $4,400,028,954.00
84.063  $1,812,084,197.25
84.010  $1,472,272,408.06
84.027  $1,351,033,772.84

Four-program expected total:
         $9,035,419,332.15

================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5X PROFILE EDUCATION ASSISTANCE FAMILY'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. MATERIALIZE CERTIFIED WA ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x_ledger;

CREATE TEMP TABLE etl174b_5x_ledger AS
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

CREATE INDEX ON etl174b_5x_ledger (cfda_number);
CREATE INDEX ON etl174b_5x_ledger (source_award_identifier);
CREATE INDEX ON etl174b_5x_ledger (action_date_fiscal_year);


-- ================================================================================================
-- 2. RECONSTRUCT CURRENT EFFECTIVE ACCOUNTING DISPOSITION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x_award_matches;

CREATE TEMP TABLE etl174b_5x_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition,
    a.inflow_family,
    a.inflow_subfamily,
    a.methodology_version
FROM etl174b_5x_ledger l
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


DROP TABLE IF EXISTS pg_temp.etl174b_5x_program_matches;

CREATE TEMP TABLE etl174b_5x_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition AS accounting_disposition,
    p.inflow_family,
    p.inflow_subfamily,
    m.methodology_version
FROM etl174b_5x_ledger l
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


-- Fail closed if current persisted policy is ambiguous.

DO $$
DECLARE
    v_award_duplicates   bigint;
    v_program_duplicates bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_award_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5x_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    SELECT COUNT(*)
    INTO v_program_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5x_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    IF v_award_duplicates <> 0 THEN
        RAISE EXCEPTION
            'ETL-174B-5X FAILED: % transactions have multiple award classifications',
            v_award_duplicates;
    END IF;

    IF v_program_duplicates <> 0 THEN
        RAISE EXCEPTION
            'ETL-174B-5X FAILED: % transactions have multiple program mappings',
            v_program_duplicates;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X RESOLUTION UNIQUENESS PASS';
END
$$;


DROP TABLE IF EXISTS pg_temp.etl174b_5x_resolved;

CREATE TEMP TABLE etl174b_5x_resolved AS
SELECT
    l.*,

    CASE
        WHEN a.assistance_transaction_id IS NOT NULL THEN 'AWARD'
        WHEN p.assistance_transaction_id IS NOT NULL THEN 'PROGRAM'
        ELSE 'UNCLASSIFIED'
    END AS resolution_level,

    COALESCE(
        a.accounting_disposition,
        p.accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_accounting_disposition

FROM etl174b_5x_ledger l
LEFT JOIN etl174b_5x_award_matches a
  ON a.assistance_transaction_id = l.assistance_transaction_id
LEFT JOIN etl174b_5x_program_matches p
  ON p.assistance_transaction_id = l.assistance_transaction_id;


CREATE INDEX ON etl174b_5x_resolved (effective_accounting_disposition);
CREATE INDEX ON etl174b_5x_resolved (funding_agency_name);
CREATE INDEX ON etl174b_5x_resolved (cfda_number);


-- ================================================================================================
-- 3. ETL-174B-5W RESIDUAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. ETL-174B-5W RESIDUAL CONTROL'
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
FROM etl174b_5x_resolved
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW';


DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_awards       bigint;
    v_total        numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COUNT(DISTINCT source_award_identifier),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(CASE WHEN is_covid
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_iija
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_extraordinary
                     THEN federal_action_obligation ELSE 0 END),
            0
        )
    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extra
    FROM etl174b_5x_resolved
    WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW';

    IF v_transactions <> 852648
       OR v_programs <> 1279
       OR v_awards <> 671888
       OR ABS(v_total - 70539463376.71::numeric) > 0.01
       OR ABS(v_covid - 20538493522.27::numeric) > 0.01
       OR ABS(v_iija - 3797323322.93::numeric) > 0.01
       OR ABS(v_extra - 25809436041.04::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5X 5W CONTROL FAILED: tx=% programs=% awards=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_awards,
            v_total,
            v_covid,
            v_iija,
            v_extra;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X 5W RESIDUAL CONTROL PASS: total=%',
        v_total;
END
$$;


-- ================================================================================================
-- 4. COMPLETE DEPARTMENT OF EDUCATION RESIDUAL
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x_education;

CREATE TEMP TABLE etl174b_5x_education AS
SELECT *
FROM etl174b_5x_resolved
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
  AND funding_agency_name = 'Department of Education';


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. COMPLETE DEPARTMENT OF EDUCATION RESIDUAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
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
FROM etl174b_5x_education;


DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_awards       bigint;
    v_total        numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COUNT(DISTINCT source_award_identifier),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(
            SUM(CASE WHEN is_covid
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_iija
                     THEN federal_action_obligation ELSE 0 END),
            0
        ),
        COALESCE(
            SUM(CASE WHEN is_extraordinary
                     THEN federal_action_obligation ELSE 0 END),
            0
        )
    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extra
    FROM etl174b_5x_education;

    IF v_transactions <> 39636
       OR v_programs <> 72
       OR v_awards <> 4654
       OR ABS(v_total - 11419755831.98::numeric) > 0.01
       OR ABS(v_covid - 4450501531.87::numeric) > 0.01
       OR ABS(v_iija - 0::numeric) > 0.01
       OR ABS(v_extra - 4506911955.87::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5X EDUCATION CONTROL FAILED: tx=% programs=% awards=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_awards,
            v_total,
            v_covid,
            v_iija,
            v_extra;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X EDUCATION CONTROL PASS: tx=% programs=% awards=% total=%',
        v_transactions,
        v_programs,
        v_awards,
        v_total;
END
$$;


-- ================================================================================================
-- 5. COMPLETE EDUCATION PROGRAM INVENTORY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. COMPLETE UNRESOLVED DEPARTMENT OF EDUCATION PROGRAM INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
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
FROM etl174b_5x_education
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC, cfda_number;


-- ================================================================================================
-- 6. FOUR-PROGRAM FOCAL UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x_focal;

CREATE TEMP TABLE etl174b_5x_focal AS
SELECT *
FROM etl174b_5x_education
WHERE cfda_number IN (
    '84.425',
    '84.063',
    '84.010',
    '84.027'
);


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FOUR-PROGRAM FOCAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
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
FROM etl174b_5x_focal;


DO $$
DECLARE
    v_programs bigint;
    v_total    numeric;
BEGIN
    SELECT
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO
        v_programs,
        v_total
    FROM etl174b_5x_focal;

    IF v_programs <> 4
       OR ABS(v_total - 9035419332.15::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5X FOCAL CONTROL FAILED: programs=% total=%',
            v_programs,
            v_total;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X FOCAL CONTROL PASS: programs=% total=%',
        v_programs,
        v_total;
END
$$;


-- ================================================================================================
-- 7. FOCAL PROGRAM SUMMARY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. FOCAL PROGRAM SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
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
FROM etl174b_5x_focal
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 8. FOCAL PROGRAMS BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. FOCAL PROGRAMS BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    action_date_fiscal_year AS fiscal_year,
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
FROM etl174b_5x_focal
GROUP BY
    cfda_number,
    action_date_fiscal_year
ORDER BY
    cfda_number,
    action_date_fiscal_year;


-- ================================================================================================
-- 9. SIGN PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. FOCAL PROGRAM SIGN PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,

    COUNT(*) FILTER (
        WHERE federal_action_obligation > 0
    ) AS positive_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (WHERE federal_action_obligation > 0),
            0
        )::numeric,
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
        )::numeric,
        2
    ) AS negative_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations

FROM etl174b_5x_focal
GROUP BY cfda_number
ORDER BY cfda_number;


-- ================================================================================================
-- 10. FUNDING PROVENANCE PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. FOCAL PROGRAM FUNDING PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount
FROM etl174b_5x_focal
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
-- 11. TOP RECIPIENTS BY PROGRAM
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP RECIPIENTS BY FOCAL PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH recipient_totals AS (
    SELECT
        cfda_number,
        recipient_name,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT source_award_identifier) AS award_count,
        SUM(federal_action_obligation)::numeric
            AS obligation_amount,

        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY
                SUM(federal_action_obligation) DESC,
                recipient_name
        ) AS recipient_rank

    FROM etl174b_5x_focal
    GROUP BY
        cfda_number,
        recipient_name
)
SELECT
    cfda_number,
    recipient_rank,
    recipient_name,
    transaction_count,
    award_count,
    ROUND(obligation_amount, 2) AS obligation_amount
FROM recipient_totals
WHERE recipient_rank <= 25
ORDER BY
    cfda_number,
    recipient_rank;


-- ================================================================================================
-- 12. TOP AWARDS BY PROGRAM
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. TOP AWARDS BY FOCAL PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH award_totals AS (
    SELECT
        cfda_number,
        source_award_identifier,
        MAX(recipient_name) AS recipient_name,
        COUNT(*) AS transaction_count,
        MIN(action_date_fiscal_year) AS first_fiscal_year,
        MAX(action_date_fiscal_year) AS last_fiscal_year,
        SUM(federal_action_obligation)::numeric
            AS obligation_amount,

        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY
                SUM(federal_action_obligation) DESC,
                source_award_identifier
        ) AS award_rank

    FROM etl174b_5x_focal
    GROUP BY
        cfda_number,
        source_award_identifier
)
SELECT
    cfda_number,
    award_rank,
    source_award_identifier,
    recipient_name,
    transaction_count,
    first_fiscal_year,
    last_fiscal_year,
    ROUND(obligation_amount, 2) AS obligation_amount
FROM award_totals
WHERE award_rank <= 25
ORDER BY
    cfda_number,
    award_rank;


-- ================================================================================================
-- 13. TRANSACTION DESCRIPTION PROFILE
--
-- Useful for detecting materially different activities hiding inside a broad
-- assistance listing.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. MOST MATERIAL TRANSACTION DESCRIPTIONS'
\echo '----------------------------------------------------------------------------------------------------'

WITH description_totals AS (
    SELECT
        cfda_number,
        COALESCE(NULLIF(BTRIM(transaction_description), ''), '[NULL]')
            AS transaction_description,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation)::numeric
            AS obligation_amount,

        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY
                ABS(SUM(federal_action_obligation)) DESC,
                COALESCE(NULLIF(BTRIM(transaction_description), ''), '[NULL]')
        ) AS description_rank

    FROM etl174b_5x_focal
    GROUP BY
        cfda_number,
        COALESCE(NULLIF(BTRIM(transaction_description), ''), '[NULL]')
)
SELECT
    cfda_number,
    description_rank,
    transaction_description,
    transaction_count,
    ROUND(obligation_amount, 2) AS obligation_amount
FROM description_totals
WHERE description_rank <= 30
ORDER BY
    cfda_number,
    description_rank;


-- ================================================================================================
-- 14. EXISTING PROGRAM CLASSIFICATIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING PROGRAM CLASSIFICATIONS TOUCHING FOCAL PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN (
      '84.425',
      '84.063',
      '84.010',
      '84.027'
  )
ORDER BY
    source_program_code,
    methodology_version;


-- ================================================================================================
-- 15. EXISTING AWARD CLASSIFICATIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXISTING AWARD CLASSIFICATIONS TOUCHING FOCAL PROGRAMS'
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
      '84.425',
      '84.063',
      '84.010',
      '84.027'
  )
ORDER BY
    source_program_code,
    source_award_identifier,
    methodology_version;


-- ================================================================================================
-- 16. EXISTING PROGRAM-POLICY MAPPINGS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EXISTING PROGRAM MAPPINGS TOUCHING FOCAL PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN (
      '84.425',
      '84.063',
      '84.010',
      '84.027'
  )
ORDER BY
    m.source_program_code,
    m.methodology_version;


-- ================================================================================================
-- 17. FOCAL SHARE OF EDUCATION AND GLOBAL RESIDUAL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. FOCAL MATERIALITY'
\echo '----------------------------------------------------------------------------------------------------'

WITH controls AS (
    SELECT
        (
            SELECT SUM(federal_action_obligation)::numeric
            FROM etl174b_5x_focal
        ) AS focal_total,

        (
            SELECT SUM(federal_action_obligation)::numeric
            FROM etl174b_5x_education
        ) AS education_total,

        (
            SELECT SUM(federal_action_obligation)::numeric
            FROM etl174b_5x_resolved
            WHERE effective_accounting_disposition =
                  'UNCLASSIFIED_REVIEW'
        ) AS residual_total
)
SELECT
    ROUND(focal_total, 2) AS focal_total,
    ROUND(education_total, 2) AS education_total,
    ROUND(residual_total, 2) AS residual_total,

    ROUND(
        100.0 * focal_total /
        NULLIF(education_total, 0),
        4
    ) AS focal_pct_of_education,

    ROUND(
        100.0 * focal_total /
        NULLIF(residual_total, 0),
        4
    ) AS focal_pct_of_residual,

    ROUND(
        residual_total - focal_total,
        2
    ) AS hypothetical_residual_if_fully_resolved
FROM controls;


-- ================================================================================================
-- 18. FINAL READ-ONLY CERTIFICATION
-- ================================================================================================

DO $$
DECLARE
    v_focal_total numeric;
    v_education_total numeric;
BEGIN
    SELECT COALESCE(SUM(federal_action_obligation), 0)
    INTO v_focal_total
    FROM etl174b_5x_focal;

    SELECT COALESCE(SUM(federal_action_obligation), 0)
    INTO v_education_total
    FROM etl174b_5x_education;

    IF ABS(v_focal_total - 9035419332.15::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5X FINAL FOCAL CONTROL FAILED: expected 9035419332.15; found %',
            v_focal_total;
    END IF;

    IF ABS(v_education_total - 11419755831.98::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5X FINAL EDUCATION CONTROL FAILED: expected 11419755831.98; found %',
            v_education_total;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X PASS - Department of Education residual and four-program focal universe profiled; focal total=%; NO PERSISTENT DB WRITES',
        v_focal_total;
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5X COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'