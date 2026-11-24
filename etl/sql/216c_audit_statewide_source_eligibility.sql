
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-216C - STATEWIDE SOURCE ACCOUNTING ELIGIBILITY AUDIT'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. REQUIRED OBJECTS AND SCHEMA CONTROLS'

DO $check$
DECLARE
    v_missing text;
BEGIN
    WITH required(schema_name, object_name) AS (
        VALUES
        ('reporting','v_washington_revenue_summary'),
        ('reporting','v_washington_tracked_expenditures'),
        ('reporting','v_washington_chip_expenditures'),
        ('reporting','v_washington_medicaid_expenditures'),
        ('reporting','v_washington_ssa_summary'),
        ('analysis','v_wa_federal_wage_allocation'),
        ('cms','medicare_core_state_year'),
        ('va','v_washington_county_gdx_control_total'),
        ('reference','federal_inflow_source_policy'),
        ('reference','federal_inflow_program_policy_mapping'),
        ('reference','federal_inflow_award_classification')
    )
    SELECT string_agg(
        format('%I.%I', schema_name, object_name), ', '
    )
    INTO v_missing
    FROM required
    WHERE to_regclass(
        format('%I.%I', schema_name, object_name)
    ) IS NULL;

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION
            'BLOCK: required objects missing: %', v_missing;
    END IF;

    RAISE NOTICE 'OBJECT PRESENCE CHECK PASS';
END
$check$;

\echo ''
\echo '2. REPORTED STREAMS AND ACCOUNTING MEASURE LABELS'

SELECT
    agency_code,
    program_code,
    COUNT(*) AS observations,
    COUNT(DISTINCT report_year) AS years,
    MIN(report_year) AS first_year,
    MAX(report_year) AS last_year,
    MIN(expenditure_dollars) AS minimum_reported_amount,
    MAX(expenditure_dollars) AS maximum_reported_amount,
    STRING_AGG(
        DISTINCT measure_note,
        ' | '
        ORDER BY measure_note
    ) AS documented_measure
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY agency_code, program_code
ORDER BY agency_code, program_code;

\echo ''
\echo '3. YEAR-BY-YEAR SOURCE ELIGIBILITY EVIDENCE'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
),
tracked AS (
    SELECT
        report_year AS fiscal_year,
        agency_code || ':' || program_code AS source_key,
        COUNT(*) AS observations,
        SUM(expenditure_dollars) AS amount
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY 1,2
),
other_sources AS (
    SELECT
        fiscal_year,
        'IRS:COLLECTIONS'::text AS source_key,
        COUNT(*) AS observations,
        SUM(gross_collections_dollars) AS amount
    FROM reporting.v_washington_revenue_summary
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year

    UNION ALL

    SELECT
        fiscal_year,
        'FEDERAL:ALLOCATED_WAGES',
        COUNT(*),
        SUM(allocated_wa_total_federal_wage_dollars)
    FROM analysis.v_wa_federal_wage_allocation
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year

    UNION ALL

    SELECT
        fiscal_year,
        'VA:GDX',
        COUNT(DISTINCT county_id),
        SUM(va_gdx_expenditure_amount)
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
),
sources AS (
    SELECT * FROM tracked
    UNION ALL
    SELECT * FROM other_sources
)
SELECT
    y.fiscal_year,
    s.source_key,
    COALESCE(s.observations,0) AS observations,
    s.amount,
    CASE
        WHEN s.source_key = 'IRS:COLLECTIONS'
            THEN 'REVENUE_CONTROL'
        WHEN s.source_key IN (
            'CMS:CHIP','CMS:MEDICAID'
        )
            THEN 'ACTUAL_FFY_EXPENDITURE'
        WHEN s.source_key = 'CMS:MEDICARE'
            THEN 'ORIGINAL_MEDICARE_CY_ONLY'
        WHEN s.source_key LIKE 'SSA:%'
            THEN 'ANNUALIZED_DECEMBER_BENEFIT'
        WHEN s.source_key = 'VA:GDX'
            THEN 'VA_GDX_EXPENDITURE_CONTROL'
        WHEN s.source_key = 'FEDERAL:ALLOCATED_WAGES'
            THEN 'ALLOCATED_COMPENSATION'
        ELSE 'MEASURE_UNCLASSIFIED'
    END AS accounting_measure_class,
    CASE
        WHEN s.source_key = 'IRS:COLLECTIONS'
            THEN 'REVENUE_SIDE_ONLY'
        WHEN s.source_key IN (
            'CMS:CHIP','CMS:MEDICAID'
        )
            THEN 'ADDITIVITY_REQUIRES_OVERLAP_CHECK'
        ELSE 'DO_NOT_AUTHORIZE_FROM_THIS_AUDIT'
    END AS proposed_eligibility
