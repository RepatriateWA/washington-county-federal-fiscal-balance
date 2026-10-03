/*
===============================================================================
ETL-174B-5K
WASHINGTON ASSISTANCE — ACCOUNTING RESOLUTION HIERARCHY PROFILE
===============================================================================

PURPOSE
-------
Determine how the complete FY2020-FY2024 certified Washington USAspending
assistance universe should inherit already-established accounting decisions.

READ ONLY.
NO DATABASE WRITES.

PROPOSED RESOLUTION HIERARCHY
-----------------------------
1. Award-specific accounting classification
2. Program/source accounting policy
3. UNCLASSIFIED_REVIEW

IMPORTANT
---------
This profile DOES NOT infer a program decision merely because a program belongs
to the same broad inflow family as an existing policy.

The purpose is to identify exact, defensible program-to-policy mappings before
we persist or operationalize the hierarchy.
===============================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5K — ACCOUNTING RESOLUTION HIERARCHY PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY — NO DATABASE WRITES'
\echo ''


/* ============================================================================
   SECTION 1 — SOURCE POLICY INVENTORY
   ========================================================================== */

\echo ''
\echo 'SECTION 1 — FEDERAL INFLOW SOURCE POLICY INVENTORY'
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
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    source_selection_basis
FROM reference.federal_inflow_source_policy
ORDER BY
    inflow_family,
    inflow_subfamily,
    methodology_version,
    federal_inflow_source_policy_id;


/* ============================================================================
   SECTION 2 — PROGRAM CLASSIFICATION INVENTORY

   This is the key linkage layer between a USAspending program code and an
   inflow family/subfamily.
   ========================================================================== */

\echo ''
\echo 'SECTION 2 — USAspending PROGRAM CLASSIFICATION INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    classification_basis
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
ORDER BY
    source_program_code,
    methodology_version,
    federal_inflow_program_classification_id;


/* ============================================================================
   SECTION 3 — PROGRAM CLASSIFICATION -> SOURCE POLICY EXACT MATCH

   Exact family + subfamily only.

   We deliberately do NOT fall back to family-only matching.
   ========================================================================== */

\echo ''
\echo 'SECTION 3 — PROGRAM CLASSIFICATION TO SOURCE POLICY EXACT MATCH'
\echo '----------------------------------------------------------------------------------------------------'

WITH program AS (
    SELECT *
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
),

matches AS (
    SELECT
        p.source_program_code,
        p.source_program_title,
        p.inflow_family,
        p.inflow_subfamily,
        p.methodology_version AS program_methodology,
        p.valid_from_fiscal_year AS program_from_fy,
        p.valid_through_fiscal_year AS program_through_fy,

        s.federal_inflow_source_policy_id,
        s.ledger_treatment,
        s.preferred_source,
        s.allocation_source,
        s.methodology_version AS policy_methodology,
        s.valid_from_fiscal_year AS policy_from_fy,
        s.valid_through_fiscal_year AS policy_through_fy

    FROM program AS p

    LEFT JOIN reference.federal_inflow_source_policy AS s
      ON s.inflow_family = p.inflow_family
     AND s.inflow_subfamily = p.inflow_subfamily
)

SELECT *
FROM matches
ORDER BY
    source_program_code,
    program_methodology,
    policy_methodology;


/* ============================================================================
   SECTION 4 — EXACT PROGRAM/POLICY MATCH CARDINALITY

   Detect ambiguity before attempting to use policy inheritance.
   ========================================================================== */

\echo ''
\echo 'SECTION 4 — EXACT PROGRAM/POLICY MATCH CARDINALITY'
\echo '----------------------------------------------------------------------------------------------------'

WITH program AS (
    SELECT *
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
)

SELECT
    p.source_program_code,
    p.inflow_family,
    p.inflow_subfamily,
    p.methodology_version,

    COUNT(s.federal_inflow_source_policy_id)
        AS matching_source_policies

FROM program AS p

LEFT JOIN reference.federal_inflow_source_policy AS s
  ON s.inflow_family = p.inflow_family
 AND s.inflow_subfamily = p.inflow_subfamily

GROUP BY
    p.source_program_code,
    p.inflow_family,
    p.inflow_subfamily,
    p.methodology_version

ORDER BY
    matching_source_policies DESC,
    p.source_program_code;


/* ============================================================================
   SECTION 5 — KNOWN HIGH-MATERIALITY PROGRAMS

   Inspect exactly how the programs already resolved in our methodology are
   represented in the program-classification and source-policy layers.
   ========================================================================== */

