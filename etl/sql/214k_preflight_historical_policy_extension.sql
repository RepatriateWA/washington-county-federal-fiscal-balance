
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214K - HISTORICAL POLICY EXTENSION PREFLIGHT'
\echo 'FY2018-FY2024 UNIFIED ACCOUNTING FRAMEWORK'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. SIX CANDIDATE PROGRAMS: EXISTING POLICY EVIDENCE'

WITH target_programs(program_code, program_name) AS (
    VALUES
        ('84.063', 'PELL GRANTS'),
        ('93.558', 'TANF'),
        ('10.555', 'SCHOOL LUNCH'),
        ('84.010', 'TITLE I'),
        ('84.027', 'SPECIAL EDUCATION'),
        ('93.600', 'HEAD START')
)
SELECT
    t.program_code,
    t.program_name,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version,
    p.mapping_basis,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.ledger_treatment,
    s.source_selection_basis
FROM target_programs t
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = t.program_code
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
ORDER BY
    t.program_code,
    p.valid_from_fiscal_year;

\echo ''
\echo '2. HISTORICAL SOURCE COMPARISON: FY2018-FY2024'

WITH target_programs(program_code, program_name) AS (
    VALUES
        ('84.063', 'PELL GRANTS'),
        ('93.558', 'TANF'),
        ('10.555', 'SCHOOL LUNCH'),
        ('84.010', 'TITLE I'),
        ('84.027', 'SPECIAL EDUCATION'),
        ('93.600', 'HEAD START')
),
source_rows AS (
    SELECT
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        l.assistance_transaction_id,
        l.federal_action_obligation AS obligation,
        l.reference_county_id,
        l.is_covid,
        l.is_iija,
        l.is_extraordinary
    FROM analysis.v_certified_assistance_ledger l
    JOIN target_programs t
      ON TRIM(l.cfda_number) = t.program_code
    WHERE
        (l.action_date_fiscal_year = 2018
         AND l.load_batch_id = 20)
        OR
        (l.action_date_fiscal_year = 2019
         AND l.load_batch_id = 21)
        OR
        (l.action_date_fiscal_year BETWEEN 2020 AND 2024
         AND l.reference_state_abbreviation = 'WA')
)
SELECT
    s.program_code,
    t.program_name,
    s.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT s.assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(s.obligation), 2)
        AS net_obligations,
    ROUND(
        COALESCE(
            SUM(s.obligation) FILTER (
                WHERE s.obligation > 0
            ), 0
        ), 2
    ) AS positive_obligations,
    ROUND(
        COALESCE(
            SUM(s.obligation) FILTER (
                WHERE s.obligation < 0
            ), 0
        ), 2
    ) AS negative_obligations,
    COUNT(*) FILTER (
        WHERE s.reference_county_id IS NOT NULL
    ) AS county_linked_rows,
    COUNT(*) FILTER (
        WHERE s.is_covid IS TRUE
           OR s.is_iija IS TRUE
           OR s.is_extraordinary IS TRUE
    ) AS extraordinary_tagged_rows
FROM source_rows s
JOIN target_programs t
  ON t.program_code = s.program_code
GROUP BY
    s.program_code,
    t.program_name,
    s.fiscal_year
ORDER BY
    s.program_code,
    s.fiscal_year;

\echo ''
\echo '3. HISTORICAL COMPETING POLICY INVENTORY'

SELECT
    'PROGRAM_POLICY' AS policy_type,
    p.source_program_code,
    NULL::text AS source_award_identifier,
    p.resolved_accounting_disposition AS disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version
FROM reference.federal_inflow_program_policy_mapping p
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code IN (
      '84.063', '93.558', '10.555',
      '84.010', '84.027', '93.600'
  )
  AND (p.valid_from_fiscal_year IS NULL
       OR p.valid_from_fiscal_year <= 2019)
  AND (p.valid_through_fiscal_year IS NULL
       OR p.valid_through_fiscal_year >= 2018)

UNION ALL

SELECT
    'AWARD_CLASSIFICATION' AS policy_type,
    a.source_program_code,
    a.source_award_identifier,
    a.accounting_disposition AS disposition,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year,
    a.methodology_version
FROM reference.federal_inflow_award_classification a
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND a.source_program_code IN (
      '84.063', '93.558', '10.555',
      '84.010', '84.027', '93.600'
  )
  AND (a.valid_from_fiscal_year IS NULL
       OR a.valid_from_fiscal_year <= 2019)
  AND (a.valid_through_fiscal_year IS NULL
       OR a.valid_through_fiscal_year >= 2018)
ORDER BY
    source_program_code,
    policy_type,
    source_award_identifier;

\echo ''
\echo '4. CHIP AND MEDICARE PART D: CONTROL POLICY INVENTORY'

SELECT
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping p
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code IN ('93.767', '93.770')
ORDER BY
    p.source_program_code,
    p.valid_from_fiscal_year;

\echo ''
\echo '5. SOURCE POLICY COVERAGE FOR FY2018-FY2019'

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
    (
        inflow_family ILIKE '%EDUCATION%'
        OR inflow_family ILIKE '%NUTRITION%'
        OR inflow_family ILIKE '%FAMILY%'
        OR inflow_family ILIKE '%CHIP%'
        OR inflow_family ILIKE '%MEDICARE%'
    )
    AND (
        valid_from_fiscal_year IS NULL
        OR valid_from_fiscal_year <= 2019
    )
    AND (
        valid_through_fiscal_year IS NULL
        OR valid_through_fiscal_year >= 2018
    )
ORDER BY
    inflow_family,
    inflow_subfamily;

ROLLBACK;

\echo 'ETL-214K COMPLETE - NO DATABASE WRITES'