FROM years y
CROSS JOIN (
    SELECT DISTINCT source_key FROM sources
) k
LEFT JOIN sources s
  ON s.fiscal_year = y.fiscal_year
 AND s.source_key = k.source_key
ORDER BY y.fiscal_year, k.source_key;

\echo ''
\echo '4. CHIP AND MEDICAID EXISTING ADDITIVITY FLAGS'

SELECT
    'CHIP' AS program,
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024

UNION ALL

SELECT
    'MEDICAID',
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY program, fiscal_year;

\echo ''
\echo '5. MEDICARE AUTHORIZATION AND COMPLETENESS'

SELECT
    calendar_year,
    partc_year_completeness,
    partd_coverage_status,
    combined_period_status,
    timing_basis_status,
    ledger_status
FROM cms.medicare_core_state_year
WHERE state_id = 48
  AND calendar_year BETWEEN 2018 AND 2024
ORDER BY calendar_year;

\echo ''
\echo '6. SOURCE POLICY ACCOUNTING HIERARCHY'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_source_policy
WHERE (
    inflow_family IN (
        'CHIP','MEDICAID','MEDICARE','VA','SSA'
    )
    OR preferred_source ILIKE '%CMS%'
    OR preferred_source ILIKE '%SSA%'
    OR preferred_source ILIKE '%VA%'
)
AND (
    valid_from_fiscal_year IS NULL
    OR valid_from_fiscal_year <= 2024
)
AND (
    valid_through_fiscal_year IS NULL
    OR valid_through_fiscal_year >= 2018
)
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year,
    methodology_version;

\echo ''
\echo '7. PROGRAM POLICY DISPOSITIONS BY YEAR'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    COUNT(*) AS matching_policy_records,
    COUNT(DISTINCT m.federal_inflow_source_policy_id)
        AS distinct_source_policies
FROM years y
JOIN reference.federal_inflow_program_policy_mapping m
  ON (
      m.valid_from_fiscal_year IS NULL
      OR m.valid_from_fiscal_year <= y.fiscal_year
  )
 AND (
      m.valid_through_fiscal_year IS NULL
      OR m.valid_through_fiscal_year >= y.fiscal_year
  )
GROUP BY 1,2,3,4
ORDER BY
    y.fiscal_year,
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition;

\echo ''
\echo '8. POTENTIAL CONFLICTING PROGRAM DISPOSITIONS'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    m.source_system,
    m.source_program_code,
    COUNT(DISTINCT m.resolved_accounting_disposition)
        AS distinct_dispositions,
    STRING_AGG(
        DISTINCT m.resolved_accounting_disposition,
        ', '
    ) AS dispositions
FROM years y
JOIN reference.federal_inflow_program_policy_mapping m
  ON (
      m.valid_from_fiscal_year IS NULL
      OR m.valid_from_fiscal_year <= y.fiscal_year
  )
 AND (
      m.valid_through_fiscal_year IS NULL
      OR m.valid_through_fiscal_year >= y.fiscal_year
  )
GROUP BY 1,2,3
HAVING COUNT(DISTINCT m.resolved_accounting_disposition) > 1
ORDER BY 1,2,3;

\echo ''
\echo '9. HISTORICAL CHIP POLICY PRESERVATION'

SELECT
    methodology_version,
    inflow_subfamily,
    accounting_disposition,
    COUNT(*) AS awards
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.767'
  AND methodology_version IN (
      'ANALYSIS-215H-v1',
      'ANALYSIS-215I3-v1'
  )
GROUP BY 1,2,3
ORDER BY 1,2,3;

\echo ''
\echo '10. BASELINE COMPLETENESS CONTROLS'

DO $verify$
DECLARE
    v_bad bigint;
BEGIN
    SELECT COUNT(*) INTO v_bad
    FROM (
        SELECT fiscal_year
        FROM reporting.v_washington_revenue_summary
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    ) q;

    IF v_bad <> 7 THEN
        RAISE EXCEPTION
            'BLOCK: IRS revenue coverage % years', v_bad;
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024;

    IF v_bad <> 42 THEN
        RAISE EXCEPTION
            'BLOCK: tracked stream count %, expected 42',
            v_bad;
    END IF;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE methodology_version = 'ANALYSIS-215I3-v1';

    IF v_bad <> 6 THEN
        RAISE EXCEPTION
            'BLOCK: historical CHIP certification count %',
            v_bad;
    END IF;

    RAISE NOTICE 'ETL-216C BASELINE CONTROLS PASS';
    RAISE NOTICE
        'Eligibility labels are diagnostic, not ledger authorization';
END
$verify$;

ROLLBACK;

\echo ''
\echo 'ETL-216C COMPLETE - READ ONLY'