\echo ''
\echo 'SECTION 5 — KNOWN HIGH-MATERIALITY PROGRAM POLICY MAP'
\echo '----------------------------------------------------------------------------------------------------'

WITH target_programs(source_program_code) AS (
    VALUES
        ('96.001'),
        ('96.002'),
        ('96.004'),
        ('96.006'),

        ('93.778'),
        ('93.767'),
        ('93.770'),
        ('93.773'),
        ('93.774'),

        ('93.775'),
        ('93.777'),
        ('93.791'),
        ('93.796')
)

SELECT
    t.source_program_code,

    p.source_program_title,
    p.inflow_family,
    p.inflow_subfamily,
    p.overlap_risk,
    p.methodology_version AS program_methodology,

    s.ledger_treatment,
    s.preferred_source,
    s.allocation_source,
    s.methodology_version AS policy_methodology,

    CASE
        WHEN p.federal_inflow_program_classification_id IS NULL
            THEN 'NO_PROGRAM_CLASSIFICATION'

        WHEN s.federal_inflow_source_policy_id IS NULL
            THEN 'PROGRAM_CLASSIFIED_NO_EXACT_POLICY'

        ELSE 'EXACT_POLICY_AVAILABLE'
    END AS mapping_status

FROM target_programs AS t

LEFT JOIN reference.federal_inflow_program_classification AS p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = t.source_program_code

LEFT JOIN reference.federal_inflow_source_policy AS s
  ON s.inflow_family = p.inflow_family
 AND s.inflow_subfamily = p.inflow_subfamily

ORDER BY
    t.source_program_code,
    p.methodology_version,
    s.methodology_version;


/* ============================================================================
   SECTION 6 — VA PROGRAM CLASSIFICATION COVERAGE

   VA requires special attention because the established policy is that VA GDX
   is the preferred accounting path. We need to see whether USAspending 64.*
   programs are explicitly mapped or merely covered by a family-level policy.
   ========================================================================== */

\echo ''
\echo 'SECTION 6 — VA USAspending PROGRAM CLASSIFICATION COVERAGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH va_universe AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        COUNT(*) AS transaction_count,
        ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'
    GROUP BY cfda_number
)

SELECT
    v.cfda_number,
    v.cfda_title,
    v.transaction_count,
    v.obligation_dollars,

    p.inflow_family,
    p.inflow_subfamily,
    p.overlap_risk,
    p.methodology_version AS program_methodology,

    s.ledger_treatment,
    s.preferred_source,
    s.methodology_version AS policy_methodology,

    CASE
        WHEN p.federal_inflow_program_classification_id IS NULL
            THEN 'NO_PROGRAM_CLASSIFICATION'

        WHEN s.federal_inflow_source_policy_id IS NULL
            THEN 'PROGRAM_CLASSIFIED_NO_EXACT_POLICY'

        ELSE 'EXACT_POLICY_AVAILABLE'
    END AS mapping_status

FROM va_universe AS v

LEFT JOIN reference.federal_inflow_program_classification AS p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = v.cfda_number

LEFT JOIN reference.federal_inflow_source_policy AS s
  ON s.inflow_family = p.inflow_family
 AND s.inflow_subfamily = p.inflow_subfamily

ORDER BY
    v.obligation_dollars DESC,
    v.cfda_number;


/* ============================================================================
   SECTION 7 — PROGRAM-LEVEL MATERIALITY VS PERSISTED CLASSIFICATION

   Shows which high-value programs currently lack an award classification,
   regardless of whether a policy already exists.
   ========================================================================== */

\echo ''
\echo 'SECTION 7 — TOP 100 PROGRAMS AND CURRENT PERSISTENCE COVERAGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        COUNT(*) AS transaction_count,
        ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
    GROUP BY cfda_number
),

award_classification_coverage AS (
    SELECT
        source_program_code,
        accounting_disposition,
        COUNT(*) AS classified_awards
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
    GROUP BY
        source_program_code,
        accounting_disposition
),

program_policy AS (
    SELECT
        p.source_program_code,
        p.inflow_family,
        p.inflow_subfamily,
        p.methodology_version AS program_methodology,
        s.ledger_treatment,
        s.methodology_version AS policy_methodology
    FROM reference.federal_inflow_program_classification AS p
    LEFT JOIN reference.federal_inflow_source_policy AS s
      ON s.inflow_family = p.inflow_family
     AND s.inflow_subfamily = p.inflow_subfamily
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
)

