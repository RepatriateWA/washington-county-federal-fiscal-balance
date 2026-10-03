/*
================================================================================
ETL-174B-5Y
SECTION 8 HOUSING CHOICE VOUCHER ASSISTANCE PROFILE
================================================================================

Purpose
-------
Profile Washington FY2020-FY2024 USAspending assistance associated with:

    14.871
    Section 8 Housing Choice Vouchers

This is the next high-materiality unresolved assistance program following
Migration 183.

Known post-Migration-183 unresolved control
-------------------------------------------
Transactions:          823,748
Programs:                 1,275
Obligations:     $61,504,044,044.56
COVID:           $16,064,457,706.27
IIJA:             $3,797,323,322.93
Extraordinary:   $21,335,400,225.04

Known 14.871 residual control
-----------------------------
Obligations:      $4,308,080,637.65

Objectives
----------
1. Reconstruct the current post-Migration-183 unresolved assistance universe.
2. Reproduce the known 14.871 dollar control.
3. Establish transaction, award, and recipient counts.
4. Profile annual behavior.
5. Profile positive obligations, deobligations, and zero-dollar transactions.
6. Profile funding-agency provenance.
7. Profile COVID / IIJA / extraordinary provenance.
8. Profile recipient concentration.
9. Profile award structure.
10. Profile transaction descriptions.
11. Inspect existing classification / mapping state.
12. Quantify materiality against the current unresolved universe.

Accounting decision
-------------------
NONE.

This script does not decide whether 14.871 is additive, overlapping,
reference-only, or withheld. It produces the evidence needed for that decision.

READ ONLY.
TEMP TABLES ONLY.
NO PERSISTENT DATABASE WRITES.

================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5Y SECTION 8 HOUSING CHOICE VOUCHER ASSISTANCE PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. MATERIALIZE CERTIFIED WA ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5y_ledger;

CREATE TEMP TABLE etl174b_5y_ledger AS
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

CREATE INDEX ON etl174b_5y_ledger (cfda_number);
CREATE INDEX ON etl174b_5y_ledger (source_award_identifier);
CREATE INDEX ON etl174b_5y_ledger (action_date_fiscal_year);


-- ================================================================================================
-- 2. RECONSTRUCT CURRENT EFFECTIVE ACCOUNTING DISPOSITION
--
-- Award-specific classification has precedence over program-policy mapping.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5y_award_matches;

CREATE TEMP TABLE etl174b_5y_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM etl174b_5y_ledger l

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


DROP TABLE IF EXISTS pg_temp.etl174b_5y_program_matches;

CREATE TEMP TABLE etl174b_5y_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM etl174b_5y_ledger l

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
     );


DO $$
DECLARE
    v_award_duplicates   bigint;
    v_program_duplicates bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_award_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5y_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    SELECT COUNT(*)
    INTO v_program_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM etl174b_5y_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    IF v_award_duplicates <> 0
       OR v_program_duplicates <> 0
    THEN
        RAISE EXCEPTION
            'ETL-174B-5Y RESOLUTION UNIQUENESS FAILED: award_duplicates=% program_duplicates=%',
            v_award_duplicates,
            v_program_duplicates;
    END IF;

    RAISE NOTICE
        'ETL-174B-5Y RESOLUTION UNIQUENESS PASS';
END
$$;


DROP TABLE IF EXISTS pg_temp.etl174b_5y_resolved;

CREATE TEMP TABLE etl174b_5y_resolved AS
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
        p.resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_accounting_disposition

FROM etl174b_5y_ledger l

LEFT JOIN etl174b_5y_award_matches a
  ON a.assistance_transaction_id =
     l.assistance_transaction_id

LEFT JOIN etl174b_5y_program_matches p
  ON p.assistance_transaction_id =
     l.assistance_transaction_id;

CREATE INDEX ON etl174b_5y_resolved (effective_accounting_disposition);
CREATE INDEX ON etl174b_5y_resolved (cfda_number);


-- ================================================================================================
-- 3. POST-MIGRATION-183 UNRESOLVED CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. CURRENT POST-M183 UNRESOLVED CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

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

FROM etl174b_5y_resolved

WHERE effective_accounting_disposition =
      'UNCLASSIFIED_REVIEW';


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

        COALESCE(
            SUM(
                CASE WHEN is_covid
                     THEN federal_action_obligation ELSE 0 END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE WHEN is_iija
                     THEN federal_action_obligation ELSE 0 END
            ),
            0
        ),

        COALESCE(
            SUM(
                CASE WHEN is_extraordinary
                     THEN federal_action_obligation ELSE 0 END
            ),
            0
        )

    INTO
        v_transactions,
        v_programs,
        v_total,
        v_covid,
        v_iija,
        v_extra

    FROM etl174b_5y_resolved

    WHERE effective_accounting_disposition =
          'UNCLASSIFIED_REVIEW';

    IF v_transactions <> 823748
       OR v_programs <> 1275
       OR ABS(v_total - 61504044044.56::numeric) > 0.01
       OR ABS(v_covid - 16064457706.27::numeric) > 0.01
       OR ABS(v_iija - 3797323322.93::numeric) > 0.01
       OR ABS(v_extra - 21335400225.04::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5Y RESIDUAL CONTROL FAILED: tx=% programs=% total=% COVID=% IIJA=% extraordinary=%',
            v_transactions,
            v_programs,
            v_total,
            v_covid,
            v_iija,
            v_extra;
    END IF;

    RAISE NOTICE
        'ETL-174B-5Y RESIDUAL CONTROL PASS: tx=% programs=% total=%',
        v_transactions,
        v_programs,
        v_total;
END
$$;


-- ================================================================================================
-- 4. MATERIALIZE 14.871 FOCAL POPULATION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5y_focal;

CREATE TEMP TABLE etl174b_5y_focal AS
SELECT *
FROM etl174b_5y_resolved
WHERE effective_accounting_disposition =
      'UNCLASSIFIED_REVIEW'
  AND cfda_number = '14.871';


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. 14.871 FOCAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

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

FROM etl174b_5y_focal;


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

    FROM etl174b_5y_focal;

    IF v_programs <> 1
       OR ABS(v_total - 4308080637.65::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5Y FOCAL CONTROL FAILED: programs=% total=%',
            v_programs,
            v_total;
    END IF;

    RAISE NOTICE
        'ETL-174B-5Y FOCAL CONTROL PASS: 14.871 total=%',
        v_total;
END
$$;


-- ================================================================================================
-- 5. TITLE / FUNDING-AGENCY IDENTITY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. PROGRAM IDENTITY AND FUNDING-AGENCY PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    cfda_title,
    COALESCE(funding_agency_name, '[NULL]')
        AS funding_agency_name,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    COUNT(DISTINCT recipient_name)
        AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM etl174b_5y_focal

GROUP BY
    cfda_number,
    cfda_title,
    COALESCE(funding_agency_name, '[NULL]')

ORDER BY
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 6. ANNUAL PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. 14.871 BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    COUNT(DISTINCT recipient_name)
        AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

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

FROM etl174b_5y_focal

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 7. SIGN PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. 14.871 SIGN / DEOBLIGATION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
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
        )::numeric,
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
        )::numeric,
        2
    ) AS negative_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation),
            0
        )::numeric,
        2
    ) AS net_obligations

FROM etl174b_5y_focal;


-- ================================================================================================
-- 8. SIGN PROFILE BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. 14.871 SIGN PROFILE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

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
        )::numeric,
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

FROM etl174b_5y_focal

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 9. FUNDING PROVENANCE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. COVID / IIJA / EXTRAORDINARY PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount

FROM etl174b_5y_focal

GROUP BY
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary

ORDER BY
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 10. RECIPIENT CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TOP 50 RECIPIENTS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    recipient_name,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT source_award_identifier)
        AS award_count,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount

FROM etl174b_5y_focal

GROUP BY recipient_name

ORDER BY
    SUM(federal_action_obligation) DESC,
    recipient_name

LIMIT 50;


-- ================================================================================================
-- 11. AWARD CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP 75 AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_award_identifier,
    MAX(recipient_name) AS recipient_name,

    COUNT(*) AS transaction_count,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        )::numeric,
        2
    ) AS covid_amount

FROM etl174b_5y_focal

GROUP BY source_award_identifier

ORDER BY
    SUM(federal_action_obligation) DESC,
    source_award_identifier

LIMIT 75;


-- ================================================================================================
-- 12. AWARD STRUCTURE BY YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. AWARD STRUCTURE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(DISTINCT source_award_identifier)
        AS distinct_awards,

    COUNT(DISTINCT recipient_name)
        AS distinct_recipients,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        AVG(federal_action_obligation)::numeric,
        2
    ) AS average_transaction_obligation

FROM etl174b_5y_focal

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 13. TRANSACTION DESCRIPTION PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. MOST MATERIAL TRANSACTION DESCRIPTIONS'
\echo '----------------------------------------------------------------------------------------------------'

WITH description_totals AS (
    SELECT
        COALESCE(
            NULLIF(BTRIM(transaction_description), ''),
            '[NULL]'
        ) AS transaction_description,

        COUNT(*) AS transaction_count,

        COUNT(DISTINCT source_award_identifier)
            AS award_count,

        SUM(federal_action_obligation)::numeric
            AS obligation_amount

    FROM etl174b_5y_focal

    GROUP BY
        COALESCE(
            NULLIF(BTRIM(transaction_description), ''),
            '[NULL]'
        )
)
SELECT
    transaction_description,
    transaction_count,
    award_count,

    ROUND(
        obligation_amount,
        2
    ) AS obligation_amount

FROM description_totals

ORDER BY
    ABS(obligation_amount) DESC,
    transaction_description

LIMIT 75;


-- ================================================================================================
-- 14. EXISTING PROGRAM CLASSIFICATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_system,
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
  AND source_program_code = '14.871'

ORDER BY methodology_version;


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
  AND source_program_code = '14.871'

ORDER BY
    source_award_identifier,
    methodology_version;


-- ================================================================================================
-- 16. EXISTING PROGRAM-POLICY MAPPING
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. EXISTING PROGRAM-POLICY MAPPING'
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
    p.allocation_source,
    p.overlapping_sources,
    p.ledger_treatment,
    p.source_selection_basis

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '14.871'

ORDER BY m.methodology_version;


-- ================================================================================================
-- 17. MATERIALITY AGAINST CURRENT RESIDUAL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. 14.871 MATERIALITY'
\echo '----------------------------------------------------------------------------------------------------'

WITH controls AS (
    SELECT
        (
            SELECT
                COALESCE(
                    SUM(federal_action_obligation),
                    0
                )::numeric
            FROM etl174b_5y_focal
        ) AS focal_total,

        (
            SELECT
                COALESCE(
                    SUM(federal_action_obligation),
                    0
                )::numeric
            FROM etl174b_5y_resolved
            WHERE effective_accounting_disposition =
                  'UNCLASSIFIED_REVIEW'
        ) AS residual_total
)
SELECT
    ROUND(
        focal_total,
        2
    ) AS focal_total,

    ROUND(
        residual_total,
        2
    ) AS residual_total,

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
-- 18. HYPOTHETICAL ACCOUNTING EFFECT
--
-- This is arithmetic only. It does NOT authorize INCLUDE_ADDITIVE.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. HYPOTHETICAL EFFECT IF 14.871 WERE EVENTUALLY CERTIFIED INCLUDE_ADDITIVE'
\echo '----------------------------------------------------------------------------------------------------'

WITH controls AS (
    SELECT
        (
            SELECT
                COALESCE(
                    SUM(federal_action_obligation),
                    0
                )::numeric
            FROM etl174b_5y_focal
        ) AS focal_total
)
SELECT
    ROUND(
        51497106903.04::numeric + focal_total,
        2
    ) AS hypothetical_include_additive,

    ROUND(
        61504044044.56::numeric - focal_total,
        2
    ) AS hypothetical_unclassified_review

FROM controls;


-- ================================================================================================
-- 19. FINAL READ-ONLY CERTIFICATION
-- ================================================================================================

DO $$
DECLARE
    v_residual_transactions bigint;
    v_residual_programs     bigint;
    v_residual_total        numeric;

    v_focal_programs        bigint;
    v_focal_total           numeric;

    v_existing_program_classifications bigint;
    v_existing_award_classifications   bigint;
    v_existing_program_mappings        bigint;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_residual_transactions,
        v_residual_programs,
        v_residual_total

    FROM etl174b_5y_resolved

    WHERE effective_accounting_disposition =
          'UNCLASSIFIED_REVIEW';


    SELECT
        COUNT(DISTINCT cfda_number),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_focal_programs,
        v_focal_total

    FROM etl174b_5y_focal;


    SELECT COUNT(*)
    INTO v_existing_program_classifications
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.871';


    SELECT COUNT(*)
    INTO v_existing_award_classifications
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.871';


    SELECT COUNT(*)
    INTO v_existing_program_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.871';


    IF v_residual_transactions <> 823748
       OR v_residual_programs <> 1275
       OR ABS(
            v_residual_total -
            61504044044.56::numeric
          ) > 0.01
       OR v_focal_programs <> 1
       OR ABS(
            v_focal_total -
            4308080637.65::numeric
          ) > 0.01
    THEN
        RAISE EXCEPTION
            'ETL-174B-5Y FINAL CONTROL FAILED: residual_tx=% residual_programs=% residual_total=% focal_programs=% focal_total=%',
            v_residual_transactions,
            v_residual_programs,
            v_residual_total,
            v_focal_programs,
            v_focal_total;
    END IF;


    RAISE NOTICE
        'ETL-174B-5Y PASS - 14.871 profiled: total=%; current residual=%; existing program classifications=% award classifications=% program mappings=%; NO PERSISTENT DB WRITES',
        v_focal_total,
        v_residual_total,
        v_existing_program_classifications,
        v_existing_award_classifications,
        v_existing_program_mappings;
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5Y COMPLETE'
\echo '===================================================================================================='
\echo 'SECTION 8 HOUSING CHOICE VOUCHERS PROFILED'
\echo 'NO ACCOUNTING DECISION MADE'
\echo 'NO PERSISTENT DATABASE WRITES'