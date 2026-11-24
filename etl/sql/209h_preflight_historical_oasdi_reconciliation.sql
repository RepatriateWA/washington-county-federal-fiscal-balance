
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209H - HISTORICAL OASDI RECONCILIATION PREFLIGHT'
\echo 'FY2018-FY2019 / SSA VS USASPENDING'
\echo 'READ ONLY - NO ACCOUNTING POLICY CHANGES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '900s';

\echo ''
\echo '1. SSA SOURCE COVERAGE AND GEOGRAPHY'

SELECT
    report_year,
    COUNT(*) AS source_rows,
    COUNT(DISTINCT county_id) AS linked_counties,
    COUNT(DISTINCT county_name) AS county_names,
    COUNT(DISTINCT benefit_type) AS benefit_types,
    COUNT(*) FILTER (
        WHERE county_id IS NULL
    ) AS unlinked_rows,
    COUNT(*) FILTER (
        WHERE annual_benefits_thousands IS NULL
    ) AS missing_annual_values
FROM ssa.benefit_payments
WHERE report_year IN (2018, 2019)
GROUP BY report_year
ORDER BY report_year;

\echo ''
\echo '2. SSA BENEFIT TYPE AND REFERENCE MAPPING'

SELECT
    b.report_year,
    b.benefit_type,
    r.benefit_group,
    r.is_total,
    COUNT(*) AS rows,
    COUNT(DISTINCT b.county_id) AS counties,
    SUM(b.beneficiary_count) AS beneficiaries,
    SUM(b.monthly_benefits_thousands) AS monthly_thousands,
    SUM(b.annual_benefits_thousands) AS annual_thousands
FROM ssa.benefit_payments b
LEFT JOIN reference.ssa_benefit_type r
  ON r.ssa_benefit_type_id = b.ssa_benefit_type_id
WHERE b.report_year IN (2018, 2019)
GROUP BY 1, 2, 3, 4
ORDER BY 1, 4 DESC, 2;

\echo ''
\echo '3. SSA TOTAL VERSUS DETAILED COMPONENTS'

WITH county_year AS (
    SELECT
        report_year,
        county_id,
        SUM(annual_benefits_thousands) FILTER (
            WHERE benefit_type = 'Total'
        ) AS published_total,
        SUM(annual_benefits_thousands) FILTER (
            WHERE benefit_type <> 'Total'
        ) AS component_total,
        SUM(beneficiary_count) FILTER (
            WHERE benefit_type = 'Total'
        ) AS total_beneficiaries,
        SUM(beneficiary_count) FILTER (
            WHERE benefit_type <> 'Total'
        ) AS component_beneficiaries
    FROM ssa.benefit_payments
    WHERE report_year IN (2018, 2019)
    GROUP BY report_year, county_id
)
SELECT
    report_year,
    COUNT(*) AS county_rows,
    COUNT(*) FILTER (
        WHERE published_total IS NULL
           OR component_total IS NULL
    ) AS missing_total_or_components,
    COUNT(*) FILTER (
        WHERE total_beneficiaries
              IS DISTINCT FROM component_beneficiaries
    ) AS beneficiary_mismatches,
    MAX(ABS(published_total - component_total))
        AS maximum_annual_rounding_difference_thousands,
    COUNT(*) FILTER (
        WHERE ABS(published_total - component_total) > 60
    ) AS annual_rounding_tolerance_failures
FROM county_year
GROUP BY report_year
ORDER BY report_year;

\echo ''
\echo '4. SSA STATEWIDE ANNUALIZED BENEFIT CONTROL'

SELECT
    report_year,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT county_id) AS counties,
    SUM(beneficiary_count) AS beneficiaries,
    SUM(monthly_benefits_thousands) * 1000
        AS december_monthly_dollars,
    SUM(annual_benefits_thousands) * 1000
        AS annualized_dollars
FROM ssa.benefit_payments
WHERE report_year IN (2018, 2019)
  AND benefit_type = 'Total'
GROUP BY report_year
ORDER BY report_year;

\echo ''
\echo '5. USASPENDING OASDI OBLIGATION CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND BTRIM(cfda_number) IN ('96.001', '96.002', '96.004')
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '6. SSA VS USASPENDING - NON-EQUIVALENT MEASURE COMPARISON'

WITH ssa_control AS (
    SELECT
        report_year AS fiscal_year,
        SUM(annual_benefits_thousands)::numeric * 1000
            AS ssa_annualized_dollars
    FROM ssa.benefit_payments
    WHERE report_year IN (2018, 2019)
      AND benefit_type = 'Total'
    GROUP BY report_year
),
usa_control AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        SUM(federal_action_obligation)::numeric
            AS usa_net_obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN ('96.001', '96.002', '96.004')
    GROUP BY action_date_fiscal_year
)
SELECT
    s.fiscal_year,
    s.ssa_annualized_dollars,
    u.usa_net_obligations,
    ROUND(
        s.ssa_annualized_dollars - u.usa_net_obligations,
        2
    ) AS measure_difference,
    ROUND(
        100 * (
            s.ssa_annualized_dollars - u.usa_net_obligations
        ) / NULLIF(s.ssa_annualized_dollars, 0),
        4
    ) AS difference_pct_of_ssa
FROM ssa_control s
JOIN usa_control u USING (fiscal_year)
ORDER BY s.fiscal_year;

\echo ''
\echo '7. EXISTING OASDI SOURCE POLICY VALIDITY'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'SOCIAL_SECURITY'
  AND inflow_subfamily = 'OASDI'
ORDER BY valid_from_fiscal_year, methodology_version;

\echo ''
\echo '8. HARD SOURCE AND POPULATION CONTROLS'

DO $$
DECLARE
    v_2018_count bigint;
    v_2019_count bigint;
    v_2018_usa numeric;
    v_2019_usa numeric;
    v_2018_ssa numeric;
    v_2019_ssa numeric;
BEGIN
    SELECT
        COUNT(*) FILTER (
            WHERE action_date_fiscal_year = 2018
        ),
        COUNT(*) FILTER (
            WHERE action_date_fiscal_year = 2019
        ),
        SUM(federal_action_obligation) FILTER (
            WHERE action_date_fiscal_year = 2018
        ),
        SUM(federal_action_obligation) FILTER (
            WHERE action_date_fiscal_year = 2019
        )
    INTO
        v_2018_count,
        v_2019_count,
        v_2018_usa,
        v_2019_usa
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN ('96.001', '96.002', '96.004');

    SELECT
        SUM(annual_benefits_thousands) FILTER (
            WHERE report_year = 2018
        ) * 1000,
        SUM(annual_benefits_thousands) FILTER (
            WHERE report_year = 2019
        ) * 1000
    INTO v_2018_ssa, v_2019_ssa
    FROM ssa.benefit_payments
    WHERE report_year IN (2018, 2019)
      AND benefit_type = 'Total';

    IF v_2018_count <> 2469
       OR v_2019_count <> 2469
       OR ROUND(v_2018_usa, 2) <> 21954487240.00
       OR ROUND(v_2019_usa, 2) <> 23309626595.00
       OR v_2018_ssa <> 22964844000
       OR v_2019_ssa <> 24211620000
    THEN
        RAISE EXCEPTION
            'ETL-209H FAIL: historical source controls differ from certified evidence';
    END IF;

    RAISE NOTICE
        'ETL-209H PASS: historical SSA and USAspending source controls verified';
END
$$;

ROLLBACK;

\echo 'ETL-209H COMPLETE - READ ONLY'
