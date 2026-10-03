/*
===============================================================================
ETL-174B-5M
WASHINGTON ASSISTANCE — RESOLVED ACCOUNTING BRIDGE v2
===============================================================================

PURPOSE
-------
Reconstruct the complete FY2020-FY2024 certified Washington USAspending
assistance universe using the durable accounting-resolution hierarchy
established through ETL-174B-5L / Migration 178.

READ ONLY.
NO DATABASE WRITES.

RESOLUTION PRECEDENCE
---------------------
1. Award-specific accounting classification
2. Explicit program -> source-policy mapping
3. UNCLASSIFIED_REVIEW

Award-specific accounting classification ALWAYS wins when both an award
classification and a program-policy mapping are available.

RESOLUTION SOURCE
-----------------
AWARD_CLASSIFICATION
PROGRAM_POLICY_MAPPING
UNCLASSIFIED

CONTROL
-------
The complete resolved bridge must reproduce the certified Washington
FY2020-FY2024 assistance universe exactly:

    $348,524,407,674.34

Nothing in this script authorizes a new accounting classification.
Nothing in this script changes the database.
===============================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5M - RESOLVED ASSISTANCE ACCOUNTING BRIDGE v2'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''


/* ============================================================================
   SECTION 1
   BUILD TRANSACTION-LEVEL RESOLUTION ONCE

   A temporary table is used so that the expensive resolution join and
   window-ranking work is performed once and all subsequent diagnostics use
   the identical resolved population.

   TEMPORARY TABLE ONLY.
   No persistent database write occurs.
   ========================================================================== */

DROP TABLE IF EXISTS etl174b_5m_resolved_assistance;

CREATE TEMP TABLE etl174b_5m_resolved_assistance AS

WITH assistance AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                cfda_number,
                COALESCE(award_id_fain, ''),
                federal_action_obligation,
                COALESCE(recipient_name, ''),
                COALESCE(funding_agency_name, '')
        ) AS bridge_row_id,

        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        cfda_title,
        award_id_fain,
        recipient_name,
        funding_agency_name,
        federal_action_obligation,
        is_covid,
        is_iija,
        is_extraordinary,
        defc_codes,
        funding_families

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

award_candidates AS (
    SELECT
        a.bridge_row_id,

        c.federal_inflow_award_classification_id
            AS award_classification_id,
        
        c.accounting_disposition,
        c.classification_basis,
        c.methodology_version,

        ROW_NUMBER() OVER (
            PARTITION BY a.bridge_row_id
            ORDER BY
                c.updated_at DESC NULLS LAST,
                c.federal_inflow_award_classification_id DESC
        ) AS candidate_rank

    FROM assistance AS a

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = a.cfda_number
     AND c.source_award_identifier = a.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR a.fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR a.fiscal_year <= c.valid_through_fiscal_year
     )
),

award_resolution AS (
    SELECT
        bridge_row_id,
        award_classification_id,
        accounting_disposition,
        classification_basis,
        methodology_version
    FROM award_candidates
    WHERE candidate_rank = 1
),

program_candidates AS (
    SELECT
        a.bridge_row_id,

        m.federal_inflow_program_policy_mapping_id
            AS program_policy_mapping_id,

        m.federal_inflow_source_policy_id,
        m.resolved_accounting_disposition,
        m.mapping_basis,
        m.methodology_version,

        ROW_NUMBER() OVER (
            PARTITION BY a.bridge_row_id
            ORDER BY
                m.updated_at DESC NULLS LAST,
                m.federal_inflow_program_policy_mapping_id DESC
        ) AS candidate_rank

    FROM assistance AS a

    JOIN reference.federal_inflow_program_policy_mapping AS m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = a.cfda_number
     AND (
            m.valid_from_fiscal_year IS NULL
         OR a.fiscal_year >= m.valid_from_fiscal_year
     )
     AND (
            m.valid_through_fiscal_year IS NULL
         OR a.fiscal_year <= m.valid_through_fiscal_year
     )
),

program_resolution AS (
    SELECT
        bridge_row_id,
        program_policy_mapping_id,
        federal_inflow_source_policy_id,
        resolved_accounting_disposition,
        mapping_basis,
        methodology_version
    FROM program_candidates
    WHERE candidate_rank = 1
)

