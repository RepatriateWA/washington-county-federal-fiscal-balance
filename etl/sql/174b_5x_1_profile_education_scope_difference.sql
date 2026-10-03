/*
================================================================================
ETL-174B-5X-1
EDUCATION FOUR-PROGRAM SCOPE-DIFFERENCE PROFILE
================================================================================

Purpose
-------
Explain the difference between:

    full WA FY2020-FY2024 unresolved population for:
        84.425
        84.063
        84.010
        84.027

and:

    the subset where funding_agency_name = 'Department of Education'

ETL-174B-5X observed Department-of-Education-funded focal total:
    $8,953,191,721.52

Prior full-program expectation:
    $9,035,419,332.15

Expected difference:
       $82,227,610.63

READ ONLY.
NO PERSISTENT DATABASE WRITES.
================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5X-1 EDUCATION FOUR-PROGRAM SCOPE-DIFFERENCE PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. BUILD FULL FOUR-PROGRAM UNIVERSE
--
-- Deliberately NO funding-agency restriction.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x1_full;

CREATE TEMP TABLE etl174b_5x1_full AS
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
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number IN (
        '84.425',
        '84.063',
        '84.010',
        '84.027'
  );


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. FULL FOUR-PROGRAM CONTROL - NO FUNDING-AGENCY RESTRICTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM etl174b_5x1_full;


-- ================================================================================================
-- 2. FUNDING-AGENCY SPLIT
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FOUR-PROGRAM FUNDING-AGENCY SPLIT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(funding_agency_name, '[NULL]')
        AS funding_agency_name,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS program_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    COUNT(DISTINCT recipient_name)
        AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM etl174b_5x1_full

GROUP BY
    COALESCE(funding_agency_name, '[NULL]')

ORDER BY
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 3. NON-DEPARTMENT-OF-EDUCATION DIFFERENCE CONTROL
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5x1_difference;

CREATE TEMP TABLE etl174b_5x1_difference AS
SELECT *
FROM etl174b_5x1_full
WHERE funding_agency_name IS DISTINCT FROM 'Department of Education';


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. NON-DEPARTMENT-OF-EDUCATION DIFFERENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM etl174b_5x1_difference;


-- ================================================================================================
-- 4. DIFFERENCE BY PROGRAM AND FUNDING AGENCY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. DIFFERENCE BY PROGRAM AND FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,

    COALESCE(funding_agency_name, '[NULL]')
        AS funding_agency_name,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    COUNT(DISTINCT recipient_name)
        AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM etl174b_5x1_difference

GROUP BY
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]')

ORDER BY
    SUM(federal_action_obligation) DESC,
    cfda_number;


-- ================================================================================================
-- 5. FULL PROGRAM CONTROLS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. FULL PROGRAM CONTROLS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    COUNT(DISTINCT recipient_name)
        AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM etl174b_5x1_full

GROUP BY cfda_number

ORDER BY
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 6. DIFFERENCE BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. DIFFERENCE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS program_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS iija_amount

FROM etl174b_5x1_difference

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 7. DIFFERENCE SIGN PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. DIFFERENCE SIGN PROFILE'
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

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligations

FROM etl174b_5x1_difference

GROUP BY cfda_number

ORDER BY cfda_number;


-- ================================================================================================
-- 8. DIFFERENCE RECIPIENT PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. DIFFERENCE RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    recipient_name,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM etl174b_5x1_difference

GROUP BY
    cfda_number,
    recipient_name

ORDER BY
    SUM(federal_action_obligation) DESC,
    cfda_number,
    recipient_name;


-- ================================================================================================
-- 9. DIFFERENCE AWARD PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. DIFFERENCE AWARD PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    source_award_identifier,

    MAX(recipient_name)
        AS recipient_name,

    MAX(funding_agency_name)
        AS funding_agency_name,

    COUNT(*) AS transaction_count,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM etl174b_5x1_difference

GROUP BY
    cfda_number,
    source_award_identifier

ORDER BY
    SUM(federal_action_obligation) DESC,
    cfda_number,
    source_award_identifier;


-- ================================================================================================
-- 10. DIFFERENCE FUNDING PROVENANCE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. DIFFERENCE FUNDING PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM etl174b_5x1_difference

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
-- 11. DIFFERENCE TRANSACTION DESCRIPTIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. DIFFERENCE TRANSACTION DESCRIPTION PROFILE'
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
            AS obligation_amount

    FROM etl174b_5x1_difference

    GROUP BY
        cfda_number,
        COALESCE(
            NULLIF(BTRIM(transaction_description), ''),
            '[NULL]'
        )
)
SELECT
    cfda_number,
    transaction_description,
    transaction_count,
    ROUND(obligation_amount, 2)
        AS obligation_amount

FROM description_totals

ORDER BY
    ABS(obligation_amount) DESC,
    cfda_number,
    transaction_description;


-- ================================================================================================
-- 12. EXISTING AWARD CLASSIFICATIONS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING AWARD CLASSIFICATIONS TOUCHING DIFFERENCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    a.source_program_code,
    a.source_award_identifier,
    a.inflow_family,
    a.inflow_subfamily,
    a.accounting_disposition,
    a.classification_basis,
    a.methodology_version,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year

FROM reference.federal_inflow_award_classification a

JOIN (
    SELECT DISTINCT
        cfda_number,
        source_award_identifier
    FROM etl174b_5x1_difference
) d
  ON d.cfda_number = a.source_program_code
 AND d.source_award_identifier =
     a.source_award_identifier

WHERE a.source_system = 'USASPENDING_ASSISTANCE'

ORDER BY
    a.source_program_code,
    a.source_award_identifier,
    a.methodology_version;


-- ================================================================================================
-- 13. EXISTING PROGRAM MAPPINGS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. EXISTING PROGRAM MAPPINGS TOUCHING FOUR FOCAL PROGRAMS'
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
-- 14. ARITHMETIC RECONCILIATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. FULL VS DEPARTMENT-OF-EDUCATION-FUNDED RECONCILIATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH x AS (
    SELECT
        SUM(federal_action_obligation)::numeric
            AS full_total,

        SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name =
                      'Department of Education'
            )::numeric
            AS education_agency_total,

        SUM(federal_action_obligation)
            FILTER (
                WHERE funding_agency_name IS DISTINCT FROM
                      'Department of Education'
            )::numeric
            AS other_agency_total

    FROM etl174b_5x1_full
)
SELECT
    ROUND(full_total, 2)
        AS full_total,

    ROUND(education_agency_total, 2)
        AS education_agency_total,

    ROUND(other_agency_total, 2)
        AS other_agency_total,

    ROUND(
        full_total
        - education_agency_total
        - other_agency_total,
        2
    ) AS closure

FROM x;


-- ================================================================================================
-- 15. FINAL CERTIFICATION
-- ================================================================================================

DO $$
DECLARE
    v_full       numeric;
    v_ed         numeric;
    v_difference numeric;
    v_closure    numeric;
BEGIN
    SELECT
        COALESCE(SUM(federal_action_obligation), 0),

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
                WHERE funding_agency_name IS DISTINCT FROM
                      'Department of Education'
            ),
            0
        )

    INTO
        v_full,
        v_ed,
        v_difference

    FROM etl174b_5x1_full;

    v_closure := v_full - v_ed - v_difference;

    IF ABS(v_closure) > 0.01 THEN
        RAISE EXCEPTION
            'ETL-174B-5X-1 RECONCILIATION FAILED: closure=%',
            v_closure;
    END IF;

    RAISE NOTICE
        'ETL-174B-5X-1 PASS - full focal=% Department-of-Education-funded=% other-agency=% closure=% - NO PERSISTENT DB WRITES',
        v_full,
        v_ed,
        v_difference,
        v_closure;
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5X-1 COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'