SELECT
    pt.cfda_number,
    pt.cfda_title,
    pt.transaction_count,
    pt.obligation_dollars,

    ac.accounting_disposition,
    ac.classified_awards,

    pp.inflow_family,
    pp.inflow_subfamily,
    pp.ledger_treatment,
    pp.program_methodology,
    pp.policy_methodology

FROM program_totals AS pt

LEFT JOIN award_classification_coverage AS ac
  ON ac.source_program_code = pt.cfda_number

LEFT JOIN program_policy AS pp
  ON pp.source_program_code = pt.cfda_number

ORDER BY
    pt.obligation_dollars DESC,
    pt.cfda_number,
    ac.accounting_disposition

LIMIT 100;


/* ============================================================================
   SECTION 8 — SOURCE-POLICY TREATMENT COUNTS
   ========================================================================== */

\echo ''
\echo 'SECTION 8 — SOURCE POLICY TREATMENT INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ledger_treatment,
    COUNT(*) AS policy_count
FROM reference.federal_inflow_source_policy
GROUP BY ledger_treatment
ORDER BY ledger_treatment;


/* ============================================================================
   SECTION 9 — POLICIES WITH NO EXACT USAspending PROGRAM MAPPING

   Useful for distinguishing broad accounting policies from policies that can
   safely drive USAspending transaction disposition.
   ========================================================================== */

\echo ''
\echo 'SECTION 9 — SOURCE POLICIES WITHOUT EXACT PROGRAM MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    s.federal_inflow_source_policy_id,
    s.inflow_family,
    s.inflow_subfamily,
    s.ledger_treatment,
    s.preferred_source,
    s.methodology_version,
    s.valid_from_fiscal_year,
    s.valid_through_fiscal_year

FROM reference.federal_inflow_source_policy AS s

LEFT JOIN reference.federal_inflow_program_classification AS p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.inflow_family = s.inflow_family
 AND p.inflow_subfamily = s.inflow_subfamily

WHERE p.federal_inflow_program_classification_id IS NULL

ORDER BY
    s.inflow_family,
    s.inflow_subfamily,
    s.methodology_version;


/* ============================================================================
   SECTION 10 — PROGRAM CLASSIFICATIONS WITH NO EXACT POLICY

   These cannot safely inherit an accounting disposition.
   ========================================================================== */

\echo ''
\echo 'SECTION 10 — PROGRAM CLASSIFICATIONS WITHOUT EXACT SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    p.federal_inflow_program_classification_id,
    p.source_program_code,
    p.source_program_title,
    p.inflow_family,
    p.inflow_subfamily,
    p.overlap_risk,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year

FROM reference.federal_inflow_program_classification AS p

LEFT JOIN reference.federal_inflow_source_policy AS s
  ON s.inflow_family = p.inflow_family
 AND s.inflow_subfamily = p.inflow_subfamily

WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND s.federal_inflow_source_policy_id IS NULL

ORDER BY
    p.source_program_code,
    p.methodology_version;


/* ============================================================================
   SECTION 11 — FY2020-2024 PROGRAM UNIVERSE NOT REPRESENTED IN THE PROGRAM
                CLASSIFICATION TABLE

   This is the genuine future classification universe.
   ========================================================================== */

\echo ''
\echo 'SECTION 11 — CERTIFIED PROGRAMS WITHOUT PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        MAX(funding_agency_name) AS representative_funding_agency,
        COUNT(*) AS transaction_count,
        ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
        ROUND(
            SUM(
                CASE WHEN is_covid
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            2
        ) AS covid_dollars,
        ROUND(
            SUM(
                CASE WHEN is_iija
                     THEN federal_action_obligation
                     ELSE 0
                END
            ),
            2
        ) AS iija_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
    GROUP BY cfda_number
)

SELECT
    pt.*
FROM program_totals AS pt

LEFT JOIN reference.federal_inflow_program_classification AS p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = pt.cfda_number

WHERE p.federal_inflow_program_classification_id IS NULL

ORDER BY
    pt.obligation_dollars DESC;


/* ============================================================================
   SECTION 12 — CONTROL TOTAL
   ========================================================================== */

\echo ''
\echo 'SECTION 12 — CERTIFIED ASSISTANCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


/* ============================================================================
   SECTION 13 — COMPLETION MARKER
   ========================================================================== */

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5K PROFILE COMPLETE — NO DB WRITES'
\echo '===================================================================================================='