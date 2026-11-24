
\set ON_ERROR_STOP on
\pset pager off

\echo '=========================================================='
\echo 'ETL-214M1 - HISTORICAL ADDITIVE EXTENSION PREFLIGHT'
\echo 'FY2018-FY2019 / SIX ASSISTANCE PROGRAMS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. EXISTING POLICY AND SOURCE RELATIONSHIPS'

SELECT
    p.source_program_code,
    p.federal_inflow_program_policy_mapping_id,
    p.federal_inflow_source_policy_id,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    s.overlapping_sources,
    s.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping p
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code IN (
      '10.555', '84.010', '84.027',
      '84.063', '93.558', '93.600'
  )
ORDER BY p.source_program_code, p.valid_from_fiscal_year;

\echo ''
\echo '2. HISTORICAL PROGRAM CLASSIFICATION EVIDENCE'

SELECT
    c.source_program_code,
    c.source_program_title,
    c.inflow_family,
    c.inflow_subfamily,
    c.overlap_risk,
    c.classification_basis,
    c.methodology_version,
    c.valid_from_fiscal_year,
    c.valid_through_fiscal_year
FROM reference.federal_inflow_program_classification c
WHERE c.source_system = 'USASPENDING_ASSISTANCE'
  AND c.source_program_code IN (
      '10.555', '84.010', '84.027',
      '84.063', '93.558', '93.600'
  )
ORDER BY
    c.source_program_code,
    c.valid_from_fiscal_year;

\echo ''
\echo '3. HISTORICAL AWARD POPULATION AND POLICY COVERAGE'

WITH target(program_code) AS (
    VALUES
        ('10.555'),
        ('84.010'),
        ('84.027'),
        ('84.063'),
        ('93.558'),
        ('93.600')
),
historical AS MATERIALIZED (
    SELECT
        l.assistance_transaction_id,
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        COALESCE(
            NULLIF(TRIM(l.award_id_fain), ''),
            NULLIF(TRIM(l.award_id_uri), '')
        ) AS award_identifier,
        l.federal_action_obligation AS obligation,
        l.reference_county_id
    FROM analysis.v_certified_assistance_ledger l
    JOIN target t
      ON TRIM(l.cfda_number) = t.program_code
    WHERE
        (l.action_date_fiscal_year = 2018
         AND l.load_batch_id = 20)
        OR
        (l.action_date_fiscal_year = 2019
         AND l.load_batch_id = 21)
),
classified AS (
    SELECT
        h.*,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping p
            WHERE p.source_system = 'USASPENDING_ASSISTANCE'
              AND p.source_program_code = h.program_code
              AND (
                  p.valid_from_fiscal_year IS NULL
                  OR p.valid_from_fiscal_year <= h.fiscal_year
              )
              AND (
                  p.valid_through_fiscal_year IS NULL
                  OR p.valid_through_fiscal_year >= h.fiscal_year
              )
        ) AS existing_program_matches,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_award_classification a
            WHERE a.source_system = 'USASPENDING_ASSISTANCE'
              AND a.source_program_code = h.program_code
              AND a.source_award_identifier = h.award_identifier
              AND (
                  a.valid_from_fiscal_year IS NULL
                  OR a.valid_from_fiscal_year <= h.fiscal_year
              )
              AND (
                  a.valid_through_fiscal_year IS NULL
                  OR a.valid_through_fiscal_year >= h.fiscal_year
              )
        ) AS existing_award_matches
    FROM historical h
)
SELECT
    program_code,
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_identifier) AS distinct_awards,
    COUNT(*) FILTER (
        WHERE award_identifier IS NULL
    ) AS missing_award_ids,
    COUNT(*) FILTER (
        WHERE obligation IS NULL
    ) AS null_obligations,
    COUNT(*) FILTER (
        WHERE obligation < 0
    ) AS negative_obligation_rows,
    COUNT(*) FILTER (
        WHERE reference_county_id IS NOT NULL
    ) AS county_linked_rows,
    COUNT(*) FILTER (
        WHERE existing_program_matches > 0
           OR existing_award_matches > 0
    ) AS existing_policy_covered,
    COUNT(*) FILTER (
        WHERE existing_program_matches > 1
           OR existing_award_matches > 1
    ) AS multiple_policy_matches,
    ROUND(SUM(obligation), 2) AS net_obligations
FROM classified
GROUP BY program_code, fiscal_year
ORDER BY program_code, fiscal_year;

\echo ''
\echo '4. OVERLAP-RISK CLASSIFICATION AND SOURCE POLICY COVERAGE'

WITH target(program_code) AS (
    VALUES
        ('10.555'),
        ('84.010'),
        ('84.027'),
        ('84.063'),
        ('93.558'),
        ('93.600')
)
SELECT
    t.program_code,
    c.inflow_family,
    c.inflow_subfamily,
    c.overlap_risk,
    c.valid_from_fiscal_year AS classification_from,
    c.valid_through_fiscal_year AS classification_through,
    s.preferred_source,
    s.accounting_measure,
    s.overlapping_sources,
    s.valid_from_fiscal_year AS source_policy_from,
    s.valid_through_fiscal_year AS source_policy_through,
    s.ledger_treatment
FROM target t
LEFT JOIN reference.federal_inflow_program_classification c
  ON c.source_system = 'USASPENDING_ASSISTANCE'
 AND c.source_program_code = t.program_code
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.inflow_family = c.inflow_family
 AND s.inflow_subfamily = c.inflow_subfamily
ORDER BY
    t.program_code,
    c.valid_from_fiscal_year,
    s.valid_from_fiscal_year;

ROLLBACK;

\echo 'ETL-214M1 COMPLETE - NO DATABASE WRITES'