SELECT
    a.*,

    ar.award_classification_id,
    pr.program_policy_mapping_id,
    pr.federal_inflow_source_policy_id,

    CASE
        WHEN ar.bridge_row_id IS NOT NULL
            THEN ar.accounting_disposition

        WHEN pr.bridge_row_id IS NOT NULL
            THEN pr.resolved_accounting_disposition

        ELSE 'UNCLASSIFIED_REVIEW'
    END AS resolved_accounting_disposition,

    CASE
        WHEN ar.bridge_row_id IS NOT NULL
            THEN 'AWARD_CLASSIFICATION'

        WHEN pr.bridge_row_id IS NOT NULL
            THEN 'PROGRAM_POLICY_MAPPING'

        ELSE 'UNCLASSIFIED'
    END AS resolution_source,

    CASE
        WHEN ar.bridge_row_id IS NOT NULL
            THEN ar.methodology_version

        WHEN pr.bridge_row_id IS NOT NULL
            THEN pr.methodology_version

        ELSE NULL
    END AS resolution_methodology,

    CASE
        WHEN ar.bridge_row_id IS NOT NULL
            THEN ar.classification_basis

        WHEN pr.bridge_row_id IS NOT NULL
            THEN pr.mapping_basis

        ELSE NULL
    END AS resolution_basis,

    CASE
        WHEN ar.bridge_row_id IS NOT NULL
         AND pr.bridge_row_id IS NOT NULL
            THEN TRUE
        ELSE FALSE
    END AS both_resolution_layers_present,

    ar.accounting_disposition
        AS award_accounting_disposition,

    pr.resolved_accounting_disposition
        AS program_accounting_disposition

FROM assistance AS a

LEFT JOIN award_resolution AS ar
  ON ar.bridge_row_id = a.bridge_row_id

LEFT JOIN program_resolution AS pr
  ON pr.bridge_row_id = a.bridge_row_id
;


/* ============================================================================
   SECTION 2
   CERTIFIED GROSS CONTROL
   ========================================================================== */

\echo ''
\echo 'SECTION 2 - CERTIFIED GROSS ASSISTANCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS gross_obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars
FROM etl174b_5m_resolved_assistance;


/* ============================================================================
   SECTION 3
   HARD GROSS-CONTROL ASSERTION
   ========================================================================== */

\echo ''
\echo 'SECTION 3 - GROSS CONTROL ASSERTION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_amount numeric;
BEGIN

    SELECT ROUND(SUM(federal_action_obligation), 2)
    INTO v_amount
    FROM etl174b_5m_resolved_assistance;

    IF v_amount <> 348524407674.34::numeric THEN
        RAISE EXCEPTION
            'ETL-174B-5M gross control failure. Expected 348524407674.34; found %',
            v_amount;
    END IF;

    RAISE NOTICE
        'PASS: gross assistance control reproduced exactly: %',
        v_amount;

END
$$;


/* ============================================================================
   SECTION 4
   RESOLUTION SOURCE SUMMARY
   ========================================================================== */

\echo ''
\echo 'SECTION 4 - RESOLUTION SOURCE SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_source,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars
FROM etl174b_5m_resolved_assistance
GROUP BY resolution_source
ORDER BY resolution_source;


/* ============================================================================
   SECTION 5
   FINAL ACCOUNTING DISPOSITION SUMMARY
   ========================================================================== */

\echo ''
\echo 'SECTION 5 - FINAL ACCOUNTING DISPOSITION SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars
FROM etl174b_5m_resolved_assistance
GROUP BY resolved_accounting_disposition
ORDER BY resolved_accounting_disposition;


/* ============================================================================
   SECTION 6
   ACCOUNTING BRIDGE CLOSURE
   ========================================================================== */

\echo ''
\echo 'SECTION 6 - ACCOUNTING BRIDGE CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

WITH disposition AS (
    SELECT
        resolved_accounting_disposition,
        SUM(federal_action_obligation) AS dollars
    FROM etl174b_5m_resolved_assistance
    GROUP BY resolved_accounting_disposition
),

