
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214J - SEVEN-YEAR PROGRAM ACCOUNTING AUDIT'
\echo 'FY2018-FY2024 / EIGHT TARGET PROGRAMS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. PROGRAM-YEAR ACCOUNTING MATRIX'

WITH programs(program_code, program_name) AS (
    VALUES
        ('93.767', 'CHIP'),
        ('93.770', 'MEDICARE PART D'),
        ('84.063', 'PELL GRANTS'),
        ('93.558', 'TANF'),
        ('10.555', 'SCHOOL LUNCH'),
        ('84.010', 'TITLE I'),
        ('84.027', 'SPECIAL EDUCATION'),
        ('93.600', 'HEAD START')
),
years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
),
source_rows AS MATERIALIZED (
    SELECT
        l.assistance_transaction_id,
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        l.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(l.award_id_fain), ''),
            NULLIF(TRIM(l.award_id_uri), '')
        ) AS award_identifier,
        l.reference_county_id,
        l.is_covid,
        l.is_iija,
        l.is_extraordinary
    FROM analysis.v_certified_assistance_ledger l
    JOIN programs p
      ON TRIM(l.cfda_number) = p.program_code
    WHERE
        (
            l.action_date_fiscal_year = 2018
            AND l.load_batch_id = 20
        )
        OR (
            l.action_date_fiscal_year = 2019
            AND l.load_batch_id = 21
        )
        OR (
            l.action_date_fiscal_year BETWEEN 2020 AND 2024
            AND l.reference_state_abbreviation = 'WA'
        )
),
resolved AS MATERIALIZED (
    SELECT
        s.*,
        CASE
            WHEN a.policy_id IS NOT NULL
                THEN 'AWARD_CLASSIFICATION'
            WHEN p.policy_id IS NOT NULL
                THEN 'PROGRAM_POLICY_MAPPING'
            ELSE 'UNCLASSIFIED'
        END AS resolution_source,
        CASE
            WHEN a.policy_id IS NOT NULL
                THEN a.disposition
            WHEN p.policy_id IS NOT NULL
                THEN p.disposition
            ELSE 'UNCLASSIFIED_REVIEW'
        END AS resolved_disposition,
        CASE
            WHEN a.policy_id IS NOT NULL
                THEN a.methodology_version
            WHEN p.policy_id IS NOT NULL
                THEN p.methodology_version
        END AS methodology_version,
        COALESCE(a.match_count, 0) AS award_matches,
        COALESCE(p.match_count, 0) AS program_matches,
        CASE
            WHEN a.policy_id IS NOT NULL
             AND p.policy_id IS NOT NULL
             AND a.disposition IS DISTINCT FROM p.disposition
            THEN TRUE
            ELSE FALSE
        END AS policy_conflict
    FROM source_rows s

    LEFT JOIN LATERAL (
        SELECT
            a.federal_inflow_award_classification_id AS policy_id,
            a.accounting_disposition AS disposition,
            a.methodology_version,
            COUNT(*) OVER () AS match_count
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (
              a.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= a.valid_from_fiscal_year
          )
          AND (
              a.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= a.valid_through_fiscal_year
          )
        ORDER BY
            a.updated_at DESC NULLS LAST,
            a.federal_inflow_award_classification_id DESC
        LIMIT 1
    ) a ON TRUE

    LEFT JOIN LATERAL (
        SELECT
            p.federal_inflow_program_policy_mapping_id AS policy_id,
            p.resolved_accounting_disposition AS disposition,
            p.methodology_version,
            COUNT(*) OVER () AS match_count
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (
              p.valid_from_fiscal_year IS NULL
              OR s.fiscal_year >= p.valid_from_fiscal_year
          )
          AND (
              p.valid_through_fiscal_year IS NULL
              OR s.fiscal_year <= p.valid_through_fiscal_year
          )
        ORDER BY
            p.updated_at DESC NULLS LAST,
            p.federal_inflow_program_policy_mapping_id DESC
        LIMIT 1
    ) p ON TRUE
),
aggregated AS (
    SELECT
        fiscal_year,
        program_code,
        COUNT(*) AS source_transactions,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_transactions,
        COALESCE(SUM(obligation), 0) AS source_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_disposition = 'INCLUDE_ADDITIVE'
        ), 0) AS additive_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_disposition = 'EXCLUDE_DUPLICATE'
        ), 0) AS duplicate_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_disposition = 'WITHHOLD_UNRESOLVED'
        ), 0) AS withheld_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_disposition = 'REFERENCE_ONLY'
        ), 0) AS reference_net,
        COALESCE(SUM(obligation) FILTER (
            WHERE resolved_disposition = 'UNCLASSIFIED_REVIEW'
        ), 0) AS unclassified_net,
        COUNT(*) FILTER (
            WHERE resolved_disposition = 'UNCLASSIFIED_REVIEW'
        ) AS unclassified_transactions,
        COUNT(*) FILTER (
            WHERE reference_county_id IS NOT NULL
        ) AS county_linked_transactions,
        COUNT(*) FILTER (
            WHERE is_covid IS TRUE
               OR is_iija IS TRUE
               OR is_extraordinary IS TRUE
        ) AS extraordinary_tagged_transactions,
        COUNT(*) FILTER (
            WHERE award_matches > 1 OR program_matches > 1
        ) AS multiple_policy_matches,
        COUNT(*) FILTER (
            WHERE policy_conflict
        ) AS conflicting_policy_rows,
        COUNT(*) FILTER (
            WHERE obligation IS NULL
        ) AS null_obligation_rows,
        STRING_AGG(
            DISTINCT
            COALESCE(methodology_version, 'NO_POLICY'),
            ', '
        ) AS methodologies
    FROM resolved
    GROUP BY fiscal_year, program_code
)
SELECT
    y.fiscal_year,
    p.program_code,
    p.program_name,
    COALESCE(a.source_transactions, 0)
        AS source_transactions,
    COALESCE(a.distinct_transactions, 0)
        AS distinct_transactions,
    ROUND(COALESCE(a.source_net, 0), 2)
        AS source_net_obligations,
    ROUND(COALESCE(a.additive_net, 0), 2)
        AS classified_additive,
    ROUND(COALESCE(a.duplicate_net, 0), 2)
        AS excluded_duplicate,
    ROUND(COALESCE(a.withheld_net, 0), 2)
        AS withheld_unresolved,
    ROUND(COALESCE(a.reference_net, 0), 2)
        AS reference_only,
    ROUND(COALESCE(a.unclassified_net, 0), 2)
        AS unclassified_review,
    COALESCE(a.unclassified_transactions, 0)
        AS unclassified_transactions,
    COALESCE(a.county_linked_transactions, 0)
        AS county_linked_transactions,
    COALESCE(a.extraordinary_tagged_transactions, 0)
        AS extraordinary_tagged_transactions,
    COALESCE(a.multiple_policy_matches, 0)
        AS multiple_policy_matches,
    COALESCE(a.conflicting_policy_rows, 0)
        AS conflicting_policy_rows,
    COALESCE(a.null_obligation_rows, 0)
        AS null_obligation_rows,
    COALESCE(a.methodologies, 'NO_SOURCE_ROWS')
        AS methodologies,
    ROUND(
        COALESCE(a.source_net, 0)
        - COALESCE(a.additive_net, 0)
        - COALESCE(a.duplicate_net, 0)
        - COALESCE(a.withheld_net, 0)
        - COALESCE(a.reference_net, 0)
        - COALESCE(a.unclassified_net, 0),
        2
    ) AS reconciliation_difference
FROM years y
CROSS JOIN programs p
LEFT JOIN aggregated a
  ON a.fiscal_year = y.fiscal_year
 AND a.program_code = p.program_code
ORDER BY y.fiscal_year, p.program_code;

\echo ''
\echo '2. EXISTING PROGRAM POLICIES'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN (
      '93.767', '93.770', '84.063', '93.558',
      '10.555', '84.010', '84.027', '93.600'
  )
ORDER BY
    source_program_code,
    valid_from_fiscal_year;

\echo ''
\echo '3. EXISTING PREFERRED SOURCE POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_source_policy
WHERE
    inflow_family ILIKE '%MEDICARE%'
    OR inflow_family ILIKE '%CHIP%'
    OR inflow_family ILIKE '%EDUCATION%'
    OR inflow_family ILIKE '%NUTRITION%'
    OR inflow_family ILIKE '%FAMILY%'
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year;

ROLLBACK;

\echo 'ETL-214J COMPLETE - NO DATABASE WRITES'
