/*
================================================================================
ETL-174B-5X-2
FULL FOUR-PROGRAM EDUCATION ASSISTANCE PROFILE
================================================================================

Purpose
-------
Complete the read-only evidence profile for four high-materiality Washington
FY2020-FY2024 education assistance programs:

    84.425  Education Stabilization Fund
    84.063  Federal Pell Grant Program
    84.010  Title I Grants to Local Educational Agencies
    84.027  Special Education Grants to States

Methodological correction from ETL-174B-5X / ETL-174B-5X-1
----------------------------------------------------------
Program identity determines the economic assistance function.

Funding agency is retained as provenance and does NOT restrict the focal
program population.

ETL-174B-5X-1 established that the full four-program population is:

    transactions        28,900
    programs                 4
    awards                1,316
    recipients              149
    obligation amount  $9,035,419,332.15
    COVID              $4,474,035,816.00
    IIJA                        $0.00
    extraordinary      $4,474,035,816.00

Funding-agency provenance:

    Department of Education    $8,953,191,721.52
    Department of the Interior    $82,227,610.63
                               ------------------
    Full population            $9,035,419,332.15

The Interior-administered portion consists of education assistance under
84.010, 84.027, and 84.425 and is retained in the full program population.

Objectives
----------
1. Reconstruct the current certified unresolved assistance universe.
2. Reproduce the full four-program controls from ETL-174B-5X-1.
3. Profile annual behavior.
4. Profile signs/deobligations.
5. Profile funding-agency provenance.
6. Profile COVID / extraordinary provenance.
7. Profile recipients and awards.
8. Profile transaction descriptions.
9. Inspect existing classifications and mappings.
10. Quantify materiality and hypothetical residual reduction.

READ ONLY.
NO PERSISTENT DATABASE WRITES.

================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5X-2 FULL FOUR-PROGRAM EDUCATION ASSISTANCE PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. MATERIALIZE CERTIFIED WA ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x2_ledger;

CREATE TEMP TABLE etl174b_5x2_ledger AS
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

CREATE INDEX ON etl174b_5x2_ledger (cfda_number);
CREATE INDEX ON etl174b_5x2_ledger (source_award_identifier);
CREATE INDEX ON etl174b_5x2_ledger (action_date_fiscal_year);


-- ================================================================================================
-- 2. RECONSTRUCT CURRENT EFFECTIVE ACCOUNTING DISPOSITION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x2_award_matches;

CREATE TEMP TABLE etl174b_5x2_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition,
    a.inflow_family,
    a.inflow_subfamily,
    a.methodology_version
FROM etl174b_5x2_ledger l
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


DROP TABLE IF EXISTS pg_temp.etl174b_5x2_program_matches;

CREATE TEMP TABLE etl174b_5x2_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition AS accounting_disposition,
    p.inflow_family,
    p.inflow_subfamily,
    m.methodology_version
FROM etl174b_5x2_ledger l
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
    v_award_duplicates   bigint;
    v_program_duplicates bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_award_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5x2_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    SELECT COUNT(*)
    INTO v_program_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5x2_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    IF v_award_duplicates <> 0 THEN
        RAISE EXCEPTION
            'ETL-174B-5X-2 FAILED: % transactions have multiple award classifications',
            v_award_duplicates;
    END IF;

    IF v_program_duplicates <> 0 THEN
        RAISE EXCEPTION
            'ETL-174B-5X-2 FAILED: % transactions have multiple program mappings',
            v_program_duplicates;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X-2 RESOLUTION UNIQUENESS PASS';
END
$$;


DROP TABLE IF EXISTS pg_temp.etl174b_5x2_resolved;

CREATE TEMP TABLE etl174b_5x2_resolved AS
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

FROM etl174b_5x2_ledger l
LEFT JOIN etl174b_5x2_award_matches a
  ON a.assistance_transaction_id = l.assistance_transaction_id
LEFT JOIN etl174b_5x2_program_matches p
  ON p.assistance_transaction_id = l.assistance_transaction_id;

CREATE INDEX ON etl174b_5x2_resolved (effective_accounting_disposition);
CREATE INDEX ON etl174b_5x2_resolved (cfda_number);


-- ================================================================================================
-- 3. CURRENT RESIDUAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. CURRENT ETL-174B-5W RESIDUAL CONTROL'
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
FROM etl174b_5x2_resolved
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
        COALESCE(SUM(CASE WHEN is_covid
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_iija
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_extraordinary
                          THEN federal_action_obligation ELSE 0 END), 0)
    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_total,
        v_covid,
        v_iija,
        v_extra
    FROM etl174b_5x2_resolved
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
            'ETL-174B-5X-2 RESIDUAL CONTROL FAILED: tx=% programs=% awards=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_awards,
            v_total,
            v_covid,
            v_iija,
            v_extra;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X-2 RESIDUAL CONTROL PASS: total=%',
        v_total;
END
$$;


-- ================================================================================================
-- 4. FULL FOUR-PROGRAM FOCAL UNIVERSE
--
-- IMPORTANT: no funding-agency restriction.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x2_focal;

CREATE TEMP TABLE etl174b_5x2_focal AS
SELECT *
FROM etl174b_5x2_resolved
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
  AND cfda_number IN (
      '84.425',
      '84.063',
      '84.010',
      '84.027'
  );


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FULL FOUR-PROGRAM FOCAL CONTROL'
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
FROM etl174b_5x2_focal;


DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_awards       bigint;
    v_recipients   bigint;
    v_total        numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COUNT(DISTINCT source_award_identifier),
        COUNT(DISTINCT recipient_name),
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
        v_awards,
        v_recipients,
        v_total,
        v_covid,
        v_iija,
        v_extra
    FROM etl174b_5x2_focal;

    IF v_transactions <> 28900
       OR v_programs <> 4
       OR v_awards <> 1316
       OR v_recipients <> 149
       OR ABS(v_total - 9035419332.15::numeric) > 0.01
       OR ABS(v_covid - 4474035816.00::numeric) > 0.01
       OR ABS(v_iija - 0::numeric) > 0.01
       OR ABS(v_extra - 4474035816.00::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5X-2 FOCAL CONTROL FAILED: tx=% programs=% awards=% recipients=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_awards,
            v_recipients,
            v_total,
            v_covid,
            v_iija,
            v_extra;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X-2 FOCAL CONTROL PASS: tx=% programs=% awards=% recipients=% total=%',
        v_transactions,
        v_programs,
        v_awards,
        v_recipients,
        v_total;
END
$$;


-- ================================================================================================
-- 5. PROGRAM SUMMARY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. FULL FOCAL PROGRAM SUMMARY'
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
FROM etl174b_5x2_focal
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 6. PROGRAM BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. FOCAL PROGRAMS BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    action_date_fiscal_year AS fiscal_year,
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
FROM etl174b_5x2_focal
GROUP BY
    cfda_number,
    action_date_fiscal_year
ORDER BY
    cfda_number,
    action_date_fiscal_year;


-- ================================================================================================
-- 7. TOTAL FOCAL POPULATION BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. TOTAL FOCAL POPULATION BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
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
FROM etl174b_5x2_focal
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 8. SIGN PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. FOCAL PROGRAM SIGN PROFILE'
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

FROM etl174b_5x2_focal
GROUP BY cfda_number
ORDER BY cfda_number;


-- ================================================================================================
-- 9. FUNDING-AGENCY PROVENANCE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. FUNDING-AGENCY PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]')
        AS funding_agency_name,
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
FROM etl174b_5x2_focal
GROUP BY
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]')
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 10. FUNDING PROVENANCE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. COVID / IIJA / EXTRAORDINARY FUNDING PROVENANCE'
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
FROM etl174b_5x2_focal
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
-- 11. RECIPIENT CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP 25 RECIPIENTS BY PROGRAM'
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

    FROM etl174b_5x2_focal
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
-- 12. AWARD CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. TOP 25 AWARDS BY PROGRAM'
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

    FROM etl174b_5x2_focal
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
-- 13. DESCRIPTION PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. MOST MATERIAL TRANSACTION DESCRIPTIONS'
\echo '----------------------------------------------------------------------------------------------------'

WITH description_totals AS (
    SELECT
        cfda_number,

        COALESCE(
            NULLIF(BTRIM(transaction_description), ''),
            '[NULL]'
        ) AS transaction_description,

        COUNT(*) AS transaction_count,

        SUM(federal_action_obligation)::numeric
            AS obligation_amount,

        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY
                ABS(SUM(federal_action_obligation)) DESC,
                COALESCE(
                    NULLIF(BTRIM(transaction_description), ''),
                    '[NULL]'
                )
        ) AS description_rank

    FROM etl174b_5x2_focal

    GROUP BY
        cfda_number,
        COALESCE(
            NULLIF(BTRIM(transaction_description), ''),
            '[NULL]'
        )
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
\echo '12. EXISTING PROGRAM CLASSIFICATIONS'
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
\echo '13. EXISTING AWARD CLASSIFICATIONS'
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
\echo '14. EXISTING PROGRAM-POLICY MAPPINGS'
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
-- 17. MATERIALITY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. FOCAL MATERIALITY'
\echo '----------------------------------------------------------------------------------------------------'

WITH controls AS (
    SELECT
        (
            SELECT SUM(federal_action_obligation)::numeric
            FROM etl174b_5x2_focal
        ) AS focal_total,

        (
            SELECT SUM(federal_action_obligation)::numeric
            FROM etl174b_5x2_resolved
            WHERE effective_accounting_disposition =
                  'UNCLASSIFIED_REVIEW'
        ) AS residual_total
)
SELECT
    ROUND(focal_total, 2) AS focal_total,
    ROUND(residual_total, 2) AS residual_total,

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
-- 18. FUNDING-AGENCY RECONCILIATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FUNDING-AGENCY RECONCILIATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH x AS (
    SELECT
        SUM(federal_action_obligation)::numeric
            AS full_total,

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name =
                      'Department of Education'
            ),
            0
        )::numeric AS education_agency_total,

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name =
                      'Department of the Interior'
            ),
            0
        )::numeric AS interior_agency_total,

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name NOT IN (
                    'Department of Education',
                    'Department of the Interior'
                )
                   OR funding_agency_name IS NULL
            ),
            0
        )::numeric AS other_agency_total

    FROM etl174b_5x2_focal
)
SELECT
    ROUND(full_total, 2)
        AS full_total,

    ROUND(education_agency_total, 2)
        AS education_agency_total,

    ROUND(interior_agency_total, 2)
        AS interior_agency_total,

    ROUND(other_agency_total, 2)
        AS other_agency_total,

    ROUND(
        full_total
        - education_agency_total
        - interior_agency_total
        - other_agency_total,
        2
    ) AS closure

FROM x;


-- ================================================================================================
-- 19. FINAL CERTIFICATION
-- ================================================================================================

DO $$
DECLARE
    v_transactions bigint;
    v_programs     bigint;
    v_awards       bigint;
    v_recipients   bigint;
    v_total        numeric;
    v_covid        numeric;
    v_iija         numeric;
    v_extra        numeric;
    v_ed           numeric;
    v_interior     numeric;
    v_other        numeric;
    v_closure      numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COUNT(DISTINCT source_award_identifier),
        COUNT(DISTINCT recipient_name),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(SUM(CASE WHEN is_covid
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_iija
                          THEN federal_action_obligation ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN is_extraordinary
                          THEN federal_action_obligation ELSE 0 END), 0),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name =
                      'Department of Education'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name =
                      'Department of the Interior'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name NOT IN (
                    'Department of Education',
                    'Department of the Interior'
                )
                   OR funding_agency_name IS NULL
            ),
            0
        )

    INTO
        v_transactions,
        v_programs,
        v_awards,
        v_recipients,
        v_total,
        v_covid,
        v_iija,
        v_extra,
        v_ed,
        v_interior,
        v_other

    FROM etl174b_5x2_focal;

    v_closure := v_total - v_ed - v_interior - v_other;

    IF v_transactions <> 28900
       OR v_programs <> 4
       OR v_awards <> 1316
       OR v_recipients <> 149
       OR ABS(v_total - 9035419332.15::numeric) > 0.01
       OR ABS(v_covid - 4474035816.00::numeric) > 0.01
       OR ABS(v_iija - 0::numeric) > 0.01
       OR ABS(v_extra - 4474035816.00::numeric) > 0.01
       OR ABS(v_ed - 8953191721.52::numeric) > 0.01
       OR ABS(v_interior - 82227610.63::numeric) > 0.01
       OR ABS(v_other) > 0.01
       OR ABS(v_closure) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5X-2 FINAL CONTROL FAILED: tx=% programs=% awards=% recipients=% total=% COVID=% IIJA=% extraordinary=% Education=% Interior=% other=% closure=%',
            v_transactions,
            v_programs,
            v_awards,
            v_recipients,
            v_total,
            v_covid,
            v_iija,
            v_extra,
            v_ed,
            v_interior,
            v_other,
            v_closure;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X-2 PASS - full four-program education population profiled: tx=% awards=% recipients=% total=% COVID=%; Education-funded=% Interior-funded=% closure=%; NO PERSISTENT DB WRITES',
        v_transactions,
        v_awards,
        v_recipients,
        v_total,
        v_covid,
        v_ed,
        v_interior,
        v_closure;
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5X-2 COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'