pivoted AS (
    SELECT
        COALESCE(
            SUM(dollars) FILTER (
                WHERE resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
            ),
            0
        ) AS include_additive,

        COALESCE(
            SUM(dollars) FILTER (
                WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
            ),
            0
        ) AS exclude_duplicate,

        COALESCE(
            SUM(dollars) FILTER (
                WHERE resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED'
            ),
            0
        ) AS withhold_unresolved,

        COALESCE(
            SUM(dollars) FILTER (
                WHERE resolved_accounting_disposition = 'REFERENCE_ONLY'
            ),
            0
        ) AS reference_only,

        COALESCE(
            SUM(dollars) FILTER (
                WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
            ),
            0
        ) AS unclassified_review

    FROM disposition
)

SELECT
    ROUND(include_additive, 2)
        AS include_additive,

    ROUND(exclude_duplicate, 2)
        AS exclude_duplicate,

    ROUND(withhold_unresolved, 2)
        AS withhold_unresolved,

    ROUND(reference_only, 2)
        AS reference_only,

    ROUND(unclassified_review, 2)
        AS unclassified_review,

    ROUND(
          include_additive
        + exclude_duplicate
        + withhold_unresolved
        + reference_only
        + unclassified_review,
        2
    ) AS reconstructed_gross,

    ROUND(
        348524407674.34::numeric
        - (
              include_additive
            + exclude_duplicate
            + withhold_unresolved
            + reference_only
            + unclassified_review
          ),
        2
    ) AS bridge_difference

FROM pivoted;


/* ============================================================================
   SECTION 7
   HARD BRIDGE-CLOSURE ASSERTION
   ========================================================================== */

\echo ''
\echo 'SECTION 7 - BRIDGE CLOSURE ASSERTION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_total numeric;
    v_bad_dispositions bigint;
BEGIN

    SELECT
        ROUND(SUM(federal_action_obligation), 2),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition NOT IN (
                'INCLUDE_ADDITIVE',
                'EXCLUDE_DUPLICATE',
                'WITHHOLD_UNRESOLVED',
                'REFERENCE_ONLY',
                'UNCLASSIFIED_REVIEW'
            )
        )
    INTO
        v_total,
        v_bad_dispositions
    FROM etl174b_5m_resolved_assistance;

    IF v_total <> 348524407674.34::numeric THEN
        RAISE EXCEPTION
            'Resolved bridge does not close to certified gross. Found %',
            v_total;
    END IF;

    IF v_bad_dispositions <> 0 THEN
        RAISE EXCEPTION
            'Resolved bridge contains % invalid accounting dispositions',
            v_bad_dispositions;
    END IF;

    RAISE NOTICE
        'PASS: accounting bridge closes exactly and all dispositions are valid';

END
$$;


/* ============================================================================
   SECTION 8
   PRECEDENCE DIAGNOSTIC

   These are observations for which BOTH an award classification and a
   program-policy mapping are available.

   The resolved disposition MUST equal the award disposition.
   ========================================================================== */

\echo ''
\echo 'SECTION 8 - AWARD-OVER-PROGRAM PRECEDENCE DIAGNOSTIC'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    resolved_accounting_disposition,
    award_accounting_disposition,
    program_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars
FROM etl174b_5m_resolved_assistance
WHERE both_resolution_layers_present
GROUP BY
    cfda_number,
    resolved_accounting_disposition,
    award_accounting_disposition,
    program_accounting_disposition
ORDER BY
    cfda_number,
    award_accounting_disposition,
    program_accounting_disposition;


/* ============================================================================
   SECTION 9
   HARD PRECEDENCE ASSERTION
   ========================================================================== */

\echo ''
\echo 'SECTION 9 - PRECEDENCE ASSERTION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_failures bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_failures
    FROM etl174b_5m_resolved_assistance
    WHERE both_resolution_layers_present
      AND resolved_accounting_disposition
          IS DISTINCT FROM award_accounting_disposition;

    IF v_failures <> 0 THEN
        RAISE EXCEPTION
            'Award-over-program precedence failure on % transactions',
            v_failures;
    END IF;

    RAISE NOTICE
        'PASS: award-specific classification has precedence on every dual-resolution transaction';

END
$$;


/* ============================================================================
   SECTION 10
   ANNUAL ACCOUNTING BRIDGE
   ========================================================================== */

\echo ''
\echo 'SECTION 10 - ANNUAL ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    fiscal_year,

    ROUND(SUM(federal_action_obligation), 2)
        AS gross_assistance,

    ROUND(
        SUM(
            CASE
                WHEN resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS include_additive,

    ROUND(
        SUM(
            CASE
                WHEN resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS exclude_duplicate,

    ROUND(
        SUM(
            CASE
                WHEN resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS withhold_unresolved,

    ROUND(
        SUM(
            CASE
                WHEN resolved_accounting_disposition = 'REFERENCE_ONLY'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS reference_only,

    ROUND(
        SUM(
            CASE
                WHEN resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS unclassified_review,

    ROUND(
        SUM(
            CASE
                WHEN resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
                 AND is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS additive_covid,

    ROUND(
        SUM(
            CASE
                WHEN resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
                 AND is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS unclassified_covid

FROM etl174b_5m_resolved_assistance

GROUP BY fiscal_year
ORDER BY fiscal_year;


/* ============================================================================
   SECTION 11
   RESOLUTION SOURCE x ACCOUNTING DISPOSITION
   ========================================================================== */

\echo ''
\echo 'SECTION 11 - RESOLUTION SOURCE x ACCOUNTING DISPOSITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_source,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars
FROM etl174b_5m_resolved_assistance
GROUP BY
    resolution_source,
    resolved_accounting_disposition
ORDER BY
    resolution_source,
    resolved_accounting_disposition;


/* ============================================================================
   SECTION 12
   PROGRAM-POLICY MAPPING EFFECT

   Shows exactly what Migration 178 contributes to resolution after award
   classifications have had first precedence.
   ========================================================================== */

\echo ''
\echo 'SECTION 12 - PROGRAM-POLICY MAPPING EFFECT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars
FROM etl174b_5m_resolved_assistance
WHERE resolution_source = 'PROGRAM_POLICY_MAPPING'
GROUP BY
    cfda_number,
    resolved_accounting_disposition
ORDER BY
    obligation_dollars DESC,
    cfda_number;


/* ============================================================================
   SECTION 13
   AWARD-CLASSIFICATION EFFECT
   ========================================================================== */

\echo ''
\echo 'SECTION 13 - AWARD-CLASSIFICATION EFFECT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars
FROM etl174b_5m_resolved_assistance
WHERE resolution_source = 'AWARD_CLASSIFICATION'
GROUP BY
    cfda_number,
    resolved_accounting_disposition
ORDER BY
    obligation_dollars DESC,
    cfda_number;


/* ============================================================================
   SECTION 14
   TOP 100 GENUINELY UNCLASSIFIED PROGRAMS

   After applying both durable resolution layers, this is the materiality
   queue for future substantive reconciliation.
   ========================================================================== */

\echo ''
\echo 'SECTION 14 - TOP 100 GENUINELY UNCLASSIFIED PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    MAX(funding_agency_name) AS representative_funding_agency,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars
FROM etl174b_5m_resolved_assistance
WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY cfda_number
ORDER BY obligation_dollars DESC
LIMIT 100;


/* ============================================================================
   SECTION 15
   GENUINELY UNCLASSIFIED BY FUNDING AGENCY
   ========================================================================== */

\echo ''
\echo 'SECTION 15 - GENUINELY UNCLASSIFIED BY FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    funding_agency_name,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS distinct_programs,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars
FROM etl174b_5m_resolved_assistance
WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY funding_agency_name
ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 16
   TOP 50 GENUINELY UNCLASSIFIED AWARDS

   Blank FAIN remains visible rather than being artificially populated.
   ========================================================================== */

\echo ''
\echo 'SECTION 16 - TOP 50 GENUINELY UNCLASSIFIED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    fiscal_year,
    cfda_number,
    cfda_title,
    award_id_fain,
    recipient_name,
    funding_agency_name,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    BOOL_OR(is_covid) AS any_covid,
    BOOL_OR(is_iija) AS any_iija,
    BOOL_OR(is_extraordinary) AS any_extraordinary
FROM etl174b_5m_resolved_assistance
WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
GROUP BY
    fiscal_year,
    cfda_number,
    cfda_title,
    award_id_fain,
    recipient_name,
    funding_agency_name
ORDER BY obligation_dollars DESC
LIMIT 50;


/* ============================================================================
   SECTION 17
   UNCLASSIFIED MATERIALITY CONCENTRATION

   Quantifies how much of the remaining unresolved universe is concentrated
   in the largest programs.
   ========================================================================== */

\echo ''
\echo 'SECTION 17 - UNCLASSIFIED MATERIALITY CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        SUM(federal_action_obligation) AS obligation_dollars
    FROM etl174b_5m_resolved_assistance
    WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW'
    GROUP BY cfda_number
),

ranked AS (
    SELECT
        cfda_number,
        obligation_dollars,
        ROW_NUMBER() OVER (
            ORDER BY obligation_dollars DESC
        ) AS materiality_rank
    FROM program_totals
),

control AS (
    SELECT
        SUM(obligation_dollars) AS unresolved_total
    FROM ranked
)

SELECT
    ROUND(c.unresolved_total, 2) AS unresolved_total,

    ROUND(
        SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 10),
        2
    ) AS top_10_programs,

    ROUND(
        100.0
        * SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 10)
        / NULLIF(c.unresolved_total, 0),
        2
    ) AS top_10_percent,

    ROUND(
        SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 25),
        2
    ) AS top_25_programs,

    ROUND(
        100.0
        * SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 25)
        / NULLIF(c.unresolved_total, 0),
        2
    ) AS top_25_percent,

    ROUND(
        SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 50),
        2
    ) AS top_50_programs,

    ROUND(
        100.0
        * SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 50)
        / NULLIF(c.unresolved_total, 0),
        2
    ) AS top_50_percent

FROM ranked AS r
CROSS JOIN control AS c
GROUP BY c.unresolved_total;


/* ============================================================================
   SECTION 18
   FINAL INTEGRITY ASSERTIONS
   ========================================================================== */

\echo ''
\echo 'SECTION 18 - FINAL INTEGRITY ASSERTIONS'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_rows bigint;
    v_null_resolution bigint;
    v_bad_source bigint;
    v_precedence_failures bigint;
    v_total numeric;
BEGIN

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition IS NULL
        ),
        COUNT(*) FILTER (
            WHERE resolution_source NOT IN (
                'AWARD_CLASSIFICATION',
                'PROGRAM_POLICY_MAPPING',
                'UNCLASSIFIED'
            )
        ),
        COUNT(*) FILTER (
            WHERE both_resolution_layers_present
              AND resolved_accounting_disposition
                  IS DISTINCT FROM award_accounting_disposition
        ),
        ROUND(SUM(federal_action_obligation), 2)

    INTO
        v_rows,
        v_null_resolution,
        v_bad_source,
        v_precedence_failures,
        v_total

    FROM etl174b_5m_resolved_assistance;


    IF v_rows = 0 THEN
        RAISE EXCEPTION
            'Resolved assistance population is empty';
    END IF;

    IF v_null_resolution <> 0 THEN
        RAISE EXCEPTION
            'Found % transactions with NULL accounting resolution',
            v_null_resolution;
    END IF;

    IF v_bad_source <> 0 THEN
        RAISE EXCEPTION
            'Found % transactions with invalid resolution_source',
            v_bad_source;
    END IF;

    IF v_precedence_failures <> 0 THEN
        RAISE EXCEPTION
            'Found % award-over-program precedence failures',
            v_precedence_failures;
    END IF;

    IF v_total <> 348524407674.34::numeric THEN
        RAISE EXCEPTION
            'Final control failure: expected 348524407674.34; found %',
            v_total;
    END IF;

    RAISE NOTICE
        'PASS: final integrity checks complete - rows %, gross %, precedence failures %',
        v_rows,
        v_total,
        v_precedence_failures;

END
$$;


/* ============================================================================
   SECTION 19
   COMPLETION MARKER
   ========================================================================== */

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5M PROFILE COMPLETE - RESOLUTION HIERARCHY APPLIED - NO PERSISTENT DB WRITES'
\echo '===================================================================================================='